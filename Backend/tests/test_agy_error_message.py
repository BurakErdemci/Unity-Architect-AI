"""Antigravity (`agy`) yolunda hata olayının MESAJI.

Arıza (denetim, 30 Ağu 2026): `cli_base` agy'nin zaman aşımını bir JSON content
event'inden üretirken ayrıntıyı `text` alanına koyuyor, `_run_agy_session` ise
yalnız `content` okuyordu. Terminal olay vardı — sözleşme bozulmuyordu — ama
kullanıcıya giden `error` olayının mesajı BOŞTU: agy'nin zaman aşımına uğradığı
ile bilinmeyen bir çökme birbirinden ayırt edilemiyordu, ve tur açıklayıcı bir
yanıt da kaydedilmeden kapanıyordu.

Ders daha genel: bir olayı tek alan adıyla okumak, o alanı üreten tarafla bu
tarafın ayrışmasına açık bırakır. İki ad da okunuyor, ve ikisi de boşsa bile
kullanıcı boş bir kutu değil bir cümle görüyor.
"""
import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import agentic.agent_runner as ar


class _SahteOturum:
    agy_uuid = None
    last_step_idx = -1
    auto_approve = False
    active_provider = None


def _hata_veren_saglayici(event: dict):
    class _P:
        async def analyze_code(self, *args, **kwargs):
            yield event

    return _P()


def _kostur(event: dict):
    import ai_providers
    import providers.agy_session as agy_session

    runner = ar.AgentRunner(provider_type="subscription", api_key="",
                            model_name="gemini-test", workspace_path=".",
                            conversation_id=9911)
    patches = [
        mock.patch.object(agy_session, "get_session", lambda cid: _SahteOturum()),
        mock.patch.object(ai_providers.AIProviderManager, "get_provider",
                          lambda cfg: _hata_veren_saglayici(event)),
    ]

    async def _go():
        return [e async for e in runner._run_agy_session("merhaba")]

    for p in patches:
        p.start()
    try:
        return asyncio.run(_go())
    finally:
        for p in reversed(patches):
            p.stop()


class TestAgyErrorTextReachesTheUser(unittest.TestCase):

    def test_a_timeout_reported_in_text_is_forwarded(self):
        """`cli_base`'in agy zaman aşımı için ürettiği olay şekli."""
        olaylar = _kostur({"type": "error", "text": "agy zaman aşımına uğradı."})
        hatalar = [e for e in olaylar if e.type == "error"]
        self.assertEqual([e.data["message"] for e in hatalar],
                         ["agy zaman aşımına uğradı."])

    def test_the_older_content_shape_still_works(self):
        """`text` eklenirken `content` düşürülmedi: diğer CLI yolları hâlâ onu
        yolluyor ve bir alanı diğeriyle DEĞİŞTİRMEK arızayı sadece taşırdı."""
        olaylar = _kostur({"type": "error", "content": "agy çöktü."})
        hatalar = [e for e in olaylar if e.type == "error"]
        self.assertEqual([e.data["message"] for e in hatalar], ["agy çöktü."])

    def test_an_error_with_no_detail_still_says_something(self):
        """Boş mesajlı bir `error` kullanıcıya hiçbir şey anlatmıyor; ayrıntı
        gerçekten yoksa bile bunun SÖYLENMESİ gerekiyor."""
        olaylar = _kostur({"type": "error"})
        hatalar = [e for e in olaylar if e.type == "error"]
        self.assertEqual(len(hatalar), 1)
        self.assertTrue(hatalar[0].data["message"].strip())

    def test_the_error_is_the_only_terminal_event(self):
        """Tur sözleşmesi: tam olarak bir `done` YA DA bir `error`."""
        olaylar = _kostur({"type": "error", "text": "agy zaman aşımına uğradı."})
        self.assertEqual([e.type for e in olaylar
                          if e.type in ("done", "error")], ["error"])


if __name__ == "__main__":
    unittest.main()
