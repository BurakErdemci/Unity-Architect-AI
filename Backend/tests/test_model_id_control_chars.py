"""Model KİMLİĞİ denetim karakteri taşıyorsa satır kabul edilmez.

Doğrulama turunun bulgusu (30 Ağu 2026): görünen adlar çizim yerinde
temizlendi, ama KAYITLI kimlik aynı sınıfın bir adım ilerisiydi \u2014 ayarlardaki
düzenlenebilir kutuya ve sohbetin model etiketine ham giriyordu.

Kimlik adla aynı şekilde ele alınamıyor, ve ayrım bu testin sebebi:
- Ad yalnızca bir etiket → çizerken temizlenir.
- Kimlik hem gösteriliyor hem KULLANILIYOR (sağlayıcıya gidiyor, config'e
  yazılıyor). Çizerken temizlemek, gösterilenden başkasını göndermek olurdu;
  her yerde temizlemek ise sağlayıcıya hiç yayınlamadığı bir kimlik yollamak.
  Geriye tek dürüst seçenek kalıyor: satırı reddetmek.

Reddetmek modeli kaybettiriyor, evet \u2014 ama bir kimlikte U+202E'nin meşru bir
karşılığı yok, ve o satırı kabul etmenin bedeli kullanıcının gördüğünden başka
bir modeli seçmiş olması.
"""
import os
import sys

import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from providers import model_catalog as mc


class _Cevap:
    """`urlopen` baglaminin taklidi — `_read_bounded` boyutlu read istiyor."""

    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")
        self._i = 0

    def read(self, n=None):
        if n is None:
            n = len(self._b)
        parca = self._b[self._i:self._i + n]
        self._i += len(parca)
        return parca

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


BIDI = "\u202e"
LRM = "\u200e"
NUL = "\u0000"


@pytest.mark.parametrize("mid", [
    "gpt-5.6-sol",
    "claude-opus-5",
    "meta/llama-4-70b-instruct",
    "gemini-3.1-flash-lite",
    "a",                       # tek karakter de meşru
    "model.with-dots_and_1",
])
def test_ordinary_model_ids_are_accepted(mid):
    # Kapının ters yönü. Bu liste olmadan "hepsini reddet" de testi geçerdi.
    assert mc.usable_model_id(mid) is True


@pytest.mark.parametrize("mid", [
    "safe" + BIDI + "-txt.exe",
    BIDI + "gpt-5.6",
    "gpt" + LRM + "-5.6",
    "gpt\u2066-5.6",           # isolate
    "gpt\u0007-5.6",           # C0
    "gpt\u009f-5.6",           # C1
    "gpt\n5.6",
    "gpt\t5.6",
    NUL,
])
def test_ids_carrying_control_characters_are_refused(mid):
    assert mc.usable_model_id(mid) is False


@pytest.mark.parametrize("mid", [None, 123, {"id": "x"}, [], "", b"gpt"])
def test_ids_that_are_not_non_empty_strings_are_refused(mid):
    assert mc.usable_model_id(mid) is False


def test_the_anonymous_catalogue_drops_a_hostile_id():
    """En kritik yol: OpenRouter kataloğu ANAHTARSIZ çekiliyor, yani bu satırı
    kim koyarsa koysun kimlik doğrulaması yok."""
    from unittest import mock

    kotu = {"data": [
        {"id": "openai/safe" + BIDI + "-model", "name": "Zararsız"},
        {"id": "openai/gpt-5.6", "name": "İyi"},
    ]}
    mc.clear_cache()
    with mock.patch.object(mc.urllib.request, "urlopen", lambda *a, **k: _Cevap(kotu)):
        katalog = mc.openrouter_catalog(force=True)
    assert katalog is not None
    kimlikler = list(katalog)
    assert not any(BIDI in k for k in kimlikler), kimlikler
    assert any("gpt-5.6" in k for k in kimlikler), "temiz satır da düştü"


def test_a_provider_list_drops_a_hostile_id_but_keeps_the_rest():
    from unittest import mock

    cevap = {"data": [
        {"id": "bad" + BIDI + "one", "display_name": "Kötü"},
        {"id": "good-one", "display_name": "İyi"},
    ]}
    mc.clear_cache()
    with mock.patch.object(mc.urllib.request, "urlopen", lambda *a, **k: _Cevap(cevap)):
        liste = mc.list_models("openai", "sk-x", force=True)
    assert liste is not None
    assert "good-one" in liste
    assert not any(BIDI in k for k in liste), list(liste)
