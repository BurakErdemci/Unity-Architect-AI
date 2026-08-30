"""Uzun ve SAĞLIKLI bir araç akışı sigortaya takılmamalı.

Burak'ın itirazı (30 Ağu 2026, sahada): *"model mesela MCP'den tool çağıracak
ve tool adımları 50 60 adımlı oluyor; burada o zaman sürekli duracak API
modeller."* İtiraz haklı bir riski gösteriyor ve bir iddiayla değil ölçümle
cevaplanması gerekiyor — bu dosya o ölçüm.

Sigortanın ateşleme koşulu dar: AYNI araç + AYNI argüman + AYNI SONUÇ üçlüsü,
24'lük pencerede 5 kez. Yani "çok adım attı" diye durmuyor; "aynı soruyu aynı
cevapla beşinci kez sordu" diye duruyor. Aşağıdaki testler bu farkı sabitliyor:

  * 60 farklı çağrı            → durmuyor (tavana kadar gidiyor)
  * cevabı değişen yoklama     → durmuyor
  * aynı araç, farklı argüman  → durmuyor
  * gerçekten kısır tekrar     → duruyor

Dördüncüsü olmadan ilk üçü bir şey söylemez: sigorta hiç ateşlemiyorsa
"takılmıyor" demek ucuz olurdu.
"""
import asyncio
import os
import sys
import types
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import agentic.agent_runner as ar


class _AracCagiranGemini:
    """`uret(i)` i. turda hangi (araç, argüman) çağrılacağını söyler.

    `None` dönerse model işi bitirir.
    """

    def __init__(self, uret):
        self.calls = 0
        self._uret = uret
        self.models = types.SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs):
        i = self.calls
        self.calls += 1
        istek = self._uret(i)
        if istek is None:
            parts = [types.SimpleNamespace(function_call=None, text="bitti", thought=False)]
        else:
            ad, args = istek
            parts = [types.SimpleNamespace(
                function_call=types.SimpleNamespace(name=ad, args=args),
                text=None, thought=False)]
        return types.SimpleNamespace(
            candidates=[types.SimpleNamespace(content=types.SimpleNamespace(parts=parts))],
            usage_metadata=types.SimpleNamespace(prompt_token_count=1, candidates_token_count=1),
        )


async def _uyuma(_s):
    return None


def _kostur(uret, arac_sonucu):
    client = _AracCagiranGemini(uret)
    runner = ar.AgentRunner(provider_type="google", api_key="k", model_name="m",
                            workspace_path=".")
    patches = [
        mock.patch.object(ar, "execute_tool", arac_sonucu),
        mock.patch.object(ar, "_all_tool_definitions",
                          lambda: [{"name": "unity_list", "description": "d",
                                    "parameters": {"type": "object", "properties": {}}}]),
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


def _durma_sebebi(olaylar):
    for e in olaylar:
        if e.type == "done":
            return (e.data or {}).get("stop_reason")
    return None


def _arac_sayisi(olaylar):
    return sum(1 for e in olaylar if e.type == "tool_result")


def test_a_sixty_step_flow_with_distinct_calls_runs_to_the_end():
    """Burak'ın senaryosu: 50-60 adımlık gerçek bir MCP akışı."""
    def uret(i):
        return None if i >= 60 else ("unity_list", {"path": f"Assets/Klasor{i}"})

    def sonuc(name, args, workspace, conversation_id):
        return {"success": True, "summary": f"{args['path']} listelendi"}

    _, olaylar = _kostur(uret, sonuc)
    assert _durma_sebebi(olaylar) == "complete"
    assert _arac_sayisi(olaylar) == 60


def test_the_same_tool_with_different_arguments_is_not_a_stall():
    def uret(i):
        return None if i >= 30 else ("unity_list", {"path": f"A{i}"})

    def sonuc(name, args, workspace, conversation_id):
        return {"success": True, "summary": "ok"}   # ÖZET AYNI, argüman farklı

    _, olaylar = _kostur(uret, sonuc)
    assert _durma_sebebi(olaylar) == "complete"


def test_a_poll_whose_answer_moves_is_not_a_stall():
    # Unity'nin belgelenmiş akışı: `run_tests` → `get_test_job(job_id)` yoklaması.
    durum = {"n": 0}

    def uret(i):
        return None if i >= 20 else ("unity_list", {"job": "job-1"})

    def sonuc(name, args, workspace, conversation_id):
        durum["n"] += 1
        return {"success": True, "summary": "ok", "progress": durum["n"]}

    _, olaylar = _kostur(uret, sonuc)
    assert _durma_sebebi(olaylar) == "complete"


def test_a_genuinely_barren_repetition_still_stops():
    # Bu test olmadan yukarıdakiler bir şey söylemez: hiç ateşlemeyen bir
    # sigorta da "takılmıyor" sonucunu verirdi.
    def uret(i):
        return None if i >= 40 else ("unity_list", {"path": "Assets"})

    def sonuc(name, args, workspace, conversation_id):
        return {"success": True, "summary": "aynı"}

    _, olaylar = _kostur(uret, sonuc)
    assert _durma_sebebi(olaylar) == "no_progress"
    # Beşinci tekrarda duruyor — 40'a kadar dönmüyor.
    assert _arac_sayisi(olaylar) == 5
