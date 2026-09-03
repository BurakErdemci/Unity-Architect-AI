"""Live dictation over HTTP chunk sessions — the registry and its three routes.

WHAT IS PINNED HERE
    That a recogniser survives across requests and that its lifetime is bounded
    on three axes the desktop app cannot police from outside: how many sessions
    may be alive (MAX_SESSIONS), how long an abandoned one lingers (the idle
    TTL), and how much audio one may swallow (per chunk and per session). Plus
    the rejection details the renderer switches on, and the fact that chunks of
    one session reach vosk in order even when two arrive at once.

WHY THERE IS A FAKE VOSK
    Same reason as `test_transcribe_route.py`: vosk is not installed in this
    venv and the ~176 MB models are not in the tree. The recogniser is injected
    into `sys.modules`; what is measured is this repo's session bookkeeping.
    The fake's `PartialResult` grows one token per accepted block, so "the
    partial grows" is a statement about what the route fed, not about vosk.
"""

import base64
import json
import sys
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from providers import stt_vosk
from routes.transcribe_routes import (
    MAX_CHUNK_B64_CHARS,
    MAX_CHUNK_BYTES,
    MAX_SESSION_BYTES,
    create_transcribe_router,
)


# ── Fake vosk ───────────────────────────────────────────────────────────────

class _FakeRecognizer:
    """Records blocks; reports one token per block as the running partial."""

    def __init__(self, model, rate, log):
        self.model = model
        self.rate = rate
        self._log = log
        self.chunks = []
        self.final_calls = 0
        # Set while inside AcceptWaveform. Two threads seeing it at once would
        # mean the per-session lock is missing.
        self.inside = False
        self.overlapped = False
        self.block_delay = 0.0

    def AcceptWaveform(self, data):
        if self.inside:
            self.overlapped = True
        self.inside = True
        try:
            if self.block_delay:
                time.sleep(self.block_delay)
            self.chunks.append(data)
        finally:
            self.inside = False
        return False

    def PartialResult(self):
        return json.dumps({"partial": " ".join(f"w{i}" for i in range(1, len(self.chunks) + 1))})

    def FinalResult(self):
        self.final_calls += 1
        return json.dumps({"text": self._log["text"]})


class _FakeVosk:
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
def _clean_state():
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


@pytest.fixture
def ready(client, fake_vosk, tmp_path, monkeypatch):
    """A client with the fake models installed — the state every test starts from."""
    _install_models(tmp_path, monkeypatch)
    return client


HEADERS = {"X-Session-Token": "dev"}


def _open(client, lang="tr"):
    return client.post("/transcribe/session", json={"lang": lang}, headers=HEADERS)


def _chunk(client, session_id, pcm=None, pcm_base64=None):
    if pcm_base64 is None:
        pcm_base64 = base64.b64encode(pcm or b"").decode("ascii")
    return client.post(f"/transcribe/session/{session_id}", json={"pcm_base64": pcm_base64}, headers=HEADERS)


def _finish(client, session_id, **body):
    return client.post(f"/transcribe/session/{session_id}/finish", json=body, headers=HEADERS)


def _new_session(client, lang="tr"):
    response = _open(client, lang)
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


# ── Session creation ────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", ["tr", "en"])
def test_a_session_can_be_opened_for_each_supported_language(ready, fake_vosk, lang):
    response = _open(ready, lang)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lang"] == lang
    assert body["session_id"]
    # The model is loaded at creation, not on the first chunk: the renderer can
    # only show "model unavailable" for the call it is still waiting on.
    assert len(fake_vosk.model_paths) == 1


def test_an_unsupported_language_cannot_open_a_session(ready):
    response = _open(ready, "de")
    assert response.status_code == 400
    assert response.json()["detail"] == "stt_bad_lang"


def test_a_missing_model_directory_refuses_the_session_with_503(client, fake_vosk, tmp_path, monkeypatch):
    monkeypatch.setenv("GAMACHINE_VOSK_MODELS_DIR", str(tmp_path / "nothing-here"))
    response = _open(client)
    assert response.status_code == 503
    assert response.json()["detail"] == "stt_model_missing"


def test_a_model_that_refuses_to_load_refuses_the_session_with_503(client, tmp_path, monkeypatch):
    _install_models(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "vosk", _FakeVosk(model_error=RuntimeError("boom")))
    response = _open(client)
    assert response.status_code == 503
    assert response.json()["detail"] == "stt_model_load_failed"


