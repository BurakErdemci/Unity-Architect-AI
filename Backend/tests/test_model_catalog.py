"""Canlı model listesi — ve BİLİNMEZLİĞİN ayrı bir hâl olarak korunması.

Bu akışın merkez tasarım kararı şu: bir sağlayıcıdan liste alınamadığında
sonuç boş küme DEĞİL `None`. Boş küme "hesabında hiç model yok" demek olurdu
ve ağı olmayan bir makinede katalogdaki her satırı "erişemiyorsun" diye
gösterirdi — yanlış kırmızının en pahalı biçimi, çünkü kullanıcı çalışan bir
modeli denemekten vazgeçer.

Bir de ölçülmüş bir tuzak sabitleniyor (30 Ağu 2026): testlerdeki sahte
veritabanı anahtar yerine mock döndürüyor ve mock truthy. `isinstance` kapısı
konmadan önce `test_anthropic_models.py` sessizce GERÇEK ağ çağrıları yapıyordu
— ölçüldü, dosyanın süresi 6,14 sn'den 3,34 sn'ye düştü.
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from providers import model_catalog


@pytest.fixture(autouse=True)
def temiz_onbellek():
    model_catalog.clear_cache()
    yield
    model_catalog.clear_cache()


class _Cevap:
    """`urlopen` bağlam yöneticisinin ihtiyaç duyulan kadarı."""

    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ─── Ağa hiç çıkmaması gereken durumlar ────────────────────────────────────


def test_unknown_provider_never_reaches_the_network():
    with patch("urllib.request.urlopen") as urlopen:
        assert model_catalog.list_models("bilinmeyen", "sk-test") is None
    urlopen.assert_not_called()


def test_a_mock_shaped_key_is_not_a_key():
    # Kapının var olma sebebi: mock truthy, ve onsuz birim testleri dışarı
    # istek atıyordu.
    with patch("urllib.request.urlopen") as urlopen:
        assert model_catalog.list_models("openai", MagicMock()) is None
    urlopen.assert_not_called()


def test_empty_key_never_reaches_the_network():
    with patch("urllib.request.urlopen") as urlopen:
        assert model_catalog.list_models("openai", "") is None
    urlopen.assert_not_called()


# ─── Cevap şekilleri ────────────────────────────────────────────────────────


def test_openai_shape_is_read_as_id_to_name():
    payload = {"data": [{"id": "gpt-5.5"}, {"id": "gpt-5.4-mini"}]}
    with patch("urllib.request.urlopen", return_value=_Cevap(payload)):
        assert model_catalog.list_models("openai", "sk-x") == {
            "gpt-5.5": "gpt-5.5", "gpt-5.4-mini": "gpt-5.4-mini",
        }


def test_anthropic_display_name_is_preferred_when_present():
    payload = {"data": [{"id": "claude-opus-5", "display_name": "Claude Opus 5"}]}
    with patch("urllib.request.urlopen", return_value=_Cevap(payload)):
        assert model_catalog.list_models("anthropic", "sk-x") == {"claude-opus-5": "Claude Opus 5"}


def test_google_ids_lose_their_models_prefix():
    payload = {"models": [{"name": "models/gemini-3.6-flash", "displayName": "Gemini 3.6 Flash"}]}
    with patch("urllib.request.urlopen", return_value=_Cevap(payload)):
        assert model_catalog.list_models("google", "k") == {"gemini-3.6-flash": "Gemini 3.6 Flash"}


# ─── Bilinmezlik ────────────────────────────────────────────────────────────


def test_an_unreadable_body_is_unknown_rather_than_empty():
    # Şema değişirse ayrıştırma boş çıkar. Onu "model yok" diye taşımak
    # katalogdaki her satırı erişilemez gösterirdi.
    with patch("urllib.request.urlopen", return_value=_Cevap({"beklenmedik": 1})):
        assert model_catalog.list_models("openai", "sk-x") is None


def test_a_failing_call_is_unknown_and_does_not_raise():
    with patch("urllib.request.urlopen", side_effect=OSError("ağ yok")):
        assert model_catalog.list_models("openai", "sk-x") is None


def test_the_api_key_is_never_written_to_the_log(caplog):
    with patch("urllib.request.urlopen", side_effect=OSError("bağlanılamadı")):
        model_catalog.list_models("openai", "sk-COK-GIZLI-ANAHTAR")
    assert "sk-COK-GIZLI-ANAHTAR" not in caplog.text


# ─── Anahtarın doğru uca gitmesi ────────────────────────────────────────────


def test_each_key_only_ever_reaches_its_own_provider_endpoint():
    """Bir sağlayıcının anahtarı başka bir sağlayıcının ucuna gidemez.

    Yapısal olarak imkânsız (aynı ad hem anahtarı hem ucu seçiyor) ama bu
    depoda sır sızıntısı ölçülmüş bir arıza sınıfı, o yüzden yapıya değil
    DAVRANIŞA bakan bir kapı bırakılıyor.
    """
    for saglayici in model_catalog.supported_providers():
        model_catalog.clear_cache()
        with patch("urllib.request.urlopen", return_value=_Cevap({"data": [{"id": "m"}]})) as urlopen:
            model_catalog.list_models(saglayici, f"anahtar-{saglayici}")
        istek = urlopen.call_args[0][0]
        gonderilen = json.dumps(dict(istek.headers))
        assert f"anahtar-{saglayici}" in gonderilen
        for digeri in model_catalog.supported_providers():
            if digeri != saglayici:
                assert f"anahtar-{digeri}" not in gonderilen


# ─── Önbellek ───────────────────────────────────────────────────────────────


def test_a_second_call_inside_the_ttl_does_not_hit_the_network_again():
    with patch("urllib.request.urlopen", return_value=_Cevap({"data": [{"id": "m"}]})) as urlopen:
        model_catalog.list_models("openai", "sk-x")
        model_catalog.list_models("openai", "sk-x")
    assert urlopen.call_count == 1


def test_force_bypasses_the_cache_or_refresh_means_nothing():
    with patch("urllib.request.urlopen", return_value=_Cevap({"data": [{"id": "m"}]})) as urlopen:
        model_catalog.list_models("openai", "sk-x")
        model_catalog.list_models("openai", "sk-x", force=True)
    assert urlopen.call_count == 2


def test_a_failed_lookup_is_cached_too_so_a_dead_endpoint_is_not_retried_per_request():
    with patch("urllib.request.urlopen", side_effect=OSError("yok")) as urlopen:
        assert model_catalog.list_models("openai", "sk-x") is None
        assert model_catalog.list_models("openai", "sk-x") is None
    assert urlopen.call_count == 1
