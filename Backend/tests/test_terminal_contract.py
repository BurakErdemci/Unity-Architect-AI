"""Bir tur TEK sonlanma olayıyla biter — ve kesilen tur işini kaybetmez.

Sözleşme: her tur ya bir `done` (içinde `stop_reason`) ya da bir `error` yollar.
Ne sıfır, ne iki. 30 Ağu 2026 denetimi bu sözleşmenin üç ayrı yerde tutmadığını
kanıtla gösterdi; buradaki testler o üç yerin karşılığı.

1. `ClaudeSDKSession._finish_turn(error=...)` hem `error` hem `done` kuyruğa
   koyuyordu. `_normalize_session_event` `done`'a varsayılan
   `stop_reason="complete"` damgasını vurduğu için aktarım hatası arayüze
   "hem çöktü hem başarıyla bitti" diye ulaşıyordu.
2. `/chat-stream` cevabı DB'ye yazarken patlarsa, `done` çoktan gitmişken
   dıştaki `except` ikinci bir `error` yolluyordu.
3. Kesilen turda (tavan, ilerleme sigortası) ekranda akan iş DB'ye HİÇ
   yazılmıyordu: kullanıcı çalışmayı görüyor, konuşmayı tekrar açınca yalnız
   uyarı satırını buluyordu.

Üçüncüsü sözleşme ihlali değil veri kaybı, ama aynı yerde yaşıyor: sonlanma
olayını üreten kod ile turu kaydeden kod aynı fonksiyonda.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import agentic.agent_runner as ar
from routes.conversation_routes import create_conversation_router, _TurnRecord


def _sse_types(body: str) -> "list[str]":
    """SSE gövdesindeki olay tiplerini sırayla döndürür."""
    import json
    out = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            out.append(json.loads(line[6:]).get("type"))
        except Exception:
            pass
    return out


def _client(runner_cls, db=None):
    db = db or MagicMock()
    db.get_ai_config.return_value = ("claude", "claude-opus-5", None, None)
    db.get_api_key.return_value = ""
    db.get_last_workspace.return_value = ""
    db.get_memory.return_value = ""
    db.get_conversation_messages.return_value = []
    app = FastAPI()
    app.include_router(create_conversation_router(db, {}))
    return db, app, patch("routes.conversation_routes.AgentRunner", runner_cls)


def _fail_only_assistant_writes():
    def _yaz(conv_id, role, content, *a, **kw):
        if role == "assistant":
            raise RuntimeError("disk dolu")
        return None
    return _yaz


def _post(app):
    with TestClient(app) as client:
        return client.post("/chat-stream",
                           json={"conversation_id": 1, "user_id": 1, "message": "selam"},
                           headers={"X-Session-Token": ""})


# ── 1. Oturum hata yolu ──────────────────────────────────────────────────
def test_the_session_error_path_queues_one_terminal_not_two():
    from providers.claude_sdk_session import ClaudeSDKSession

    sess = ClaudeSDKSession.__new__(ClaudeSDKSession)
    q: asyncio.Queue = asyncio.Queue()
    sess._turn_active = True
    sess._result_pending = False
    sess._out_q = q
    sess._usage_event = None
    sess._final_text = "yarım cevap"
    sess._last_result_text = ""
    sess.session_id = "s1"
    sess.conversation_id = 1
    sess._cancel_grace = lambda: None
    sess._flush_deltas = _noop

    asyncio.run(sess._finish_turn(error="aktarım koptu"))

    tipler = _drain(q)
    assert tipler.count("done") == 0, f"hata yolunda done da gitti: {tipler}"
    assert tipler.count("error") == 1, f"tam bir error bekleniyordu: {tipler}"


def test_the_session_error_path_still_delivers_the_partial_text():
    """Sonlanmayı tekilleştirmek İÇERİĞİ düşürmemeli — yoksa raporlama
    hatasını veri kaybına çevirmiş oluruz."""
    from providers.claude_sdk_session import ClaudeSDKSession

    sess = ClaudeSDKSession.__new__(ClaudeSDKSession)
    q: asyncio.Queue = asyncio.Queue()
    sess._turn_active = True
    sess._result_pending = False
    sess._out_q = q
    sess._usage_event = None
    sess._final_text = "yarım cevap"
    sess._last_result_text = ""
    sess.session_id = "s1"
    sess.conversation_id = 1
    sess._cancel_grace = lambda: None
    sess._flush_deltas = _noop

    asyncio.run(sess._finish_turn(error="aktarım koptu"))
    assert "response" in _drain(q)


def test_the_session_success_path_still_sends_done():
    """Kapının ters yönü: başarılı tur hâlâ tam olarak bir `done` yolluyor."""
    from providers.claude_sdk_session import ClaudeSDKSession

    sess = ClaudeSDKSession.__new__(ClaudeSDKSession)
    q: asyncio.Queue = asyncio.Queue()
    sess._turn_active = True
    sess._result_pending = False
    sess._out_q = q
    sess._usage_event = None
    sess._final_text = "tam cevap"
    sess._last_result_text = ""
    sess.session_id = "s1"
    sess.conversation_id = 1
    sess._cancel_grace = lambda: None
    sess._flush_deltas = _noop

    asyncio.run(sess._finish_turn())
    tipler = _drain(q)
    assert tipler.count("done") == 1 and "error" not in tipler, tipler


async def _noop():
    return None


def _drain(q: asyncio.Queue) -> "list[str]":
    out = []
    while not q.empty():
        ev = q.get_nowait()
        if ev is None:
            break
        out.append(ev.get("type"))
    return out


# ── 2. Kayıt hatası ikinci terminal üretmiyor ────────────────────────────
class _NormalRunner:
    def __init__(self, **kw):
        pass

    async def run(self, message):
        yield ar.AgentEvent("response", {"content": "cevap"})
        yield ar.AgentEvent("done", {"iterations": 1, "stop_reason": "complete"})


def test_a_failing_turn_write_does_not_append_a_second_terminal():
    db, app, p = _client(_NormalRunner)
    # YALNIZ asistan yazımı düşsün: `add_message` kullanıcı mesajı için de
    # çağrılıyor ve o çağrı akıştan ÖNCE, yani hepsini düşürmek turu hiç
    # başlatmazdı — sınamak istediğimiz dal da hiç koşmazdı.
    db.add_message.side_effect = _fail_only_assistant_writes()
    with p:
        body = _post(app).text
    tipler = _sse_types(body)
    assert tipler.count("done") == 1, tipler
    assert "error" not in tipler, f"done'dan sonra ikinci terminal gitti: {tipler}"


def test_a_failing_turn_write_is_still_told_to_the_user():
    """Sessizlik de kabul değil: cevap ekranda ama kaydedilmedi, kullanıcı
    bunu bilmeli. `warning` terminal olmadığı için sözleşmeyi bozmuyor."""
    db, app, p = _client(_NormalRunner)
    # YALNIZ asistan yazımı düşsün: `add_message` kullanıcı mesajı için de
    # çağrılıyor ve o çağrı akıştan ÖNCE, yani hepsini düşürmek turu hiç
    # başlatmazdı — sınamak istediğimiz dal da hiç koşmazdı.
    db.add_message.side_effect = _fail_only_assistant_writes()
    with p:
        body = _post(app).text
    assert "turn_not_saved" in body
    assert "warning" in _sse_types(body)


def test_a_healthy_turn_emits_no_warning():
    # Kapının ters yönü: uyarı yalnız gerçekten kaydedilemeyince çıkmalı.
    db, app, p = _client(_NormalRunner)
    with p:
        body = _post(app).text
    assert "turn_not_saved" not in body
    assert db.add_message.called


# ── 3. Kesilen turun akan işi kayboluyor mu ──────────────────────────────
class _StoppedRunner:
    """Tavana çarpan tur: `text` akıyor, `response` HİÇ gelmiyor."""

    def __init__(self, **kw):
        pass

    async def run(self, message):
        yield ar.AgentEvent("text", {"content": "birinci adım tamam"})
        yield ar.AgentEvent("text", {"content": "ikinci adım tamam"})
        yield ar.AgentEvent("done", {"iterations": 300, "stop_reason": "max_iterations",
                                     "stop_message": "Koşum durduruldu."})


def test_a_hard_stopped_turn_keeps_the_work_it_streamed():
    db, app, p = _client(_StoppedRunner)
    with p:
        _post(app)
    assert db.add_message.called, "kesilen tur hiç kaydedilmedi"
    kayitli = db.add_message.call_args[0][2]
    assert "birinci adım tamam" in kayitli
    assert "ikinci adım tamam" in kayitli
    assert "Koşum durduruldu." in kayitli, "durma sebebi de kalmalı"


def test_a_normal_turn_does_not_store_its_answer_twice():
    """`text` biriktirmenin bedeli tam olarak burada ölçülür: normal turda
    cevap hem akar hem `response` ile gelir; ikisini de saymak cevabı iki kez
    kaydederdi."""

    class _EchoRunner:
        def __init__(self, **kw):
            pass

        async def run(self, message):
            yield ar.AgentEvent("text", {"content": "merhaba"})
            yield ar.AgentEvent("response", {"content": "merhaba"})
            yield ar.AgentEvent("done", {"iterations": 1, "stop_reason": "complete"})

    db, app, p = _client(_EchoRunner)
    with p:
        _post(app)
    kayitli = db.add_message.call_args[0][2]
    assert kayitli.count("merhaba") == 1, f"cevap iki kez kaydedildi: {kayitli!r}"


# ── Biriktiricinin kendi sözleşmesi ──────────────────────────────────────
def test_the_record_prefers_response_over_streamed_text():
    r = _TurnRecord()
    r.add(ar.AgentEvent("text", {"content": "akan"}))
    r.add(ar.AgentEvent("response", {"content": "nihai"}))
    assert r.value() == "nihai"


def test_the_record_falls_back_to_streamed_text_without_a_response():
    r = _TurnRecord()
    r.add(ar.AgentEvent("text", {"content": "akan"}))
    r.add(ar.AgentEvent("done", {"stop_message": "durdu"}))
    assert "akan" in r.value() and "durdu" in r.value()


def test_the_record_stays_empty_when_nothing_was_produced():
    r = _TurnRecord()
    r.add(ar.AgentEvent("done", {"stop_reason": "complete"}))
    assert r.value() == ""
