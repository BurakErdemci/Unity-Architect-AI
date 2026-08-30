"""Sağlayıcı isteğinin ömrü: beklerken konuşmak, tur ölünce isteği bırakmamak,
ve bozuk bir cevabı terminal olaya çevirmek.

Üç arıza, üçü de 30 Ağu 2026 denetiminde canlı üretildi:

1. Kalp atışı yalnız OpenAI-uyumlu isteğin ETRAFINA konmuştu. Gemini bloklayan
   SDK çağrısını `asyncio.to_thread` ile, Anthropic `messages.create`'i doğrudan
   bekliyordu ve ikisi de tek olay yaymadan sessiz kalıyordu. Bu deponun adı
   konmuş yinelenen arızası: kapı bir dala konuyor, diğerleri açık kalıyor.
   O yüzden buradaki testler ÜÇ yolu birden sınıyor.

2. OpenAI döngüsü isteği bir göreve alıp `asyncio.wait` ile yarıştırıyor ama
   generator kapandığında (kullanıcı "Durdur"a bastığında) o görevi kimse iptal
   etmiyordu: durdurulan bir tur sağlayıcı çağrısını 300 sn'lik zaman aşımına
   kadar sahipsiz koşar hâlde bırakıyordu.

3. `response.choices[0]` kontrolsüz indeksleniyordu. `choices=[]` dönen bir
   sağlayıcı cevabında `IndexError` generator'ın DIŞINA taşıyor ve tur HİÇBİR
   terminal olay üretmeden bitiyordu — sözleşme her turun tam olarak bir `done`
   ya da bir `error` ile bitmesi (bkz. `test_iteration_ceiling`).

Canlı sağlayıcıya çıkılmıyor: her istemci sahte.
"""
import asyncio
import os
import sys
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import agentic.agent_runner as ar


# ── Ortak koşum düzeneği ────────────────────────────────────────────────────


def _patches(client, kalp_atisi=0.01):
    return [
        mock.patch.object(ar, "_all_tool_definitions", lambda: []),
        mock.patch.object(ar, "get_openai_tool_declarations", lambda: []),
        mock.patch.object(ar, "get_gemini_tool_declarations",
                          lambda: [{"function_declarations": []}]),
        mock.patch.object(ar, "_KALP_ATISI_SN", kalp_atisi),
        mock.patch.object(ar.openai, "AsyncOpenAI", lambda **kw: client),
        mock.patch.object(ar.anthropic, "AsyncAnthropic", lambda **kw: client),
        mock.patch.object(ar.genai, "Client", lambda **kw: client),
    ]


def _runner(provider_type):
    return ar.AgentRunner(provider_type=provider_type, api_key="k",
                          model_name="test-model", workspace_path=".")


def _loop_of(runner, provider_type, mesaj="merhaba"):
    return {"openai": runner._run_openai,
            "anthropic": runner._run_anthropic,
            "google": runner._run_gemini}[provider_type](mesaj)


def _collect(provider_type, client, kalp_atisi=0.01):
    runner = _runner(provider_type)
    ps = _patches(client, kalp_atisi)

    async def _go():
        return [e async for e in _loop_of(runner, provider_type)]

    for p in ps:
        p.start()
    try:
        return asyncio.run(_go())
    finally:
        for p in reversed(ps):
            p.stop()


def _kalpler(olaylar):
    return [e for e in olaylar if e.type == "status"
            and "sn'dir yanıt vermedi" in (e.data.get("detail") or "")]


# ── Sahte, YAVAŞ sağlayıcılar ───────────────────────────────────────────────
# Gecikme kalp atışı aralığının (0.01) birkaç katı; testin kendisi ~60 ms.
_GECIKME = 0.06


class _YavasOpenAI:
    def __init__(self):
        self.base_url = None
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        await asyncio.sleep(_GECIKME)
        message = types.SimpleNamespace(content="bitti", tool_calls=None)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=message)],
            usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))


class _YavasAnthropic:
    def __init__(self):
        self.messages = types.SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        await asyncio.sleep(_GECIKME)
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text="bitti")],
            usage=types.SimpleNamespace(input_tokens=1, output_tokens=1))


