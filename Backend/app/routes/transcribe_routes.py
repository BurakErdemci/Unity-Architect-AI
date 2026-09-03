"""`POST /transcribe` — offline dictation. Audio in, text out; nothing is sent.

The renderer records 16 kHz mono 16-bit PCM, wraps it in a RIFF WAV, base64s it
and posts it here; the recognised text is inserted at the caret of the chat box
and the user presses Enter themselves.

The handler is a plain `def` on purpose: recognition is CPU-bound and blocking
(hundreds of ms), so FastAPI runs it in the threadpool instead of stalling the
event loop the way an `async def` body would.
"""
import base64
import binascii
import io
import logging
import re
import wave

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from auth_utils import _check_token
from providers import stt_vosk

logger = logging.getLogger(__name__)

MAX_WAV_BYTES = 2_097_152                 # 2 MiB decoded ≈ 65 s of 16 kHz mono PCM
# ceil(2 MiB / 3) * 4 — the longest base64 string that can still decode within
# the cap. Checked BEFORE decoding so a hostile 50 MB string is refused without
# ever being materialised in memory.
MAX_B64_CHARS = 2_796_204


# Live dictation chunks. ~2 s of 16 kHz mono PCM per chunk; the base64 bound is
# ceil(65536 / 3) * 4, checked before decoding for the same reason as above.
MAX_CHUNK_BYTES = 65_536
MAX_CHUNK_B64_CHARS = 87_384
MAX_SESSION_BYTES = 2_097_152             # same 2 MiB budget as the one-shot route

# A session id only ever comes from `secrets.token_urlsafe`. Anything outside
# that alphabet cannot name a live session, so it is answered like any other
# unknown id instead of reaching the registry.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class TranscribeRequest(BaseModel):
    lang: str
    wav_base64: str


class SessionCreateRequest(BaseModel):
    lang: str


class SessionChunkRequest(BaseModel):
    pcm_base64: str


class SessionFinishRequest(BaseModel):
    discard: bool = False


def create_transcribe_router():
    router = APIRouter()

    @router.post("/transcribe")
    def transcribe(request: TranscribeRequest, x_session_token: str = Header(alias="X-Session-Token")):
        _check_token(x_session_token)

        if request.lang not in stt_vosk.SUPPORTED_LANGS:
            raise HTTPException(400, detail="stt_bad_lang")

        if len(request.wav_base64) > MAX_B64_CHARS:
            raise HTTPException(413, detail="stt_too_large")

        try:
            wav_bytes = base64.b64decode(request.wav_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, detail="stt_bad_base64")

        if len(wav_bytes) > MAX_WAV_BYTES:
            raise HTTPException(413, detail="stt_too_large")

        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
                channels = wav.getnchannels()
                width = wav.getsampwidth()
                rate = wav.getframerate()
                frames = wav.getnframes()
                pcm = wav.readframes(frames)
        except Exception:                            # noqa: BLE001
            # `wave` raises wave.Error, EOFError or struct.error depending on
            # where the bytes stop being a RIFF file; all three mean the same
            # thing to the caller.
            raise HTTPException(400, detail="stt_not_wav")

        if channels != 1 or width != 2 or rate != stt_vosk.SAMPLE_RATE:
            raise HTTPException(400, detail="stt_wrong_format")

        if frames <= 0:
            raise HTTPException(400, detail="stt_empty_audio")

        # `wave` trusts the declared data length; `readframes` returns what is
        # actually there. A truncated file otherwise reaches recognition as
        # complete audio (audit probe, 3 Sep 2026: 32,000 declared, 2 present, 200).
        if len(pcm) != frames * channels * width:
            raise HTTPException(400, detail="stt_not_wav")

        try:
            text, duration_ms = stt_vosk.transcribe_pcm(pcm, request.lang)
        except stt_vosk.SttModelMissing:
            raise HTTPException(503, detail="stt_model_missing")
        except stt_vosk.SttModelLoadFailed as exc:
            logger.warning(f"[transcribe] vosk model '{request.lang}' unavailable: {exc}")
            raise HTTPException(503, detail="stt_model_load_failed")

        return {"text": text, "lang": request.lang, "duration_ms": duration_ms}

    @router.post("/transcribe/session")
    def open_session(request: SessionCreateRequest, x_session_token: str = Header(alias="X-Session-Token")):
        _check_token(x_session_token)
        stt_vosk.purge_expired()

        if request.lang not in stt_vosk.SUPPORTED_LANGS:
            raise HTTPException(400, detail="stt_bad_lang")

        try:
            session_id = stt_vosk.open_session(request.lang)
        except stt_vosk.SttBusy:
            raise HTTPException(503, detail="stt_busy")
        except stt_vosk.SttModelMissing:
            raise HTTPException(503, detail="stt_model_missing")
        except stt_vosk.SttModelLoadFailed as exc:
            logger.warning(f"[transcribe] vosk model '{request.lang}' unavailable: {exc}")
            raise HTTPException(503, detail="stt_model_load_failed")

        return {"session_id": session_id, "lang": request.lang}

    @router.post("/transcribe/session/{session_id}")
    def feed_session(
        session_id: str,
        request: SessionChunkRequest,
        x_session_token: str = Header(alias="X-Session-Token"),
    ):
        # Deliberately silent: this runs twice a second while the user speaks,
        # and a log line per chunk would flood the console the desktop app tails.
        _check_token(x_session_token)
        stt_vosk.purge_expired()

        if not _SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(404, detail="stt_no_session")

        if len(request.pcm_base64) > MAX_CHUNK_B64_CHARS:
            raise HTTPException(413, detail="stt_too_large")

        try:
            pcm = base64.b64decode(request.pcm_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, detail="stt_bad_base64")

        if len(pcm) > MAX_CHUNK_BYTES:
            raise HTTPException(413, detail="stt_too_large")

        if len(pcm) % 2:
            # Half a sample: the caller sliced its Int16 buffer wrong, and vosk
            # would silently reinterpret every following byte.
            raise HTTPException(400, detail="stt_wrong_format")

        try:
            # The cap is read before feeding so the session survives the refusal
            # and the caller can still finish what it has already said.
            if stt_vosk.session_bytes(session_id) + len(pcm) > MAX_SESSION_BYTES:
                raise HTTPException(413, detail="stt_too_large")
            partial = stt_vosk.feed(session_id, pcm)
            total = stt_vosk.session_bytes(session_id)
        except stt_vosk.SttNoSession:
            raise HTTPException(404, detail="stt_no_session")

        return {"partial": partial, "bytes": total}

    @router.post("/transcribe/session/{session_id}/finish")
    def finish_session(
        session_id: str,
        request: SessionFinishRequest,
        x_session_token: str = Header(alias="X-Session-Token"),
    ):
        _check_token(x_session_token)
        stt_vosk.purge_expired()

        if not _SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(404, detail="stt_no_session")

        try:
            text, duration_ms = stt_vosk.finish(session_id, discard=request.discard)
        except stt_vosk.SttNoSession:
            raise HTTPException(404, detail="stt_no_session")

        return {"text": text, "duration_ms": duration_ms}

    return router
