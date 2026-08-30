"""Gemini yeniden-deneme turunun kullanıcıya NE söylediği.

Saha, 30 Ağu 2026: araç çağıran bir Gemini koşumu üç araçtan sonra
"AI yanıt vermeyi reddetti (Rate Limit)." ile öldü. O cümle iki şeyi birden
yanlış söylüyordu:

  * reddeden MODEL değil, sağlayıcı (kota) — "AI reddetti" kullanıcıyı
    prompt'unu değiştirmeye yollar, oysa yapılacak şey beklemek;
  * 503 (servis kesintisi) de aynı cümleyle "Rate Limit" diye raporlanıyordu,
    yani teşhis için gereken tek ayrım siliniyordu. Kod loglarda vardı,
    kullanıcıda yoktu.

Üçüncü kusur sessizdi: üç deneme 10+20+30 = 60 saniye bekliyor ve o süre
boyunca arayüze TEK olay gitmiyordu. Kullanıcı donmuş bir uygulama görüyor.
"""
import asyncio
import os
import sys
import types
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import agentic.agent_runner as ar


class _HepPatlayanGemini:
    def __init__(self, hata: str):
        self.calls = 0
        self._hata = hata
        self.models = types.SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs):
        self.calls += 1
        raise RuntimeError(self._hata)


async def _uyuma(_s):
    return None


def _kostur(hata: str):
    client = _HepPatlayanGemini(hata)
    runner = ar.AgentRunner(provider_type="google", api_key="k", model_name="m",
                            workspace_path=".")
    patches = [
        mock.patch.object(ar, "_all_tool_definitions", lambda: []),
        mock.patch.object(ar, "get_gemini_tool_declarations",
                          lambda: [{"function_declarations": []}]),
        mock.patch.object(ar.asyncio, "sleep", _uyuma),
        mock.patch.object(ar.genai, "Client", lambda **kw: client),
    ]

    async def _go():
        return [e async for e in runner._run_inner("merhaba")]

    for p in patches:
        p.start()
    try:
        return client, asyncio.run(_go())
    finally:
        for p in reversed(patches):
            p.stop()


def _hata_metni(olaylar):
    return next(e.data["message"] for e in olaylar if e.type == "error")


def test_a_quota_refusal_says_quota_not_that_the_model_refused():
    _, olaylar = _kostur("429 RESOURCE_EXHAUSTED: quota")
    metin = _hata_metni(olaylar)
    assert "kota" in metin.lower()
    assert "reddetti" in metin  # sağlayıcı reddetti — ama...
    assert "AI yanıt vermeyi reddetti" not in metin


def test_an_outage_is_not_reported_as_a_rate_limit():
    # Eski kod 503'ü de "Rate Limit" diye raporluyordu; iki arızanın
    # kullanıcıya söylediği iş farklı (bekle vs. tekrar dene).
    _, olaylar = _kostur("503 Service Unavailable")
    metin = _hata_metni(olaylar)
    assert "503" in metin
    assert "kota" not in metin.lower()


def test_the_wait_is_announced_rather_than_silent():
    # Üç deneme 60 saniye sürüyor. Tek olay gitmezse uygulama donmuş görünür.
    _, olaylar = _kostur("429 too many requests")
    durumlar = [e for e in olaylar if e.type == "status"]
    assert len(durumlar) == 3
    assert all("deneme" in (e.data.get("detail") or "").lower() for e in durumlar)


def test_all_three_attempts_actually_run():
    client, _ = _kostur("429 quota")
    assert client.calls == 3


def test_a_non_retryable_error_is_not_retried_and_carries_its_own_text():
    client, olaylar = _kostur("400 INVALID_ARGUMENT: Role 'tool' is not supported")
    assert client.calls == 1
    assert "INVALID_ARGUMENT" in _hata_metni(olaylar)


def test_a_number_that_merely_contains_429_is_not_a_quota_error():
    """`"429" in err_msg` bir sayının İÇİNDE de eşleşiyordu.

    Bedeli üç katlı: alakasız bir hata kota sanılıyor, üç kez boşuna yeniden
    deneniyor (60 sn), ve kullanıcıya yanlış teşhis veriliyor — o da prompt'unu
    değil bekleme süresini değiştirmeye çalışıyor.
    """
    client, olaylar = _kostur("400 INVALID_ARGUMENT: token count 4293 exceeds limit")
    assert client.calls == 1, "kota sanılıp yeniden denenmemeli"
    metin = _hata_metni(olaylar)
    assert "4293" in metin
    assert "kota" not in metin.lower()


def test_the_turn_ends_with_error_and_no_done():
    # A paketinin sonlanma sözleşmesi: bir tur `done` YA DA `error` ile biter.
    _, olaylar = _kostur("429 quota")
    tipler = [e.type for e in olaylar]
    assert "error" in tipler
    assert "done" not in tipler
