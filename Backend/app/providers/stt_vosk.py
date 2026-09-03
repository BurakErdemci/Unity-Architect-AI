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
import sys
import threading

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
    """Drops the loaded models. Exists for tests; nothing in the app calls it."""
    with _models_lock:
        _models.clear()