def test_a_fifth_concurrent_session_is_refused_and_a_finish_frees_the_slot(ready):
    """MAX_SESSIONS is a memory bound: each live session holds a recogniser."""
    ids = [_new_session(ready) for _ in range(stt_vosk.MAX_SESSIONS)]

    refused = _open(ready)
    assert refused.status_code == 503
    assert refused.json()["detail"] == "stt_busy"

    assert _finish(ready, ids[0]).status_code == 200
    assert _open(ready).status_code == 200, "finishing a session did not free its slot"


# ── Chunks ──────────────────────────────────────────────────────────────────

def test_the_partial_grows_as_chunks_are_fed(ready):
    session_id = _new_session(ready)
    first = _chunk(ready, session_id, b"\x01\x02" * 4000).json()
    second = _chunk(ready, session_id, b"\x01\x02" * 4000).json()
    assert first["partial"] == "w1"
    assert second["partial"] == "w1 w2"


def test_the_reported_byte_count_is_the_session_total_not_the_chunk(ready):
    session_id = _new_session(ready)
    assert _chunk(ready, session_id, b"\x00" * 800).json()["bytes"] == 800
    assert _chunk(ready, session_id, b"\x00" * 400).json()["bytes"] == 1200


def test_the_recogniser_receives_the_exact_pcm_across_chunks(ready, fake_vosk):
    session_id = _new_session(ready)
    first = bytes((i * 7) % 256 for i in range(10000))
    second = bytes((i * 3) % 256 for i in range(2000))
    _chunk(ready, session_id, first)
    _chunk(ready, session_id, second)
    rec = fake_vosk.recognizers[0]
    assert b"".join(rec.chunks) == first + second
    assert [len(c) for c in rec.chunks] == [8000, 2000, 2000]


def test_an_oversized_base64_string_is_refused_before_it_is_decoded(ready):
    """The precheck is the whole point: a hostile 50 MB body must never be
    materialised as bytes. The string below is not valid base64 at all, so a
    400 here would prove the decoder ran first."""
    session_id = _new_session(ready)
    response = _chunk(ready, session_id, pcm_base64="!" * (MAX_CHUNK_B64_CHARS + 4))
    assert response.status_code == 413
    assert response.json()["detail"] == "stt_too_large"


def test_a_chunk_over_the_per_chunk_cap_is_refused(ready):
    session_id = _new_session(ready)
    payload = base64.b64encode(b"\x00" * (MAX_CHUNK_BYTES + 2)).decode("ascii")
    assert len(payload) <= MAX_CHUNK_B64_CHARS, "this body must pass the string precheck"
    response = _chunk(ready, session_id, pcm_base64=payload)
    assert response.status_code == 413
    assert response.json()["detail"] == "stt_too_large"


