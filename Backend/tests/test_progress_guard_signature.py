"""İlerleme sigortasına NE veriliyor: nesne mi, yoksa transkript için kısaltılmış
JSON dizesi mi.

Tek bir yazım hatası, iki yönde birden arıza (denetim, 30 Ağu 2026). Üç el
yazımı döngü de `record`'a, modele göndermek için ürettikleri `result_str`'i
veriyordu — 8.000 karaktere KIRPILMIŞ ve ZATEN serileştirilmiş bir dize:

  · Kırpılmış olduğu için, uzun bir ortak önek paylaşan gerçekten FARKLI iki
    sonuç aynı imzayı üretiyordu. Sağlıklı bir koşu "ilerleme yok" diye
    durduruluyordu — YANLIŞ DURUŞ: kullanıcı yapılmış işi kaybediyor.
  · Zaten serileştirilmiş olduğu için `_canonical_blob`'un `sort_keys`'i
    sıralayacak bir şey bulamıyordu; anahtar sırası VERİ gibi karşılaştırılıyor
    ve gerçekten tekrar eden bir sonuç ilerleme sanılıyordu.

İkisi tek tasarım hatası: sigorta nesne isterken ona dize veriliyordu. Bu dosya
her iki yönü de üç döngüde birden tutuyor — kapıyı bir dala koyup diğerlerini
açık bırakmak bu deponun adı konmuş yinelenen arızası.
"""
import asyncio
import json
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import agentic.agent_runner as ar

# Kırpma sınırının (8.000) üstünde ortak önek: kırpılmış imzada kuyruk hiç
# görünmez, yani DEĞİŞEN kısım tam olarak kaybolan kısımdır.
_UZUN_ONEK = "x" * 9000


def _tool_call(i, ad="read_file", args=None):
    return types.SimpleNamespace(
        id=f"t{i}",
        function=types.SimpleNamespace(
            name=ad, arguments=json.dumps(args or {"file_path": "a.txt"})))


class _AracCagiranOpenAI:
    """`durdur_sonrasi` çağrıya kadar hep aynı aracı aynı argümanlarla ister."""

    def __init__(self, durdur_sonrasi=6):
        self.calls = 0
        self.base_url = None
        self._durdur = durdur_sonrasi
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        i = self.calls
        self.calls += 1
        if i >= self._durdur:
            message = types.SimpleNamespace(content="bitti", tool_calls=None)
        else:
            message = types.SimpleNamespace(content=None, tool_calls=[_tool_call(i)])
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=message)],
            usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))


class _AracCagiranAnthropic:
    def __init__(self, durdur_sonrasi=6):
        self.calls = 0
        self._durdur = durdur_sonrasi
        self.messages = types.SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        i = self.calls
        self.calls += 1
        usage = types.SimpleNamespace(input_tokens=1, output_tokens=1)
        if i >= self._durdur:
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(type="text", text="bitti")], usage=usage)
        return types.SimpleNamespace(content=[types.SimpleNamespace(
            type="tool_use", id=f"t{i}", name="read_file",
            input={"file_path": "a.txt"})], usage=usage)


class _AracCagiranGemini:
    def __init__(self, durdur_sonrasi=6):
        self.calls = 0
        self._durdur = durdur_sonrasi
        self.models = types.SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs):
        i = self.calls
        self.calls += 1
        if i >= self._durdur:
            parts = [types.SimpleNamespace(function_call=None, text="bitti", thought=False)]
        else:
            parts = [types.SimpleNamespace(function_call=types.SimpleNamespace(
                name="read_file", args={"file_path": "a.txt"}), text=None, thought=False)]
        return types.SimpleNamespace(
            candidates=[types.SimpleNamespace(
                content=types.SimpleNamespace(parts=parts))],
            usage_metadata=types.SimpleNamespace(
                prompt_token_count=1, candidates_token_count=1))


_PROVIDERS = (("openai", _AracCagiranOpenAI),
              ("anthropic", _AracCagiranAnthropic),
              ("google", _AracCagiranGemini))


async def _uyuma(_saniye):
    """Döngüler tur başına 5 sn hız-sınırı molası veriyor; testin işi o değil."""
    return None


def _kostur(provider_type, client, arac_sonucu):
    runner = ar.AgentRunner(provider_type=provider_type, api_key="k",
                            model_name="m", workspace_path=".")

    async def _execute(_ad, _args):
        return arac_sonucu(), []

    runner._execute_tool_with_approval = _execute
    patches = [
        mock.patch.object(ar, "_all_tool_definitions", lambda: []),
        mock.patch.object(ar, "get_openai_tool_declarations", lambda: []),
        mock.patch.object(ar, "get_gemini_tool_declarations",
                          lambda: [{"function_declarations": []}]),
        mock.patch.object(ar.asyncio, "sleep", _uyuma),
        mock.patch.object(ar.openai, "AsyncOpenAI", lambda **kw: client),
        mock.patch.object(ar.anthropic, "AsyncAnthropic", lambda **kw: client),
        mock.patch.object(ar.genai, "Client", lambda **kw: client),
    ]

    async def _go():
        loop = {"openai": runner._run_openai, "anthropic": runner._run_anthropic,
                "google": runner._run_gemini}[provider_type]
        return [e async for e in loop("merhaba")]

    for p in patches:
        p.start()
    try:
        return asyncio.run(_go())
    finally:
        for p in reversed(patches):
            p.stop()


