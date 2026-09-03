"""`POST /transcribe` — the dictation endpoint, its validation order and its gate.

WHAT IS PINNED HERE
    That the route rejects in the order the shared contract fixes (token → lang
    → size → base64 → RIFF → format → frames → recognition), with the exact
    `stt_*` detail strings the renderer switches on; that the 2 MiB cap is
    enforced on the base64 STRING, before any decoding happens; that the model
    resolver honours the env override, the frozen layout and the dev tree; and
    that a model is loaded once per language, not once per request.

WHY THERE IS A FAKE VOSK
    vosk is NOT installed in this venv and the model directories are NOT in the
    tree (they are ~176 MB, fetched by the packaging step). A test suite that
    needed either would be red on every developer machine and green only on the
    build agent — so the recogniser is injected into `sys.modules` and the model
    directory is built out of empty files in tmp. What is being measured is this
    repo's code: the resolver, the validation order and the chunking, none of
    which are vosk's behaviour.
"""

import base64
import io
import json
import os
import sys
import wave

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from providers import stt_vosk
from routes.transcribe_routes import create_transcribe_router, MAX_B64_CHARS


# ── Fake vosk ───────────────────────────────────────────────────────────────

class _FakeRecognizer:
    def __init__(self, model, rate, log):
        self.model = model
        self.rate = rate
        self._log = log
        self.chunks = []

    def AcceptWaveform(self, data):
        self.chunks.append(data)
        return False

    def FinalResult(self):
        return json.dumps({"text": self._log["text"]})


class _FakeVosk:
    """Records what the route asked of it; returns a canned recognition."""

    def __init__(self, text="merhaba dunya", model_error=None):
        self.log = {"text": text}
        self.log_levels = []
        self.model_paths = []
        self.recognizers = []
        self._model_error = model_error

    def SetLogLevel(self, level):
        self.log_levels.append(level)

    def Model(self, path):
        self.model_paths.append(path)
        if self._model_error is not None:
            raise self._model_error
        return f"model@{path}"

    def KaldiRecognizer(self, model, rate):
        rec = _FakeRecognizer(model, rate, self.log)
        self.recognizers.append(rec)
        return rec


def _install_models(tmp_path, monkeypatch):
    """Both shipped layouts: TR keeps `final.mdl` at the root, EN under `am/`."""
    root = tmp_path / "vosk"
    tr = root / stt_vosk.MODEL_NAMES["tr"]
    tr.mkdir(parents=True)
    (tr / "final.mdl").write_bytes(b"")
    en_am = root / stt_vosk.MODEL_NAMES["en"] / "am"
    en_am.mkdir(parents=True)
    (en_am / "final.mdl").write_bytes(b"")
    monkeypatch.setenv("GAMACHINE_VOSK_MODELS_DIR", str(root))
    return root


@pytest.fixture(autouse=True)
def _clean_model_cache():
    stt_vosk.reset_cache()
    yield
    stt_vosk.reset_cache()


@pytest.fixture
def fake_vosk(monkeypatch):
    fake = _FakeVosk()
    monkeypatch.setitem(sys.modules, "vosk", fake)
    return fake


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(create_transcribe_router())
    return TestClient(app)


HEADERS = {"X-Session-Token": "dev"}


