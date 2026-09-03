"""Resolves the bundled Vosk speech models and runs offline recognition.

Frozen: electron-builder puts the models at ``<app>/resources/vosk/`` while the
frozen backend lives at ``<app>/resources/Backend/backend.exe`` — hence the
``..`` hop off ``sys.executable``.
Dev: ``Backend/vendor/models/vosk`` (same dirname-chain idiom as
``video_bin._vendor_dir``).

``import vosk`` happens INSIDE the loader, never at module import: the backend
must start, and every other route must work, on a machine where vosk was never
installed (Docker image, a dev tree without the fetch step).
"""
import json
import os
import secrets
import sys
import threading
import time

MODEL_NAMES = {
    "tr": "vosk-model-small-tr-0.3",
    "en": "vosk-model-small-en-us-0.15",
}

SUPPORTED_LANGS = tuple(MODEL_NAMES)

SAMPLE_RATE = 16000
# 4000 frames × 2 bytes — the block size vosk's own examples feed.
_CHUNK_BYTES = 8000


class SttModelMissing(Exception):
    """No model directory for this language on this machine."""

    def __init__(self, lang: str):
        super().__init__(f"vosk model for '{lang}' not found")
        self.lang = lang


class SttModelLoadFailed(Exception):
    """vosk could not be imported, or ``Model()`` refused the directory."""

    def __init__(self, lang: str, cause: BaseException):
        super().__init__(f"vosk model for '{lang}' failed to load: {cause}")
        self.lang = lang
        self.cause = cause


def _vendor_models_dir() -> str:
    # providers/ → app/ → Backend/
    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(backend, "vendor", "models", "vosk")


def models_root() -> str:
    """The directory that holds the per-language model folders.

    The env var is not a fallback but an override: when it is set it is the ONLY
    candidate, so a test or a Docker mount cannot be silently overtaken by a
    stale tree next to the executable.
    """
    env = os.environ.get("GAMACHINE_VOSK_MODELS_DIR", "").strip()
    if env:
        return env
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "..", "vosk")
    return _vendor_models_dir()


def model_dir(lang: str) -> str:
    return os.path.join(models_root(), MODEL_NAMES[lang])


def _has_acoustic_model(root: str) -> bool:
    """``final.mdl`` anywhere below ``root``.

    Its position is not the same in the two shipped models: TR 0.3 is flat and
    keeps it at the root, EN 0.15 keeps it under ``am/``. Probing for a fixed
    path would have called one of the two missing.
    """
    if not os.path.isdir(root):
        return False
    for _dirpath, _dirnames, filenames in os.walk(root):
        if "final.mdl" in filenames:
            return True
    return False


def missing_models() -> "list[str]":
    """Languages whose model directory is absent or incomplete (empty = all present)."""
    return [lang for lang in SUPPORTED_LANGS if not _has_acoustic_model(model_dir(lang))]


_models: dict = {}
_models_lock = threading.Lock()


def _load_model(lang: str):
    """Returns the cached ``vosk.Model`` for ``lang``, loading it on first use.

    The lock covers loading ONLY. Recognition is the long part (hundreds of ms)
    and vosk's Model is safe to share across recognisers, so holding the lock
    through it would serialise every concurrent dictation for no benefit.
    """
    cached = _models.get(lang)
    if cached is not None:
        return cached
    with _models_lock:
        cached = _models.get(lang)
        if cached is not None:
            return cached
        directory = model_dir(lang)
        if not _has_acoustic_model(directory):
            raise SttModelMissing(lang)
        try:
            import vosk
        except Exception as exc:                     # noqa: BLE001 — see below
            # Not just ImportError: on Windows vosk's __init__ calls
            # os.add_dll_directory on its own package dir and raises
            # FileNotFoundError when a build stripped it (measured 3 Sep 2026,
            # PyInstaller without collect_all('vosk')).
            raise SttModelLoadFailed(lang, exc) from exc
        # Vosk logs to stderr at level 0 by default.
        try:
            vosk.SetLogLevel(-1)
        except Exception:                            # noqa: BLE001
            pass
        try:
            model = vosk.Model(directory)
        except Exception as exc:                     # noqa: BLE001
            raise SttModelLoadFailed(lang, exc) from exc
        _models[lang] = model
        return model


def _new_recognizer(lang: str):
    model = _load_model(lang)
    import vosk

    try:
        return vosk.KaldiRecognizer(model, SAMPLE_RATE)
    except Exception as exc:                         # noqa: BLE001
        raise SttModelLoadFailed(lang, exc) from exc


