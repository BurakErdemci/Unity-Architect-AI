"""`/session-report` ucu — ve ucun GERÇEKTEN çağrılabildiği.

Bu dosya bir arızadan doğdu (30 Ağu 2026, sahada): uç `get_current_user`
çağırıyordu ama o ad bu modülde import EDİLMEMİŞTİ. Sonuç her istekte
`NameError` → HTTP 500.

Yakalanamamasının sebebi kayda değer: ucun ÇAĞIRANI için 10 test yazılmıştı
(arayüz paneli, `fetch` sahtesiyle), ÇAĞRILANI için sıfır. Sahte cevap veren
bir istemci testi, sunucunun import satırını hiç çalıştırmıyor. Panel testleri
yeşildi ve özellik tamamen kırıktı.

Buradaki testler bu yüzden route fonksiyonunu DOĞRUDAN koşturuyor.

İKİNCİ TUR (dış denetim, 30 Ağu 2026)
Bu dosyanın ilk hâli yeşildi ve uç üç ayrı yerden kırıktı. Sebep tek bir kalıp:
testler tam da düşen DURUMLARI yamayıp yerine geçiyordu — `peek_session` zorla
`None`, `session_busy` zorla `True`. Yamanan bir durum sınanmamış bir durumdur.
Aşağıdaki üç test bu yüzden GERÇEK oturum nesneleriyle ve gerçek kilitle
koşuyor; adlarının sonunda hangi arızadan doğdukları yazılı.
"""
import asyncio
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from routes.conversation_routes import create_conversation_router


def _db(provider="subscription", model="claude-opus-5", mesajlar=None):
    db = MagicMock()
    db.get_ai_config.return_value = (provider, model, "", False)
    # Stored messages are what the context fallback counts. Left EMPTY by
    # default so a test that does not set them measures the "no data at all"
    # branch rather than silently inheriting an estimate.
    db.get_conversation_messages.return_value = mesajlar or []
    return db


@pytest.fixture(autouse=True)
def _kullanim_cachei_temiz():
    """The usage cache is module-global and OUTLIVES a test.

    Without this, a cached "50% used" from an earlier test answers a later
    test's "no session" case as a stale `ok` — the later test then measures the
    leak, not the endpoint.
    """
    from routes import conversation_routes as cr
    cr._USAGE_CACHE.clear()
    yield
    cr._USAGE_CACHE.clear()


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
    assert sonuc["status"] == "no_data"


def test_an_unknown_kind_is_rejected():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _cagir("kullanim")
    assert e.value.status_code == 400


def test_no_live_session_is_reported_as_such_and_no_session_is_created():
    # Rapor isteyen bir uç, raporlayacağı süreci VAR ETMEMELİ.
    with patch("providers.claude_sdk_session.peek_session", return_value=None) as peek, \
         patch("providers.claude_sdk_session.get_session") as get:
        sonuc = _cagir("context")
    # Nothing stored either, so the fallback has nothing to offer and the reason
    # still names the real cause.
    assert sonuc == {"status": "no_data", "kind": "context", "reason": "no_session"}
    peek.assert_called_once()
    get.assert_not_called()


def test_a_running_turn_is_busy_rather_than_a_ten_second_wait():
    sess = MagicMock()
    with patch("providers.claude_sdk_session.peek_session", return_value=sess), \
         patch("providers.claude_sdk_session.session_busy", return_value=True):
        assert _cagir("context")["reason"] == "busy"
    # Meşgulken oturuma HİÇ mesaj gitmemeli.
    sess.stream.assert_not_called()


def test_a_cloud_provider_has_no_such_report():
    assert _cagir("usage", _db(provider="anthropic"))["status"] == "unsupported"


def test_codex_has_usage_but_not_context():
    db = _db(model="gpt-5.6-sol")
    assert _cagir("context", db) == {"status": "no_data", "kind": "context",
                                     "reason": "codex_no_context"}


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

    async def _akis(mesaj, lock_timeout=10.0):
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

    async def _akis(_m, lock_timeout=10.0):
        raise RuntimeError("kopuk")
        yield  # pragma: no cover
    sess.stream = _akis
    with patch("providers.claude_sdk_session.peek_session", return_value=sess), \
         patch("providers.claude_sdk_session.session_busy", return_value=False):
        assert _cagir("context")["reason"] == "error"


