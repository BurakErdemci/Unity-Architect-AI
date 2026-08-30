"""Sağlayıcı beklerken kullanıcıya NE söyleniyor — OpenAI uyumlu yol.

İki arıza, ikisi de sahada (Burak, 30 Ağu 2026):

1. NVIDIA NIM üzerinde bir DeepSeek modeli iki dakika boyunca cevap vermedi ve
   ekranda yalnız "düşünüyor..." vardı. Kullanıcı uygulamanın mı sağlayıcının
   mı takıldığını ayırt edemiyordu. `openai` SDK'sının varsayılan zaman aşımı
   600 saniye, yani hiçbir şey söylemeden on dakika beklenebiliyordu.

2. Aynı döngüdeki hata sınıflandırması `"429" in err_msg` idi. Gemini yolunda
   30 Ağu'da düzeltildi, BURASI UNUTULDU — bu deponun en sık arıza şekli:
   dört yoldan birini kapatan fix. Sınıflandırma artık tek bir fonksiyonda
   (`provider_retry_code`) ve iki döngü de onu çağırıyor.
"""
import asyncio
import os
import sys
import types
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import agentic.agent_runner as ar


# ── Sınıflandırıcı: tek kopya, sınır ile eşleşme ───────────────────────────


@pytest.mark.parametrize("metin,beklenen", [
    ("429 RESOURCE_EXHAUSTED", "429"),
    ("Error code: 429 - rate limited", "429"),
    ("too many requests", "429"),
    ("503 Service Unavailable", "503"),
    ("model unavailable right now", "503"),
    ("400 INVALID_ARGUMENT: token count 4293 exceeds limit", None),
    ("500 internal error id=15034", None),
    ("", None),
])
def test_the_retry_classifier_matches_codes_at_a_boundary(metin, beklenen):
    assert ar.provider_retry_code(metin) == beklenen


def test_a_number_containing_429_is_not_a_quota_error():
    # Sınıfın en pahalı hâli: alakasız bir hata üç kez yeniden denenip
    # sonra kullanıcıya "kota" diye raporlanıyordu.
    assert ar.provider_retry_code("prompt is 4293 tokens") is None
    assert ar.provider_retry_code("request 50399 failed") is None


# ── Bekleme sessiz olmamalı ────────────────────────────────────────────────


class _YavasOpenAI:
    """İlk çağrıda gecikir, sonra araçsız bir cevap döndürür."""

    def __init__(self, gecikme_turu: int):
        self.calls = 0
        self._gecikme = gecikme_turu
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            # Kalp atışı sayacının birkaç kez dönmesine yetecek kadar bekle.
            await asyncio.sleep(self._gecikme)
        message = types.SimpleNamespace(content="bitti", tool_calls=None)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=message)],
            usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))


def _kostur(client, kalp_atisi=0.01):
    runner = ar.AgentRunner(provider_type="nvidia", api_key="k",
                            model_name="deepseek-ai/deepseek-v4-flash", workspace_path=".")
    patches = [
        mock.patch.object(ar, "_all_tool_definitions", lambda: []),
        mock.patch.object(ar, "get_openai_tool_declarations", lambda: []),
        mock.patch.object(ar, "_KALP_ATISI_SN", kalp_atisi),
        mock.patch.object(ar.openai, "AsyncOpenAI", lambda **kw: client),
    ]

    async def _go():
        return [e async for e in runner._run_inner("merhaba")]

    for p in patches:
        p.start()
    try:
        return asyncio.run(_go())
    finally:
        for p in reversed(patches):
            p.stop()


def test_a_slow_provider_produces_heartbeats_rather_than_silence():
    olaylar = _kostur(_YavasOpenAI(gecikme_turu=0.06))
    kalpler = [e for e in olaylar if e.type == "status"
               and "sn'dir yanıt vermedi" in (e.data.get("detail") or "")]
    assert kalpler, "bekleme sessiz kalmamalı"


def test_the_heartbeat_names_the_model_and_offers_a_way_out():
    olaylar = _kostur(_YavasOpenAI(gecikme_turu=0.06))
    detay = next(e.data["detail"] for e in olaylar if e.type == "status"
                 and "sn'dir yanıt vermedi" in (e.data.get("detail") or ""))
    assert "deepseek-ai/deepseek-v4-flash" in detay
    assert "Durdur" in detay


def test_a_fast_provider_produces_no_heartbeat_noise():
    olaylar = _kostur(_YavasOpenAI(gecikme_turu=0))
    kalpler = [e for e in olaylar if e.type == "status"
               and "sn'dir yanıt vermedi" in (e.data.get("detail") or "")]
    assert kalpler == []


def test_the_run_still_finishes_after_the_wait():
    olaylar = _kostur(_YavasOpenAI(gecikme_turu=0.06))
    assert any(e.type == "done" for e in olaylar)
    assert any(e.type == "response" for e in olaylar)


def test_an_explicit_timeout_is_sent_rather_than_the_sdk_default():
    """SDK varsayılanı 600 sn ve o süre boyunca hiçbir şey söylenmiyordu."""
    yakalanan = {}

    class _Yakalayan(_YavasOpenAI):
        async def _create(self, **kwargs):
            yakalanan.update(kwargs)
            return await super()._create(**kwargs)

    _kostur(_Yakalayan(gecikme_turu=0))
    assert yakalanan.get("timeout") == ar._SAGLAYICI_ZAMAN_ASIMI