def transcribe_pcm(pcm: bytes, lang: str) -> "tuple[str, int]":
    """Recognises raw 16 kHz mono 16-bit PCM. Returns ``(text, duration_ms)``."""
    recognizer = _new_recognizer(lang)
    for start in range(0, len(pcm), _CHUNK_BYTES):
        recognizer.AcceptWaveform(pcm[start:start + _CHUNK_BYTES])
    try:
        text = json.loads(recognizer.FinalResult()).get("text", "")
    except (ValueError, TypeError, AttributeError):
        # An unparseable result is an empty transcription, not a 500: the
        # renderer already has a named state for "nothing was recognised".
        text = ""
    duration_ms = int(len(pcm) // 2 * 1000 / SAMPLE_RATE)
    return text, duration_ms


def transcribe_wav(wav_bytes: bytes, lang: str) -> "tuple[str, int]":
    """Recognises a whole RIFF WAV file. Caller has already validated the format."""
    import io
    import wave

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        frames = wav.getnframes()
        pcm = wav.readframes(frames)
    return transcribe_pcm(pcm, lang)


def reset_cache() -> None:
    """Drops the loaded models and any live session. Exists for tests."""
    with _models_lock:
        _models.clear()
    with _sessions_lock:
        _sessions.clear()


# ── Streaming sessions ──────────────────────────────────────────────────────
#
# Live dictation feeds one recogniser across many small HTTP chunks, so the
# recogniser has to outlive the request. The registry below is that lifetime:
# ids handed out by the create route, dropped by finish or by the idle TTL.

MAX_SESSIONS = 4
SESSION_TTL_S = 90.0

# The time source is a module attribute so a test can replace it; monotonic
# because the TTL must survive a wall-clock jump.
_now = time.monotonic


class SttNoSession(Exception):
    """No live session with this id (never existed, finished, or expired)."""


class SttBusy(Exception):
    """MAX_SESSIONS recognisers are already alive."""


class _Session:
    __slots__ = ("id", "lang", "recognizer", "lock", "created", "last_seen", "total_bytes")

    def __init__(self, session_id: str, lang: str, recognizer):
        self.id = session_id
        self.lang = lang
        self.recognizer = recognizer
        # Per session, not global: two dictations must not serialise on each
        # other, but the chunks of ONE dictation must reach vosk in order.
        self.lock = threading.Lock()
        now = _now()
        self.created = now
        self.last_seen = now
        self.total_bytes = 0


_sessions: "dict[str, _Session]" = {}
_sessions_lock = threading.Lock()


def purge_expired(now=None) -> "list[str]":
    """Drops sessions idle for longer than the TTL. Returns the dropped ids."""
    if now is None:
        now = _now()
    dropped = []
    with _sessions_lock:
        for session_id, session in list(_sessions.items()):
            if now - session.last_seen > SESSION_TTL_S:
                del _sessions[session_id]
                dropped.append(session_id)
    return dropped


def open_session(lang: str) -> str:
    """Creates a recogniser and returns its session id.

    The model is loaded HERE rather than on the first chunk so the cost (and the
    503 when it is missing) lands on the call the renderer can still show an
    error for, and the first chunk stays fast.
    """
    with _sessions_lock:
        if len(_sessions) >= MAX_SESSIONS:
            raise SttBusy()
    recognizer = _new_recognizer(lang)          # outside the lock: can take ~250 ms
    session_id = secrets.token_urlsafe(16)
    with _sessions_lock:
        if len(_sessions) >= MAX_SESSIONS:
            raise SttBusy()
        _sessions[session_id] = _Session(session_id, lang, recognizer)
    return session_id


def _get(session_id: str) -> _Session:
    with _sessions_lock:
        session = _sessions.get(session_id)
    if session is None:
        raise SttNoSession(session_id)
    return session


def session_bytes(session_id: str) -> int:
    """Decoded bytes fed to this session so far (the caller's running total)."""
    return _get(session_id).total_bytes


def feed(session_id: str, pcm: bytes) -> str:
    """Feeds one chunk and returns the partial text so far.

    An empty chunk is a keep-alive: it refreshes ``last_seen`` and reports the
    current partial without touching the recogniser.
    """
    session = _get(session_id)
    with session.lock:
        for start in range(0, len(pcm), _CHUNK_BYTES):
            session.recognizer.AcceptWaveform(pcm[start:start + _CHUNK_BYTES])
        session.total_bytes += len(pcm)
        try:
            partial = json.loads(session.recognizer.PartialResult()).get("partial", "")
        except (ValueError, TypeError, AttributeError):
            partial = ""
        session.last_seen = _now()
    return partial


def finish(session_id: str, discard: bool = False) -> "tuple[str, int]":
    """Removes the session and returns ``(text, duration_ms)``.

    With ``discard`` the recogniser is dropped without asking it for a result —
    a cancelled dictation must not pay for a recognition nobody will read.
    """
    with _sessions_lock:
        session = _sessions.pop(session_id, None)
    if session is None:
        raise SttNoSession(session_id)
    if discard:
        return "", 0
    with session.lock:
        try:
            text = json.loads(session.recognizer.FinalResult()).get("text", "")
        except (ValueError, TypeError, AttributeError):
            text = ""
        total = session.total_bytes
    return text, total // 2 * 1000 // SAMPLE_RATE
