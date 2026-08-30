"""`/session-report` ucu — ve ucun GERÇEKTEN çağrılabildiği.

Bu dosya bir arızadan doğdu (30 Ağu 2026, sahada): uç `get_current_user`
çağırıyordu ama o ad bu modülde import EDİLMEMİŞTİ. Sonuç her istekte
`NameError` → HTTP 500.

Yakalanamamasının sebebi kayda değer: ucun ÇAĞIRANI için 10 test yazılmıştı
(arayüz paneli, `fetch` sahtesiyle), ÇAĞRILANI için sıfır. Sahte cevap veren
bir istemci testi, sunucunun import satırını hiç çalıştırmıyor. Panel testleri
yeşildi ve özellik tamamen kırıktı.

Buradaki testler bu yüzden route fonksiyonunu DOĞRUDAN koşturuyor.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from routes.conversation_routes import create_conversation_router


def _db(provider="subscription", model="claude-opus-5"):
    db = MagicMock()
    db.get_ai_config.return_value = (provider, model, "", False)
    return db


def _cagir(kind: str, db=None):
    router = create_conversation_router(db or _db(), MagicMock())
    route = next(r for r in router.routes
                 if getattr(r, "path", "") == "/session-report/{conv_id}/{kind}")
    return asyncio.run(route.endpoint(conv_id=1, kind=kind, x_session_token="t"))


def test_the_endpoint_is_actually_callable():
    # Bu dosyanın var olma sebebi: eksik bir import bu satırda NameError
    # veriyordu ve hiçbir test oraya kadar gitmiyordu.
    with patch("providers.claude_sdk_session.peek_session", return_value=None):
        sonuc = _cagir("context")
    assert sonuc["status"] in ("no_session", "unsupported", "busy", "ok", "error")


def test_an_unknown_kind_is_rejected():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _cagir("kullanim")
    assert e.value.status_code == 400


def test_no_live_session_is_reported_as_such_and_no_session_is_created():
    # Rapor isteyen bir uç, raporlayacağı süreci VAR ETMEMELİ.
    with patch("providers.claude_sdk_session.peek_session", return_value=None) as peek, \
         patch("providers.claude_sdk_session.get_session") as get:
        assert _cagir("context")["status"] == "no_session"
    peek.assert_called_once()
    get.assert_not_called()


def test_a_running_turn_is_busy_rather_than_a_ten_second_wait():
    sess = MagicMock()
    with patch("providers.claude_sdk_session.peek_session", return_value=sess), \
         patch("providers.claude_sdk_session.session_busy", return_value=True):
        assert _cagir("context")["status"] == "busy"
    # Meşgulken oturuma HİÇ mesaj gitmemeli.
    sess.stream.assert_not_called()


def test_a_cloud_provider_has_no_such_report():
    assert _cagir("usage", _db(provider="anthropic"))["status"] == "unsupported"


def test_codex_has_usage_but_not_context():
    db = _db(model="gpt-5.6-sol")
    assert _cagir("context", db) == {"status": "unsupported", "reason": "codex_no_context"}


def test_codex_usage_comes_from_the_zero_token_path():
    db = _db(model="gpt-5.6-sol")
    sess = MagicMock()

    async def _kart():
        return "50% used"
    sess.usage_card_text.side_effect = _kart
    with patch("providers.codex_session.peek_session", return_value=sess):
        sonuc = _cagir("usage", db)
    assert sonuc == {"status": "ok", "kind": "usage", "text": "50% used"}


def test_agy_is_unsupported_rather_than_silently_empty():
    assert _cagir("usage", _db(model="gemini-3.6-flash"))["status"] == "unsupported"


def test_claude_report_text_is_collected_from_the_stream():
    sess = MagicMock()

    async def _akis(mesaj):
        assert mesaj == "/context"
        for ev in [{"type": "text", "content": "**Tokens:** "},
                   {"type": "text", "content": "69.9k / 1m (7%)"},
                   {"type": "done"}]:
            yield ev
    sess.stream = _akis
    with patch("providers.claude_sdk_session.peek_session", return_value=sess), \
         patch("providers.claude_sdk_session.session_busy", return_value=False):
        sonuc = _cagir("context")
    assert sonuc["status"] == "ok"
    assert sonuc["text"] == "**Tokens:** 69.9k / 1m (7%)"


def test_a_failing_stream_is_an_error_not_a_crash():
    sess = MagicMock()

    async def _akis(_m):
        raise RuntimeError("kopuk")
        yield  # pragma: no cover
    sess.stream = _akis
    with patch("providers.claude_sdk_session.peek_session", return_value=sess), \
         patch("providers.claude_sdk_session.session_busy", return_value=False):
        assert _cagir("context")["status"] == "error"