# ── Denetim turu: cache'te DURAN ama BAŞLAMAMIŞ oturum ──────────────────────
# Bu testler bir kalıbı kırıyor: yukarıdaki eski testler `peek_session`ı `None`
# döndürmeye zorluyordu, yani "nesne var ama süreç yok" durumu HİÇ kurulmuyordu.
# Gerçek nesneler kullanılıyor, yalnız süreç doğuran `start()` bir sayaçla
# değiştiriliyor — çağrılırsa test kırılır.

def test_a_cached_but_unstarted_claude_session_is_no_session_not_a_new_process():
    from providers.claude_sdk_session import ClaudeSDKSession

    sess = ClaudeSDKSession(1)
    baslatildi: list[str] = []

    async def _sahte_start():
        baslatildi.append("start")
        sess._started = True

    sess.start = _sahte_start
    assert sess.is_live is False, "kurulmuş ama başlamamış nesne canlı sayılmamalı"
    with patch("providers.claude_sdk_session.peek_session", return_value=sess), \
         patch("providers.claude_sdk_session.session_busy", return_value=False):
        assert _cagir("usage")["status"] == "no_session"
    # Asıl iddia: salt-okunur bir GET, raporlayacağı SÜRECİ var etmedi.
    assert baslatildi == [], "GET Claude CLI transport'unu başlattı"


def test_a_cached_but_unstarted_codex_session_is_no_session_not_a_new_process():
    from providers.codex_session import CodexSession

    sess = CodexSession(1)
    baslatildi: list[str] = []

    async def _sahte_start():
        baslatildi.append("start")
        sess._started = True

    sess.start = _sahte_start
    assert sess.is_live is False
    with patch("providers.codex_session.peek_session", return_value=sess):
        assert _cagir("usage", _db(model="gpt-5.6-sol"))["status"] == "no_session"
    assert baslatildi == [], "GET codex app-server sürecini başlattı"


def test_both_providers_peek_hide_a_session_whose_process_is_gone():
    """İki `peek_session` AYNI ölçütü kullanmalı.

    Denetimin bulduğu asimetri: Claude tarafı kopuk oturumu eliyordu, Codex
    tarafı hiçbir şey elemiyordu — yani aynı uç, sağlayıcıya göre farklı
    davranıyordu.
    """
    from providers import claude_sdk_session as c
    from providers import codex_session as x

    claude = c.ClaudeSDKSession(4242)
    claude._started = True
    codex = x.CodexSession(4242)
    codex._started = True
    with patch.dict(c._SESSIONS, {4242: claude}, clear=False), \
         patch.dict(x._SESSIONS, {4242: codex}, clear=False):
        assert c.peek_session(4242) is claude
        assert x.peek_session(4242) is codex
        # Claude: reader öldü. Codex: okuma döngüsü süreç ölünce _started'ı düşürür.
        claude._broken = True
        codex._started = False
        assert c.peek_session(4242) is None
        assert x.peek_session(4242) is None


# ── Denetim turu: sağlayıcı yönlendirmesi ──────────────────────────────────

@pytest.mark.parametrize("model", ["kimi-k3", "copilot-auto", "cursor-auto", "opencode:auto"])
def test_a_non_claude_subscription_model_never_reads_a_stale_claude_session(model):
    """Kimi/Copilot/Cursor/OpenCode seçiliyken rapor `unsupported` olmalı.

    Arıza (denetim, 30 Ağu 2026): yönlendirme "gpt- değil, gemini değil, agy-
    değil → Claude" diyordu. Kullanıcı sohbeti Claude'dan bu ailelerden birine
    çevirdiğinde eski Claude oturumu cache'te kalıyor ve uç ONA `/usage`
    gönderip BAŞKA SAĞLAYICININ raporunu `status: ok` ile kullanıcının
    raporuymuş gibi gösteriyordu.
    """
    cagrilar: list[str] = []

    class BayatClaudeOturumu:
        is_live = True

        async def stream(self, mesaj, lock_timeout=10.0):
            cagrilar.append(mesaj)
            yield {"type": "text", "content": "BAYAT CLAUDE RAPORU"}
            yield {"type": "done"}

    with patch("providers.claude_sdk_session.peek_session", return_value=BayatClaudeOturumu()), \
         patch("providers.claude_sdk_session.session_busy", return_value=False):
        sonuc = _cagir("usage", _db(model=model))
    assert sonuc == {"status": "unsupported", "reason": "provider"}
    assert cagrilar == [], "bayat Claude oturumuna mesaj gitti"


