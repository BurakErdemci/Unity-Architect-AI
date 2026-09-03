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


class TranscribeRequest(BaseModel):
    lang: str
    wav_base64: str


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
        except Exception:                            # noqa: BLE001
            # `wave` raises wave.Error, EOFError or struct.error depending on
            # where the bytes stop being a RIFF file; all three mean the same
            # thing to the caller.
            raise HTTPException(400, detail="stt_not_wav")

        if channels != 1 or width != 2 or rate != stt_vosk.SAMPLE_RATE:
            raise HTTPException(400, detail="stt_wrong_format")

        if frames <= 0:
            raise HTTPException(400, detail="stt_empty_audio")

        try:
            text, duration_ms = stt_vosk.transcribe_wav(wav_bytes, request.lang)
        except stt_vosk.SttModelMissing:
            raise HTTPException(503, detail="stt_model_missing")
        except stt_vosk.SttModelLoadFailed as exc:
            logger.warning(f"[transcribe] vosk model '{request.lang}' unavailable: {exc}")
            raise HTTPException(503, detail="stt_model_load_failed")

        return {"text": text, "lang": request.lang, "duration_ms": duration_ms}

    return router
