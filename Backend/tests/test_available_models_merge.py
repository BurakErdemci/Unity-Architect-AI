"""Elle yazılı bulut kataloğu + canlı liste = üç ayrı hâl.

Katalog SİLİNMİYOR çünkü küratörlü bilgi taşıyor (görünen ad, OpenRouter
karşılığı, ücretli işareti) ve hiçbir `/v1/models` cevabında bunlar yok.
Canlı liste ise tek bir soruyu cevaplıyor: bu hesap gerçekten neye erişiyor.

Testlerin sabitlediği asıl şey, üç hâlin BİRBİRİNE karışmaması:
  erişilebilir · erişilemez · bilinmiyor.
Üçüncüsü ikinciye çökerse, ağı olmayan bir makinede çalışan her model
"erişemiyorsun" diye görünür.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from routes.config_routes import create_config_router


def _db(anahtarlar: dict):
    db = MagicMock()
    db.get_api_key.side_effect = lambda _uid, saglayici: anahtarlar.get(saglayici, "")
    return db


def _katalog(anahtarlar: dict, canli: dict, refresh: bool = False):
    """`canli`: saglayici -> ({id: ad} | None). Sözlükte olmayan hiç sorulmaz."""
    router = create_config_router(_db(anahtarlar))
    route = next(r for r in router.routes if r.path == "/available-models")

    def sahte(saglayici, _anahtar, force=False):
        return canli.get(saglayici)

    # Ollama çağrısı da ağ: yerel uç yoksa zaten düşüyor ama testi makinenin
    # durumuna bağlamamak için kapatılıyor.
    with patch("providers.model_catalog.list_models", side_effect=sahte), \
         patch("urllib.request.urlopen", side_effect=OSError("kapalı")):
        return asyncio.run(route.endpoint(refresh=refresh))


def _bul(cloud, mid, saglayici):
    return next(m for m in cloud if m["id"] == mid and m["provider"] == saglayici)


def test_a_catalog_model_the_account_has_is_marked_available():
    sonuc = _katalog({"anthropic": "sk-x"}, {"anthropic": {"claude-opus-5": "Claude Opus 5"}})
    assert _bul(sonuc["cloud"], "claude-opus-5", "anthropic")["available"] is True
    assert sonuc["cloud_sources"]["anthropic"] == "live"


def test_a_catalog_model_the_account_lacks_is_marked_unavailable():
    sonuc = _katalog({"anthropic": "sk-x"}, {"anthropic": {"claude-opus-5": "Claude Opus 5"}})
    assert _bul(sonuc["cloud"], "claude-haiku-4-5", "anthropic")["available"] is False


def test_an_unreachable_provider_leaves_availability_UNSET_not_false():
    # Bu testin tamamı bu satır için var: bilinmezlik "erişemiyorsun" değil.
    sonuc = _katalog({"anthropic": "sk-x"}, {"anthropic": None})
    model = _bul(sonuc["cloud"], "claude-opus-5", "anthropic")
    assert "available" not in model
    assert sonuc["cloud_sources"]["anthropic"] == "unknown"


def test_a_provider_without_a_key_is_reported_as_such_not_as_a_failure():
    sonuc = _katalog({}, {})
    assert sonuc["cloud_sources"]["openai"] == "no_key"
    assert "available" not in _bul(sonuc["cloud"], "gpt-5.5", "openai")


def test_a_model_only_the_account_has_is_added_so_a_new_release_needs_no_deploy():
    sonuc = _katalog({"openai": "sk-x"}, {"openai": {"gpt-6-yeni": "GPT-6 Yeni"}})
    yeni = _bul(sonuc["cloud"], "gpt-6-yeni", "openai")
    assert yeni["name"] == "GPT-6 Yeni"
    assert yeni["source"] == "live"
    assert yeni["available"] is True


def test_a_live_entry_never_overwrites_the_curated_one():
    # Katalogdaki satır openrouter karşılığını taşıyor; canlı cevap taşımıyor.
    # Canlı liste kazansa o bilgi sessizce düşerdi.
    sonuc = _katalog({"openai": "sk-x"}, {"openai": {"gpt-5.5": "gpt-5.5"}})
    eslesenler = [m for m in sonuc["cloud"] if m["id"] == "gpt-5.5" and m["provider"] == "openai"]
    assert len(eslesenler) == 1
    assert eslesenler[0]["name"] == "GPT-5.5"
    assert eslesenler[0]["openrouter_id"] == "openai/gpt-5.5"
    assert eslesenler[0]["source"] == "catalog"


def test_one_provider_being_down_does_not_hide_another_provider_state():
    sonuc = _katalog(
        {"openai": "sk-x", "anthropic": "sk-y"},
        {"openai": None, "anthropic": {"claude-opus-5": "Claude Opus 5"}},
    )
    assert sonuc["cloud_sources"]["openai"] == "unknown"
    assert sonuc["cloud_sources"]["anthropic"] == "live"
    assert _bul(sonuc["cloud"], "claude-opus-5", "anthropic")["available"] is True
    assert "available" not in _bul(sonuc["cloud"], "gpt-5.5", "openai")


def test_the_subscription_list_is_untouched_by_cloud_liveness():
    # Abonelik CLI'ları bu yoldan hiç geçmiyor; oradaki listelerin canlılığı
    # ayrı bir uçtan (`/cli-models/{cli}`) geliyor.
    sonuc = _katalog({"openai": "sk-x"}, {"openai": {"gpt-5.5": "gpt-5.5"}})
    assert all("available" not in m for m in sonuc["subscription"])