def test_an_unrecognised_subscription_model_is_unsupported_rather_than_claude():
    """Tanınmayan ad SESSİZCE Claude'a düşmez.

    `spawn_env.env_family` bilinmeyen adı bilerek "claude"a düşürüyor (alt süreç
    ortamı için doğru karar: en kısıtlı izin listesi). Rapor ucunda aynı düşüş
    başka sağlayıcının raporunu göstermek demek olurdu.
    """
    assert _cagir("usage", _db(model="hicbir-yerde-olmayan-model"))["status"] == "unsupported"


def test_the_report_routing_table_agrees_with_the_real_provider_dispatch():
    """Rapor ailesi ile `AIProviderManager`ın SEÇTİĞİ sağlayıcı sınıfı aynı olmalı.

    Bu deponun tekrar eden arıza şekli "uyuşması gereken iki tablo uyuşmuyor".
    Rapor ucu ikinci bir önek tablosu tutmuyor (`spawn_env.env_family` kullanıyor)
    ama o tablo da manager'dan AYRI bir dosyada duruyor — burada ikisi karşı
    karşıya getiriliyor, yani biri değişip diğeri değişmezse test kırılır.
    """
    from ai_providers import AIProviderManager
    from providers.agy_provider import AgyProvider
    from providers.claude_provider import ClaudeCodeProvider
    from providers.codex_provider import CodexProvider
    from providers.copilot_provider import CopilotProvider
    from providers.cursor_provider import CursorProvider
    from providers.kimi_provider import KimiProvider
    from providers.opencode_provider import OpenCodeProvider
    from routes.conversation_routes import _report_family

    beklenen = {
        "claude-opus-5": ("claude", ClaudeCodeProvider),
        "gpt-5.6-sol": ("codex", CodexProvider),
        "gemini-3.6-flash": ("agy", AgyProvider),
        "agy-pro": ("agy", AgyProvider),
        "cursor-auto": ("cursor", CursorProvider),
        "copilot-auto": ("copilot", CopilotProvider),
        "opencode:auto": ("opencode", OpenCodeProvider),
        "kimi-k3": ("kimi", KimiProvider),
    }
    for model, (aile, sinif) in beklenen.items():
        assert _report_family(model) == aile, f"{model}: rapor ailesi kaydı"
        provider = AIProviderManager.get_provider(
            {"provider_type": "subscription", "model_name": model})
        assert isinstance(provider, sinif), (
            f"{model}: manager {type(provider).__name__} seçiyor ama rapor ucu "
            f"{aile!r} ailesi sanıyor — iki tablo ayrışmış"
        )


# ── Denetim turu: meşgul kontrolü ile kullanımı arasındaki yarış ───────────

def test_a_turn_that_starts_after_the_busy_check_still_answers_busy_immediately():
    """`session_busy()` "boş" dedikten SONRA başlayan bir tur cevabı bekletmemeli.

    Arıza (denetim, 30 Ağu 2026): uç önce `session_busy()` soruyor, sonra
    `stream()`e giriyordu; `stream()` aynı kilidi BAĞIMSIZ olarak 10 saniye
    bekliyor. İki işlem arasında başlayan bir tur "anında busy" vaadini
    yalanlıyor — kullanıcı ya saniyelerce donuyor ya da `error` görüyordu.

    Eski test bunu göremezdi çünkü `session_busy`ı `True` döndürmeye zorluyordu,
    yani pencereyi hiç AÇMIYORDU. Burada kontrol `False` diyor ve hemen ardından
    kilit gerçekten alınıyor.
    """
    from providers.claude_sdk_session import ClaudeSDKSession

    sess = ClaudeSDKSession(1)
    sess._started = True
    sorgular: list[str] = []

    class SahteIstemci:
        async def query(self, mesaj):
            sorgular.append(mesaj)

    sess._client = SahteIstemci()

    def bayat_mesgul_kontrolu(_conv_id):
        # Kontrol anı ile kullanım anı ARASINDA rakip tur kilidi alıyor.
        sess._turn_lock._locked = True
        return False

    baslangic = time.monotonic()
    with patch("providers.claude_sdk_session.peek_session", return_value=sess), \
         patch("providers.claude_sdk_session.session_busy", side_effect=bayat_mesgul_kontrolu):
        sonuc = _cagir("context")
    gecen = time.monotonic() - baslangic

    assert sonuc["reason"] == "busy", f"{sonuc!r} döndü — 'busy' bekleniyordu"
    assert gecen < 1.0, f"cevap {gecen:.2f}s bekledi; anında olmalıydı"
    assert sorgular == [], "meşgul oturuma mesaj gönderildi"