def test_the_session_total_cap_refuses_the_chunk_but_keeps_the_session(ready):
    session_id = _new_session(ready)
    block = b"\x00" * MAX_CHUNK_BYTES
    for _ in range(MAX_SESSION_BYTES // MAX_CHUNK_BYTES):
        assert _chunk(ready, session_id, block).status_code == 200

    response = _chunk(ready, session_id, block)
    assert response.status_code == 413
    assert response.json()["detail"] == "stt_too_large"
    # Alive on purpose: the caller still has to collect what was already said.
    assert _finish(ready, session_id).status_code == 200


def test_an_odd_byte_count_is_rejected(ready):
    """Half a 16-bit sample; vosk would reinterpret every following byte."""
    session_id = _new_session(ready)
    response = _chunk(ready, session_id, b"\x01\x02\x03")
    assert response.status_code == 400
    assert response.json()["detail"] == "stt_wrong_format"


def test_a_chunk_that_is_not_base64_is_rejected(ready):
    session_id = _new_session(ready)
    response = _chunk(ready, session_id, pcm_base64="not base64 !!!")
    assert response.status_code == 400
    assert response.json()["detail"] == "stt_bad_base64"


def test_an_empty_chunk_is_a_keep_alive_that_returns_the_current_partial(ready, fake_vosk):
    session_id = _new_session(ready)
    _chunk(ready, session_id, b"\x01\x02" * 4000)
    response = _chunk(ready, session_id, b"")
    assert response.status_code == 200
    body = response.json()
    assert body["partial"] == "w1"
    assert body["bytes"] == 8000
    assert len(fake_vosk.recognizers[0].chunks) == 1, "an empty chunk reached the recogniser"


def test_an_empty_chunk_refreshes_the_idle_timer(ready, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(stt_vosk, "_now", clock)
    session_id = _new_session(ready)
    clock.value += stt_vosk.SESSION_TTL_S - 1
    assert _chunk(ready, session_id, b"").status_code == 200
    clock.value += stt_vosk.SESSION_TTL_S - 1
    assert _chunk(ready, session_id, b"").status_code == 200


def test_a_chunk_for_an_unknown_session_is_a_404(ready):
    response = _chunk(ready, "Zm9vYmFyMTIzNDU2", b"\x00\x00")
    assert response.status_code == 404
    assert response.json()["detail"] == "stt_no_session"


def test_a_session_id_outside_the_token_alphabet_is_a_404_not_a_lookup(ready):
    response = _chunk(ready, "a.b/../etc", b"\x00\x00")
    assert response.status_code == 404


# ── Finish ──────────────────────────────────────────────────────────────────

def test_finish_returns_the_final_text_and_the_duration_of_the_audio(ready):
    session_id = _new_session(ready)
    _chunk(ready, session_id, b"\x01\x02" * 16000)      # 32000 bytes = 1 s at 16 kHz
    response = _finish(ready, session_id)
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "merhaba dunya"
    assert body["duration_ms"] == 1000


def test_the_session_is_gone_after_finish(ready):
    session_id = _new_session(ready)
    assert _finish(ready, session_id).status_code == 200
    assert _chunk(ready, session_id, b"\x00\x00").status_code == 404
    second = _finish(ready, session_id)
    assert second.status_code == 404
    assert second.json()["detail"] == "stt_no_session"


def test_a_discarded_session_is_dropped_without_a_recognition(ready, fake_vosk):
    """A cancelled dictation must not pay for a result nobody will read."""
    session_id = _new_session(ready)
    _chunk(ready, session_id, b"\x01\x02" * 4000)
    response = _finish(ready, session_id, discard=True)
    assert response.status_code == 200
    assert response.json() == {"text": "", "duration_ms": 0}
    assert fake_vosk.recognizers[0].final_calls == 0
    assert _chunk(ready, session_id, b"\x00\x00").status_code == 404


def test_finish_on_an_unknown_session_is_a_404(ready):
    response = _finish(ready, "Zm9vYmFyMTIzNDU2")
    assert response.status_code == 404
    assert response.json()["detail"] == "stt_no_session"


# ── Idle TTL ────────────────────────────────────────────────────────────────

class _Clock:
    """A monotonic clock the test moves by hand."""

    def __init__(self, start=1000.0):
        self.value = start

    def __call__(self):
        return self.value


def test_an_abandoned_session_expires_after_the_idle_ttl(ready, monkeypatch):
    """A renderer that crashes mid-dictation never sends finish; without the TTL
    its recogniser would hold a MAX_SESSIONS slot until the backend restarts."""
    clock = _Clock()
    monkeypatch.setattr(stt_vosk, "_now", clock)
    session_id = _new_session(ready)

    clock.value += stt_vosk.SESSION_TTL_S - 1
    assert _chunk(ready, session_id, b"\x00\x00").status_code == 200

    clock.value += stt_vosk.SESSION_TTL_S + 1
    expired = _chunk(ready, session_id, b"\x00\x00")
    assert expired.status_code == 404
    assert expired.json()["detail"] == "stt_no_session"


def test_expiry_frees_the_slot_of_a_session_nobody_finished(ready, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(stt_vosk, "_now", clock)
    for _ in range(stt_vosk.MAX_SESSIONS):
        _new_session(ready)
    assert _open(ready).status_code == 503

    clock.value += stt_vosk.SESSION_TTL_S + 1
    assert _open(ready).status_code == 200


# ── Serialisation ───────────────────────────────────────────────────────────

def test_chunks_of_one_session_never_reach_the_recogniser_concurrently(ready, fake_vosk):
    """vosk's recogniser is not reentrant: two overlapping AcceptWaveform calls
    corrupt the decoder state rather than raising."""
    session_id = _new_session(ready)
    rec = fake_vosk.recognizers[0]
    rec.block_delay = 0.01

    errors = []

    def send(byte):
        try:
            assert _chunk(ready, session_id, bytes([byte, byte]) * 4000).status_code == 200
        except Exception as exc:                     # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=send, args=(i,)) for i in (1, 2, 3, 4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    assert not rec.overlapped, "two chunks were inside AcceptWaveform at the same time"
    assert len(rec.chunks) == 4
    # Each request's audio is one 8000-byte block, so no chunk may be interleaved
    # with another: every block is a single repeated byte.
    for block in rec.chunks:
        assert len(set(block)) == 1


# ── The gate ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/transcribe/session",
    "/transcribe/session/abc",
    "/transcribe/session/abc/finish",
])
def test_every_session_route_requires_the_session_token_header(ready, path):
    """The header is declared without a default, so its absence is a 422 from
    FastAPI's own validation — the handler body never runs. The authz matrix
    checks the same three routes against the real gate."""
    assert ready.post(path, json={"lang": "tr", "pcm_base64": ""}).status_code == 422