class _YavasGemini:
    """Gemini'nin SDK çağrısı BLOKLAYAN: `time.sleep`, `asyncio.sleep` değil.

    Arızanın tam şekli buydu — iş `asyncio.to_thread` ile havuz thread'ine
    gidiyor, olay döngüsü boşta ama hiçbir şey yayınlamıyordu.
    """

    def __init__(self):
        self.models = types.SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs):
        time.sleep(_GECIKME)
        part = types.SimpleNamespace(function_call=None, text="bitti", thought=False)
        return types.SimpleNamespace(
            candidates=[types.SimpleNamespace(
                content=types.SimpleNamespace(parts=[part]))],
            usage_metadata=types.SimpleNamespace(
                prompt_token_count=1, candidates_token_count=1))


_YAVAS = (("openai", _YavasOpenAI), ("anthropic", _YavasAnthropic),
          ("google", _YavasGemini))


class TestHeartbeatCoversEveryProvider(unittest.TestCase):

    def test_a_slow_call_reports_on_all_three_paths(self):
        for ad, factory in _YAVAS:
            with self.subTest(provider=ad):
                olaylar = _collect(ad, factory())
                self.assertTrue(_kalpler(olaylar),
                                "bekleme sessiz kalmamalı")

    def test_the_heartbeat_names_the_model_and_offers_a_way_out(self):
        for ad, factory in _YAVAS:
            with self.subTest(provider=ad):
                detay = _kalpler(_collect(ad, factory()))[0].data["detail"]
                self.assertIn("test-model", detay)
                self.assertIn("Durdur", detay)

    def test_a_fast_call_produces_no_heartbeat_noise(self):
        """Kalp atışı bir gürültü kaynağına dönüşürse anlamını kaybeder."""

        class _HizliOpenAI(_YavasOpenAI):
            async def _create(self, **kwargs):
                message = types.SimpleNamespace(content="bitti", tool_calls=None)
                return types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=message)],
                    usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))

        self.assertEqual(_kalpler(_collect("openai", _HizliOpenAI())), [])

    def test_the_run_still_finishes_after_the_wait(self):
        for ad, factory in _YAVAS:
            with self.subTest(provider=ad):
                olaylar = _collect(ad, factory())
                self.assertEqual([e.type for e in olaylar
                                  if e.type in ("done", "error")], ["done"])

    def test_the_wait_lives_in_one_helper_not_three(self):
        """Sınıfı kapatıyor, bir dalı değil.

        Bekleme mantığı üç döngüye kopyalanırsa biri düzeltilip diğeri
        unutuluyor — bu deponun ölçülmüş en sık arıza şekli, ve kalp atışının
        ilk hâli tam olarak böyle tek dala konmuştu.
        """
        src = open(ar.__file__, encoding="utf-8").read()
        self.assertEqual(src.count("asyncio.wait({"), 1)
        self.assertEqual(src.count("self._await_provider("), 3)


# ── Durdurulan tur sağlayıcı isteğini de götürür ────────────────────────────


class _AskidaOpenAI:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.tasks = []
        self.base_url = None
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.started.set()
        self.tasks.append(asyncio.current_task())
        await self.release.wait()
        raise AssertionError("askıda kalan istek serbest bırakılmamalıydı")


class _AskidaAnthropic(_AskidaOpenAI):
    def __init__(self):
        super().__init__()
        self.messages = types.SimpleNamespace(create=self._create)