# ── 5 Sep 2026: the panel must not go blank while a turn streams ────────────
# Measured complaint: usage and context both emptied out during a run, and the
# context section never filled in any state. The two tests below fix what the
# endpoint is allowed to answer instead — and the third fixes what it must NOT
# invent.

def _mesajlar(*metinler):
    return [{"content": m} for m in metinler]


def test_usage_survives_a_running_turn_by_serving_the_last_reading_with_its_age():
    """A running turn must not blank the usage section.

    The report is read by sending `/usage` into the live session, and that
    session serialises turns — while a turn runs it is unreachable. The numbers
    are account-level though (quota), so the previous reading is still true; it
    goes out stamped `stale` with its age, never as a fresh reading.
    """
    db = _db()
    sess = MagicMock()

    async def _akis(mesaj, lock_timeout=10.0):
        assert mesaj == "/usage"
        yield {"type": "text", "content": "Current session: 22% used"}
        yield {"type": "done"}

    sess.stream = _akis
    with patch("providers.claude_sdk_session.peek_session", return_value=sess), \
         patch("providers.claude_sdk_session.session_busy", return_value=False):
        taze = _cagir("usage", db)
    assert taze["status"] == "ok" and "22% used" in taze["text"]
    assert "stale" not in taze, "a live reading must not be labelled stale"

    # Now a turn is running: the same session cannot be queried.
    with patch("providers.claude_sdk_session.peek_session", return_value=sess), \
         patch("providers.claude_sdk_session.session_busy", return_value=True):
        mesgul = _cagir("usage", db)
    assert mesgul["status"] == "ok", f"{mesgul!r} — the section went blank again"
    assert mesgul["text"] == taze["text"]
    assert mesgul["stale"] is True and mesgul["reason"] == "busy"
    assert isinstance(mesgul["age_s"], int)


def test_context_falls_back_to_the_stored_conversation_in_every_dead_state():
    """The context section showed data in NO state; now the stored chat feeds it."""
    db = _db(mesajlar=_mesajlar("merhaba", "x" * 4000))

    # 1) No live session at all.
    with patch("providers.claude_sdk_session.peek_session", return_value=None):
        yok = _cagir("context", db)
    # 2) A turn is streaming.
    with patch("providers.claude_sdk_session.peek_session", return_value=MagicMock()), \
         patch("providers.claude_sdk_session.session_busy", return_value=True):
        mesgul = _cagir("context", db)
    # 3) Codex, where `/context` does not exist as a command at all.
    kodeks = _cagir("context", _db(model="gpt-5.6-sol",
                                   mesajlar=_mesajlar("merhaba", "x" * 4000)))

    for sonuc, sebep in ((yok, "no_session"), (mesgul, "busy"),
                         (kodeks, "codex_no_context")):
        assert sonuc["status"] == "estimate", f"{sebep}: {sonuc!r}"
        assert sonuc["reason"] == sebep
        p = sonuc["context_usage"]
        assert p["message_count"] == 2
        assert p["total_chars"] == 4007
        # The stamp that keeps the number from being read as a measurement.
        assert p["estimated"] is True


def test_an_estimate_is_never_dressed_up_as_a_live_report():
    """`estimate` must not arrive as `ok`, and no token is invented for it.

    Real token counts exist on only 4 of the 8 run paths. An estimate that
    arrived as `ok` would be drawn in the same card as a measured reading, and
    the user could not tell which one they were looking at.
    """
    db = _db(mesajlar=_mesajlar("merhaba"))
    with patch("providers.claude_sdk_session.peek_session", return_value=None):
        sonuc = _cagir("context", db)
    assert sonuc["status"] == "estimate"
    assert "text" not in sonuc, "an estimate must not travel as report text"
    assert "last_turn" not in sonuc["context_usage"], "no turn tokens were measured"
