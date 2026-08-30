"""Onay kapısının yaşam döngüsü — 30 Ağu 2026 denetiminden terfi eden testler.

Üç bulgu buraya taşındı. İkisinin kanıt betiği düzeltmeden sonra `rc=2`
(ölçtüğü API kalmadı) döndü; bir sınıfı "artık ölçemiyorum" ile kapatmak
kapatmak değildir, o yüzden iddiaları kalıcı teste çevrildi.

Kapı bu üründeki en sonuç doğuran karar noktası: model bir aracı çalıştırmak
isterken kullanıcının evet/hayır'ını burada bekliyor.
"""
import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import agentic.agent_runner as ar
from agentic.command_gates import APPROVAL_GATES, APPROVAL_RESULTS


def _delete_call_client():
    """Her turda silme (onay gerektiren) çağrısı isteyen sahte Anthropic."""

    class _C:
        def __init__(self):
            self.messages = types.SimpleNamespace(create=self._create)

        async def _create(self, **kw):
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(
                    type="tool_use", id="t1", name="delete_file",
                    input={"file_path": "a.cs"})],
                usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    return _C()


class TestGateCleanup(unittest.TestCase):
    def setUp(self):
        APPROVAL_GATES.clear()
        APPROVAL_RESULTS.clear()

    def test_closing_the_stream_at_the_approval_card_leaves_no_gate(self):
        """Kayıt temizliği eskiden beklemenin `finally`'sindeydi; istemci kartı
        gördükten HEMEN sonra akışı kapatınca beklemeye hiç girilmiyor ve iki
        kayıt da geride kalıyordu. Geç gelen bir cevap o sahipsiz kapıyı
        `True`'ya çevirebiliyordu.
        """
        runner = ar.AgentRunner(provider_type="anthropic", api_key="k",
                                model_name="m", workspace_path=".")
        client = _delete_call_client()

        async def _drive():
            gen = runner._run_anthropic("merhaba")
            async for ev in gen:
                if ev.type == "command_approval_needed":
                    await gen.aclose()   # kullanıcı sekmeyi kapattı
                    break

        with mock.patch.object(ar.anthropic, "AsyncAnthropic", lambda **kw: client), \
             mock.patch.object(ar, "_all_tool_definitions",
                               lambda: [{"name": "delete_file", "description": "d",
                                         "parameters": {"type": "object", "properties": {}}}]):
            asyncio.run(_drive())

        self.assertEqual(dict(APPROVAL_GATES), {})
        self.assertEqual(dict(APPROVAL_RESULTS), {})


class TestGateIdentity(unittest.TestCase):
    def setUp(self):
        APPROVAL_GATES.clear()
        APPROVAL_RESULTS.clear()

    def test_two_gates_never_share_a_slot(self):
        """Kimlik 10 onaltılık karaktere kırpılıyordu ve kayıt zaten var mı diye
        bakılmıyordu: aynı değeri çeken iki eşzamanlı tur tek yuvayı paylaşıyor,
        birine verilen onay diğerini çalıştırabiliyordu.

        `uuid4` sabitlenerek çakışma ZORLANIYOR — gerçek hayatta 128 bitte
        olmayacak bir şey, ama kapı bu koşulda da iki ayrı yuva vermeli.
        """
        runner = ar.AgentRunner(provider_type="anthropic", api_key="k",
                                model_name="m", workspace_path=".")
        fixed = types.SimpleNamespace(hex="a" * 32)
        with mock.patch.object(ar.uuid, "uuid4", lambda: fixed):
            with runner._approval_gate("rm -rf a") as (_ev_a, id_a):
                with runner._approval_gate("rm -rf b") as (_ev_b, id_b):
                    self.assertNotEqual(id_a, id_b)
                    APPROVAL_RESULTS[id_b] = True
                    self.assertFalse(APPROVAL_RESULTS[id_a])

    def test_gate_ids_are_released_after_the_block(self):
        runner = ar.AgentRunner(provider_type="anthropic", api_key="k",
                                model_name="m", workspace_path=".")
        with runner._approval_gate("rm -rf a") as (_ev, gate_id):
            self.assertIn(gate_id, APPROVAL_GATES)
        self.assertNotIn(gate_id, APPROVAL_GATES)
        self.assertNotIn(gate_id, APPROVAL_RESULTS)


class TestDecisionHonesty(unittest.TestCase):
    """Fail-closed olmak ile "kullanıcı reddetti" demek aynı şey değil."""

    def setUp(self):
        APPROVAL_GATES.clear()
        APPROVAL_RESULTS.clear()

    def _decide(self, gate_id):
        runner = ar.AgentRunner(provider_type="anthropic", api_key="k",
                                model_name="m", workspace_path=".")
        return asyncio.run(runner._await_approval(gate_id))

    def test_missing_gate_is_not_reported_as_a_refusal(self):
        d = self._decide("yok-boyle-bir-kapi")
        self.assertFalse(d.approved)
        self.assertNotIn("reddedildi", d.summary.lower())

    def test_waiter_failure_is_not_reported_as_a_refusal(self):
        """Denetim bulgusu: bekleyici bir istisna atınca üç kopya da modele
        "kullanıcı reddetti" diyordu; model hiç verilmemiş bir karara göre
        akıl yürütüyordu."""
        async def _go():
            runner = ar.AgentRunner(provider_type="anthropic", api_key="k",
                                    model_name="m", workspace_path=".")
            with runner._approval_gate("rm -rf x") as (_ev, gate_id):
                async def _boom(*a, **kw):
                    raise RuntimeError("bekleyici patladı")
                with mock.patch.object(ar.asyncio, "wait_for", _boom):
                    return await runner._await_approval(gate_id)

        d = asyncio.run(_go())
        self.assertFalse(d.approved)
        self.assertNotIn("reddedildi", d.summary.lower())

    def test_an_actual_refusal_still_says_so(self):
        async def _go():
            runner = ar.AgentRunner(provider_type="anthropic", api_key="k",
                                    model_name="m", workspace_path=".")
            with runner._approval_gate("rm -rf x") as (_ev, gate_id):
                APPROVAL_RESULTS[gate_id] = False
                APPROVAL_GATES[gate_id].set()
                return await runner._await_approval(gate_id)

        d = asyncio.run(_go())
        self.assertFalse(d.approved)
        self.assertIn("reddedildi", d.summary.lower())

    def test_approval_is_honoured(self):
        async def _go():
            runner = ar.AgentRunner(provider_type="anthropic", api_key="k",
                                    model_name="m", workspace_path=".")
            with runner._approval_gate("rm -rf x") as (_ev, gate_id):
                APPROVAL_RESULTS[gate_id] = True
                APPROVAL_GATES[gate_id].set()
                return await runner._await_approval(gate_id)

        self.assertTrue(asyncio.run(_go()).approved)


if __name__ == "__main__":
    unittest.main()