class TestCancellationTakesTheRequestWithIt(unittest.TestCase):
    """Durdurulan bir tur arkasında koşan bir sağlayıcı çağrısı bırakmaz.

    Bırakınca ne oluyordu: sonucunu tüketecek kimse kalmadığı hâlde istek
    300 sn'lik zaman aşımına kadar sağlayıcı/ağ kaynağı harcamaya devam
    ediyor, art arda durdurulan turlar bunları biriktiriyordu.
    """

    def _iptal_et(self, provider_type, client):
        async def _go():
            runner = _runner(provider_type)
            gen = _loop_of(runner, provider_type)
            tuketici = asyncio.create_task(gen.__anext__())
            await asyncio.wait_for(client.started.wait(), timeout=2.0)
            tuketici.cancel()
            await asyncio.gather(tuketici, return_exceptions=True)
            await asyncio.sleep(0)
            askida = [t for t in client.tasks if not t.done()]
            await gen.aclose()
            return client.tasks, askida

        ps = _patches(client)
        for p in ps:
            p.start()
        try:
            return asyncio.run(_go())
        finally:
            for p in reversed(ps):
                p.stop()

    def test_stopping_the_turn_cancels_the_openai_request(self):
        tumu, askida = self._iptal_et("openai", _AskidaOpenAI())
        self.assertEqual(len(tumu), 1)
        self.assertEqual(askida, [])

    def test_stopping_the_turn_cancels_the_anthropic_request(self):
        tumu, askida = self._iptal_et("anthropic", _AskidaAnthropic())
        self.assertEqual(len(tumu), 1)
        self.assertEqual(askida, [])

    def test_a_finished_request_is_not_cancelled_out_from_under_the_caller(self):
        """İptal `done()` olmayan isteğe ÖZEL.

        Biten bir isteği `finally` içinde beklemek onun sonucunu (ya da
        istisnasını) yutardı; bu test bitenin sonucunun hâlâ okunduğunu
        gösteriyor, yani iptal ucu yutan bir uca dönüşmemiş.
        """
        olaylar = _collect("openai", _YavasOpenAI())
        yanit = [e for e in olaylar if e.type == "response"]
        self.assertEqual([e.data["content"] for e in yanit], ["bitti"])

    def test_a_provider_error_is_still_reported_not_swallowed(self):
        class _Patlayan(_YavasOpenAI):
            async def _create(self, **kwargs):
                raise RuntimeError("saglayici patladi")

        olaylar = _collect("openai", _Patlayan())
        terminal = [e for e in olaylar if e.type in ("done", "error")]
        self.assertEqual([e.type for e in terminal], ["error"])
        self.assertIn("saglayici patladi", terminal[0].data["message"])


# ── Bozuk sağlayıcı cevabı = tam olarak bir terminal olay ───────────────────


class TestMalformedResponseStillTerminates(unittest.TestCase):

    def test_empty_choices_becomes_exactly_one_error(self):
        class _BosSecenek:
            def __init__(self):
                self.base_url = None
                self.chat = types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=self._create))

            async def _create(self, **kwargs):
                return types.SimpleNamespace(choices=[], usage=None)

        olaylar = _collect("openai", _BosSecenek())   # istisna sızarsa test kırmızı
        terminal = [e for e in olaylar if e.type in ("done", "error")]
        self.assertEqual([e.type for e in terminal], ["error"])
        self.assertEqual(terminal[0].data["code"], "provider_malformed_response")
        # Mesaj hangi modelin bozuk cevap verdiğini söylemeli: "bir hata oldu"
        # kullanıcının üzerine hareket edebileceği bir cümle değil.
        self.assertIn("test-model", terminal[0].data["message"])

    def test_gemini_content_without_parts_still_terminates(self):
        """Aynı sınıfın Gemini'deki hâli: `candidates` boşluğu kapalıydı ama
        `content.parts` değildi ve `for part in None` bir `TypeError`'ı dışarı
        taşırdı. Parçasız bir aday araçsız bir tur demek → tek `done`."""

        class _ParcasizGemini:
            def __init__(self):
                self.models = types.SimpleNamespace(generate_content=self._generate)

            def _generate(self, **kwargs):
                return types.SimpleNamespace(
                    candidates=[types.SimpleNamespace(
                        content=types.SimpleNamespace(parts=None))],
                    usage_metadata=None)

        olaylar = _collect("google", _ParcasizGemini())
        self.assertEqual([e.type for e in olaylar
                          if e.type in ("done", "error")], ["done"])

    def test_anthropic_response_without_content_still_terminates(self):
        class _IceriksizAnthropic:
            def __init__(self):
                self.messages = types.SimpleNamespace(create=self._create)

            async def _create(self, **kwargs):
                return types.SimpleNamespace(content=None, usage=None)

        olaylar = _collect("anthropic", _IceriksizAnthropic())
        self.assertEqual([e.type for e in olaylar
                          if e.type in ("done", "error")], ["done"])


if __name__ == "__main__":
    unittest.main()
