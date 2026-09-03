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
        # 1-based AcceptWaveform call number to raise on, or None to never raise.
        self.raise_on_block = None
        self.raise_on_partial = False

    def AcceptWaveform(self, data):
        if self.inside:
            self.overlapped = True
        self.inside = True
        try:
            if self.block_delay:
                time.sleep(self.block_delay)
            if self.raise_on_block is not None and len(self.chunks) + 1 == self.raise_on_block:
                raise RuntimeError("recognizer refused this block")
            self.chunks.append(data)
        finally:
            self.inside = False
        return False

    def PartialResult(self):
        if self.raise_on_partial:
            raise RuntimeError("recognizer refused to report a partial")
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
    # `raise_server_exceptions=False` matches what a real HTTP client sees (a
    # 500 response) rather than the test client's default of re-raising —
    # needed to assert on the response a recognizer exception produces, not
    # just to observe the exception itself.
    return TestClient(app, raise_server_exceptions=False)


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


def test_two_concurrent_boundary_chunks_cannot_both_pass_the_session_cap(ready, fake_vosk):
    """Audit finding, 3 Sep 2026: the cap used to be read (`session_bytes`) and
    the total incremented (inside `feed`) in two separate critical sections, so
    two chunks arriving at once could both read the same stale total and push
    the session two bytes past the 2 MiB cap together. The recogniser's own
    delay is what makes two real HTTP requests actually overlap in time; a
    unit-level race needs no delay because it drives `feed` directly, but this
    is the route's own admission check, so the overlap has to be real."""
    session_id = _new_session(ready)
    fake_vosk.recognizers[0].block_delay = 0.05
    block = b"\x00" * MAX_CHUNK_BYTES
    for _ in range((MAX_SESSION_BYTES - 2) // MAX_CHUNK_BYTES):
        assert _chunk(ready, session_id, block).status_code == 200
    remainder = (MAX_SESSION_BYTES - 2) % MAX_CHUNK_BYTES
    if remainder:
        assert _chunk(ready, session_id, block[:remainder]).status_code == 200

    responses = []

    def send():
        responses.append(_chunk(ready, session_id, b"\x00\x00"))

    threads = [threading.Thread(target=send) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert len(responses) == 2
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 413], [r.text for r in responses]
    admitted = next(r for r in responses if r.status_code == 200)
    assert admitted.json()["bytes"] == MAX_SESSION_BYTES


def test_a_mid_chunk_recognizer_failure_poisons_the_session_instead_of_leaving_it_resendable(ready, fake_vosk):
    """Audit finding, 3 Sep 2026: `AcceptWaveform` raising on a later 8000-byte
    slice used to leave the recogniser having consumed an earlier slice while
    `total_bytes` stayed at its pre-call value — a retry of the same chunk
    would re-feed the already-consumed prefix into the transcript. The session
    is now dropped on any feed exception, so a retry gets an honest 404
    instead of a silent duplicate."""
    session_id = _new_session(ready)
    fake_vosk.recognizers[0].raise_on_block = 2   # the second 8000-byte slice
    two_blocks = b"\x00" * 16000
    response = _chunk(ready, session_id, two_blocks)
    assert response.status_code == 500
    assert len(fake_vosk.recognizers[0].chunks) == 1  # the first slice was consumed

    retry = _chunk(ready, session_id, two_blocks)
    assert retry.status_code == 404
    assert retry.json()["detail"] == "stt_no_session"


def test_a_partial_result_failure_poisons_the_session_instead_of_leaving_it_resendable(ready, fake_vosk):
    """Same class, the other trigger: `PartialResult` raising AFTER
    `total_bytes` was already incremented for the accepted chunk. Without the
    fix a retry of that same chunk would be accepted a second time, feeding it
    to the recogniser twice."""
    session_id = _new_session(ready)
    fake_vosk.recognizers[0].raise_on_partial = True
    one_block = b"\x00" * 8000
    response = _chunk(ready, session_id, one_block)
    assert response.status_code == 500
    assert len(fake_vosk.recognizers[0].chunks) == 1

    retry = _chunk(ready, session_id, one_block)
    assert retry.status_code == 404
    assert retry.json()["detail"] == "stt_no_session"


def test_a_feed_blocked_on_the_lock_is_rejected_after_the_session_is_poisoned(ready, fake_vosk):
    """Verification round, 3 Sep 2026: the poisoning fix above only stops a
    FUTURE `_get()` call from finding the dropped session. A caller that
    already obtained the `_Session` object and is blocked waiting for
    `session.lock` when the poisoning happens used to go on to feed the
    now-detached recognizer anyway — measured: it raised a SECOND, unrelated
    exception of its own. `feed()` now re-checks registry membership by
    identity once it holds the lock."""
    session_id = _new_session(ready)
    rec = fake_vosk.recognizers[0]
    rec.block_delay = 0.05
    rec.raise_on_block = 2   # the second 8000-byte slice of A's chunk

    errors = []

    def poison():
        try:
            stt_vosk.feed(session_id, b"\x00" * 16000)
        except Exception as exc:                      # noqa: BLE001
            errors.append(("A", exc))

    def blocked():
        try:
            stt_vosk.feed(session_id, b"\x00" * 8000)
        except Exception as exc:                       # noqa: BLE001
            errors.append(("B", exc))

    a = threading.Thread(target=poison)
    b = threading.Thread(target=blocked)
    a.start()
    time.sleep(0.02)   # let A acquire session.lock before B calls _get()
    b.start()
    a.join(timeout=5)
    b.join(timeout=5)

    kinds = {who: type(exc).__name__ for who, exc in errors}
    assert kinds.get("A") == "RuntimeError"        # A's own recognizer failure
    assert kinds.get("B") == "SttNoSession"        # not a second RuntimeError
    assert session_id not in stt_vosk._sessions


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


def test_an_empty_session_id_never_reaches_the_registry(ready):
    """Audit finding, 3 Sep 2026, demoted: a raw slash or an empty id are not
    valid path segments, so Starlette answers them itself -- a generic 404 for
    the slash (already covered above) and a 307 redirect toward the session
    CREATE route for the empty one, before either reaches `_SESSION_ID_RE` or
    the registry. Neither form ever names or mutates a live session; this
    pins the current (not the ideal) status codes so a future change to it is
    visible rather than silent. `follow_redirects=False`: the redirect target
    expects `{lang}`, not `{pcm_base64}`, and following it would just measure
    a second, unrelated 422 from the create route."""
    response = ready.post(
        "/transcribe/session/",
        json={"pcm_base64": ""},
        headers=HEADERS,
        follow_redirects=False,
    )
    assert response.status_code == 307


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


@pytest.mark.parametrize("value", [1, "yes"])
def test_a_non_boolean_discard_value_is_rejected_not_coerced(ready, value):
    """Audit finding, 3 Sep 2026: plain `bool` coerces `1` and `"yes"` to True,
    so a stray non-boolean value silently discarded a dictation instead of
    being refused. `StrictBool` turns both into a 422 instead."""
    session_id = _new_session(ready)
    response = _finish(ready, session_id, discard=value)
    assert response.status_code == 422
    # The session is untouched by the refused request.
    assert _chunk(ready, session_id, b"\x00\x00").status_code == 200


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