def _ozet(olaylar):
    done = [e for e in olaylar if e.type == "done"]
    return ((done[-1].data.get("stop_reason") if done else None),
            len([e for e in olaylar if e.type == "tool_call"]))


class TestLongDistinctResultsAreProgress(unittest.TestCase):
    """YANLIŞ DURUŞ yönü: farklı sonuçlar aynı sanılıp koşu kesiliyordu."""

    @staticmethod
    def _degisen_sonuc():
        sayac = {"n": 0}

        def _next():
            sayac["n"] += 1
            # Değişen kısım kırpma sınırının ÖTESİNDE — kırpılmış bir imzada
            # bu altı sonuç birbirinden ayırt edilemezdi.
            return {"success": True, "prefix": _UZUN_ONEK, "tail": sayac["n"]}

        return _next

    def test_changing_results_past_the_truncation_point_are_not_a_stall(self):
        for ad, factory in _PROVIDERS:
            with self.subTest(provider=ad):
                olaylar = _kostur(ad, factory(), self._degisen_sonuc())
                sebep, cagrilar = _ozet(olaylar)
                self.assertEqual(sebep, "complete")
                self.assertEqual(cagrilar, 6)

    def test_the_guard_hashes_long_values_instead_of_cutting_them(self):
        """Kırpma iki farklı değeri tek imzaya çökertir; özet almak çökertmez.
        Sınır burada `_STALL_ARG_MAX`, ve aşan değer HASH'leniyor."""
        a = ar._canonical_call("read_file", {"p": "a"},
                               {"prefix": _UZUN_ONEK, "tail": 1})
        b = ar._canonical_call("read_file", {"p": "a"},
                               {"prefix": _UZUN_ONEK, "tail": 2})
        self.assertNotEqual(a, b)
        self.assertLess(len(a), 200)


class TestReorderedEquivalentResultsAreARepeat(unittest.TestCase):
    """Ters yön: aynı sonuç, farklı anahtar sırası — yine de tekrar."""

    @staticmethod
    def _sirasi_degisen_sonuc():
        sayac = {"n": 0}

        def _next():
            sayac["n"] += 1
            if sayac["n"] % 2:
                return {"success": True, "alpha": "a", "beta": "b"}
            return {"beta": "b", "success": True, "alpha": "a"}

        return _next

    def test_key_order_alone_does_not_count_as_progress(self):
        for ad, factory in _PROVIDERS:
            with self.subTest(provider=ad):
                olaylar = _kostur(ad, factory(), self._sirasi_degisen_sonuc())
                sebep, cagrilar = _ozet(olaylar)
                self.assertEqual(sebep, "no_progress")
                self.assertEqual(cagrilar, ar._STALL_LIMIT)

    def test_the_canonicalizer_sorts_result_keys(self):
        self.assertEqual(
            ar._canonical_call("t", {}, {"a": 1, "b": 2}),
            ar._canonical_call("t", {}, {"b": 2, "a": 1}))

    def test_a_pre_serialized_result_defeats_the_sort(self):
        """Neden çağıranlar NESNE geçmek zorunda, tek satırda.

        Dize hâlinde verilen aynı sözlük iki farklı imza üretiyor; sigortanın
        `sort_keys`'i o noktada yapacak bir şey bulamıyor.
        """
        self.assertNotEqual(
            ar._canonical_call("t", {}, json.dumps({"a": 1, "b": 2})),
            ar._canonical_call("t", {}, json.dumps({"b": 2, "a": 1})))


class TestEveryCallSitePassesTheObject(unittest.TestCase):
    """Sınıfı kapatıyor, üç örneği değil: `record`'a kırpılmış dize veren YENİ
    bir çağrı yeri de aynı arızayı sessizce geri getirirdi."""

    def test_no_record_call_is_handed_the_truncated_string(self):
        src = open(ar.__file__, encoding="utf-8").read()
        cagrilar = [ln.strip() for ln in src.splitlines()
                    if "_progress.record(" in ln and not ln.strip().startswith("#")]
        self.assertTrue(cagrilar)
        for ln in cagrilar:
            self.assertNotIn("result_str", ln, ln)


if __name__ == "__main__":
    unittest.main()