def _wav(frames=16000, channels=1, width=2, rate=16000, pcm=None):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm if pcm is not None else b"\x01\x02" * (frames * channels * width // 2))
    return buf.getvalue()


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _post(client, **body):
    return client.post("/transcribe", json=body, headers=HEADERS)


# ── Happy path ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", ["tr", "en"])
def test_a_valid_wav_is_transcribed_for_each_supported_language(client, fake_vosk, tmp_path, monkeypatch, lang):
    _install_models(tmp_path, monkeypatch)
    response = _post(client, lang=lang, wav_base64=_b64(_wav(frames=16000)))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "merhaba dunya"
    assert body["lang"] == lang
    # 16000 frames at 16 kHz is exactly one second; the number is computed from
    # the audio, not from how long recognition took.
    assert body["duration_ms"] == 1000
    assert fake_vosk.model_paths == [os.path.join(str(tmp_path / "vosk"), stt_vosk.MODEL_NAMES[lang])]


def test_the_recogniser_receives_the_exact_pcm_in_8000_byte_chunks(client, fake_vosk, tmp_path, monkeypatch):
    _install_models(tmp_path, monkeypatch)
    pcm = bytes((i * 7) % 256 for i in range(20000))     # 10000 frames, not a chunk multiple
    response = _post(client, lang="tr", wav_base64=_b64(_wav(pcm=pcm)))
    assert response.status_code == 200, response.text

    rec = fake_vosk.recognizers[0]
    assert rec.rate == 16000
    assert b"".join(rec.chunks) == pcm, "the audio reaching vosk is not the audio that was posted"
    assert [len(c) for c in rec.chunks] == [8000, 8000, 4000]


def test_the_vosk_stderr_logger_is_silenced_once(client, fake_vosk, tmp_path, monkeypatch):
    """Level 0 (the default) floods the console the desktop app tails."""
    _install_models(tmp_path, monkeypatch)
    assert _post(client, lang="tr", wav_base64=_b64(_wav())).status_code == 200
    assert fake_vosk.log_levels == [-1]


def test_an_empty_recognition_is_a_200_not_an_error(client, fake_vosk, tmp_path, monkeypatch):
    """Silence is a normal outcome of dictation; the renderer has a named state
    for it. Turning it into a 4xx would make "you said nothing" indistinguishable
    from "the request was malformed"."""
    _install_models(tmp_path, monkeypatch)
    fake_vosk.log["text"] = ""
    response = _post(client, lang="tr", wav_base64=_b64(_wav()))
    assert response.status_code == 200
    assert response.json()["text"] == ""


# ── Rejections ──────────────────────────────────────────────────────────────

def test_an_unsupported_language_is_rejected(client, fake_vosk, tmp_path, monkeypatch):
    _install_models(tmp_path, monkeypatch)
    response = _post(client, lang="de", wav_base64=_b64(_wav()))
    assert response.status_code == 400
    assert response.json()["detail"] == "stt_bad_lang"


def test_a_body_that_is_not_base64_is_rejected(client, fake_vosk, tmp_path, monkeypatch):
    _install_models(tmp_path, monkeypatch)
    response = _post(client, lang="tr", wav_base64="not base64 !!!")
    assert response.status_code == 400
    assert response.json()["detail"] == "stt_bad_base64"


def test_bytes_that_are_not_a_riff_file_are_rejected(client, fake_vosk, tmp_path, monkeypatch):
    _install_models(tmp_path, monkeypatch)
    response = _post(client, lang="tr", wav_base64=_b64(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64))
    assert response.status_code == 400
    assert response.json()["detail"] == "stt_not_wav"


@pytest.mark.parametrize(
    "name,kwargs",
    [
        ("stereo", {"channels": 2}),
        ("8 kHz", {"rate": 8000}),
        ("8-bit", {"width": 1}),
    ],
)
def test_a_wav_that_is_not_16k_mono_16bit_is_rejected(client, fake_vosk, tmp_path, monkeypatch, name, kwargs):
    """Vosk is created for one sample rate and silently mis-recognises anything
    else; resampling server-side would hide a renderer bug rather than report it."""
    _install_models(tmp_path, monkeypatch)
    response = _post(client, lang="tr", wav_base64=_b64(_wav(frames=1600, **kwargs)))
    assert response.status_code == 400, name
    assert response.json()["detail"] == "stt_wrong_format", name


@pytest.mark.parametrize(
    "keep_bytes",
    [46, 44 + 8000],
    ids=["two bytes of a declared second", "a quarter of a declared second"],
)
def test_a_wav_whose_data_chunk_is_shorter_than_declared_is_rejected(client, fake_vosk, tmp_path, monkeypatch, keep_bytes):
    """Class: declared-length-not-enforced. `wave` reports the declared frame
    count; `readframes` silently returns fewer bytes. The audit probe posted a
    file declaring 32,000 PCM bytes with two present and got a 200 whose
    recognition ran on two bytes."""
    _install_models(tmp_path, monkeypatch)
    truncated = _wav(frames=16000)[:keep_bytes]
    response = _post(client, lang="tr", wav_base64=_b64(truncated))
    assert response.status_code == 400
    assert response.json()["detail"] == "stt_not_wav"
    assert fake_vosk.recognizers == []


def test_a_wav_with_zero_frames_is_rejected(client, fake_vosk, tmp_path, monkeypatch):
    _install_models(tmp_path, monkeypatch)
    response = _post(client, lang="tr", wav_base64=_b64(_wav(pcm=b"")))
    assert response.status_code == 400
    assert response.json()["detail"] == "stt_empty_audio"


def test_an_oversize_body_is_refused_before_it_is_decoded(client, fake_vosk, tmp_path, monkeypatch):
    """The cap is on the base64 STRING, and this is the point of it: a hostile
    50 MB string must cost the backend a `len()`, not a 37 MB allocation. So the
    test both stays cheap (no real 2 MiB WAV is built) and proves the ordering
    by making any decode attempt an error."""
    _install_models(tmp_path, monkeypatch)

    def _explode(*args, **kwargs):
        raise AssertionError("base64 was decoded despite the string exceeding the cap")

    monkeypatch.setattr(base64, "b64decode", _explode)
    response = _post(client, lang="tr", wav_base64="A" * (MAX_B64_CHARS + 1))
    assert response.status_code == 413
    assert response.json()["detail"] == "stt_too_large"


# ── Model unavailability ────────────────────────────────────────────────────

def test_a_missing_model_directory_is_a_503(client, fake_vosk, tmp_path, monkeypatch):
    monkeypatch.setenv("GAMACHINE_VOSK_MODELS_DIR", str(tmp_path / "nowhere"))
    response = _post(client, lang="tr", wav_base64=_b64(_wav()))
    assert response.status_code == 503
    assert response.json()["detail"] == "stt_model_missing"
    assert fake_vosk.model_paths == [], "vosk was asked to load a directory that does not exist"


def test_a_model_that_refuses_to_load_is_a_503(client, tmp_path, monkeypatch):
    _install_models(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "vosk", _FakeVosk(model_error=RuntimeError("bad graph")))
    response = _post(client, lang="tr", wav_base64=_b64(_wav()))
    assert response.status_code == 503
    assert response.json()["detail"] == "stt_model_load_failed"


def test_a_backend_without_vosk_installed_is_a_503_not_a_crash(client, tmp_path, monkeypatch):
    """`sys.modules["vosk"] = None` is what an absent package looks like to
    `import`: the whole feature is unavailable, but every other route — and the
    process itself — must keep working, which is why the import is inside the
    loader."""
    _install_models(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "vosk", None)
    response = _post(client, lang="tr", wav_base64=_b64(_wav()))
    assert response.status_code == 503
    assert response.json()["detail"] == "stt_model_load_failed"


# ── The token gate ──────────────────────────────────────────────────────────

class TestTheTokenGate:
    """The suite-wide conftest runs token-less on purpose; this class opts back
    IN to a configured token, otherwise `_check_token` returns early and the
    rejection tests would pass with no gate present at all."""

    TOKEN = "transcribe-token-4f21"

    @pytest.fixture(autouse=True)
    def _real_token(self, monkeypatch):
        monkeypatch.delenv("UNITYAI_ALLOW_NO_TOKEN", raising=False)
        monkeypatch.setenv("LOCAL_APP_TOKEN", self.TOKEN)

    def _body(self):
        return {"lang": "tr", "wav_base64": _b64(_wav())}

    def test_a_request_without_the_header_never_reaches_the_handler(self, client, fake_vosk, tmp_path, monkeypatch):
        # The header is declared required, so FastAPI validation rejects with 422
        # before the body runs — measured, not assumed.
        _install_models(tmp_path, monkeypatch)
        response = client.post("/transcribe", json=self._body())
        assert response.status_code == 422
        assert fake_vosk.model_paths == []

    def test_a_wrong_token_is_rejected(self, client, fake_vosk, tmp_path, monkeypatch):
        _install_models(tmp_path, monkeypatch)
        response = client.post("/transcribe", json=self._body(), headers={"X-Session-Token": "WRONG"})
        assert response.status_code == 401
        assert fake_vosk.model_paths == []

    def test_the_configured_token_is_accepted(self, client, fake_vosk, tmp_path, monkeypatch):
        _install_models(tmp_path, monkeypatch)
        response = client.post("/transcribe", json=self._body(), headers={"X-Session-Token": self.TOKEN})
        assert response.status_code == 200


# ── The resolver ────────────────────────────────────────────────────────────

def test_the_env_override_wins_over_everything_else(tmp_path, monkeypatch):
    """It is an override, not a fallback: a Docker mount or a test must not be
    silently overtaken by a tree next to the executable."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("GAMACHINE_VOSK_MODELS_DIR", str(tmp_path / "chosen"))
    assert stt_vosk.models_root() == str(tmp_path / "chosen")


def test_the_frozen_layout_resolves_next_to_the_resources_directory(tmp_path, monkeypatch):
    """backend.exe sits at <app>/resources/Backend/, electron-builder puts the
    models at <app>/resources/vosk/ — hence the `..` hop."""
    monkeypatch.delenv("GAMACHINE_VOSK_MODELS_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    exe = tmp_path / "resources" / "Backend" / "backend.exe"
    monkeypatch.setattr(sys, "executable", str(exe))
    assert os.path.normpath(stt_vosk.models_root()) == os.path.normpath(str(tmp_path / "resources" / "vosk"))


def test_the_dev_layout_resolves_into_the_repo_vendor_tree(monkeypatch):
    monkeypatch.delenv("GAMACHINE_VOSK_MODELS_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    root = stt_vosk.models_root()
    assert root.replace("\\", "/").endswith("Backend/vendor/models/vosk")
    assert os.path.isabs(root)


def test_missing_models_finds_final_mdl_in_both_shipped_layouts(tmp_path, monkeypatch):
    """TR 0.3 is flat (final.mdl at the root), EN 0.15 keeps it under am/. A probe
    for one fixed path would have declared one of the two missing."""
    _install_models(tmp_path, monkeypatch)
    assert stt_vosk.missing_models() == []

    os.remove(tmp_path / "vosk" / stt_vosk.MODEL_NAMES["en"] / "am" / "final.mdl")
    assert stt_vosk.missing_models() == ["en"]

    monkeypatch.setenv("GAMACHINE_VOSK_MODELS_DIR", str(tmp_path / "empty"))
    assert stt_vosk.missing_models() == ["tr", "en"]


# ── The model cache ─────────────────────────────────────────────────────────

def test_a_model_is_loaded_once_per_language_not_once_per_request(client, fake_vosk, tmp_path, monkeypatch):
    """Loading the TR model took 237 ms in the frozen probe (3 Sep 2026); paying
    that on every dictation would double the perceived latency of short clips."""
    _install_models(tmp_path, monkeypatch)
    body = _b64(_wav())

    assert _post(client, lang="tr", wav_base64=body).status_code == 200
    assert _post(client, lang="tr", wav_base64=body).status_code == 200
    assert len(fake_vosk.model_paths) == 1
    assert len(fake_vosk.recognizers) == 2, "the recogniser is per request, only the model is shared"

    assert _post(client, lang="en", wav_base64=body).status_code == 200
    assert len(fake_vosk.model_paths) == 2
