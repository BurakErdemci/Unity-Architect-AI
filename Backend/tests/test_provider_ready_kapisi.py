"""Sohbet kapısı: `/provider-ready` — seçili sağlayıcı GERÇEKTEN kullanılabilir mi?

Ürün kararı (8 Ağu 2026): kullanıcıya hiçbir şey habersiz kurulmuyor, dolayısıyla
sağlayıcısı olmayan kullanıcı bozuk bir sohbete düşmemeli. Sohbet bu uca göre
kilitleniyor, yani bu uç yanlış cevap verdiğinde ya çalışan bir kurulum kilitlenir
ya da kullanıcı ham bir istisnayla karşılaşır. İki yön de burada sınanıyor.
"""
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(db):
    from routes.config_routes import create_config_router

    app = FastAPI()
    app.include_router(create_config_router(db))
    return TestClient(app, raise_server_exceptions=False)


def _db(provider_type, model_name, api_key=""):
    db = MagicMock()
    db.get_ai_config.return_value = (provider_type, model_name, "", "")
    db.get_api_key.return_value = api_key
    return db


def _sor(db):
    r = _client(db).get("/provider-ready/1", headers={"X-Session-Token": "t"})
    assert r.status_code == 200, r.text
    return r.json()


# ── Bulut sağlayıcılar: anahtar şart ─────────────────────────────────────────

def test_anahtari_olmayan_bulut_saglayicisi_sohbeti_ACMIYOR():
    d = _sor(_db("anthropic", "claude-opus-4-6", api_key=""))
    assert d["ready"] is False
    assert d["needs"] == "apikey"
    assert d["kind"] == "api"


def test_anahtari_olan_bulut_saglayicisi_sohbeti_ACIYOR():
    """KARŞIT YÖN — bu testin kırılması, anahtarını girmiş kullanıcının
    sohbetinin kilitli kalması demektir."""
    d = _sor(_db("anthropic", "claude-opus-4-6", api_key="sk-ant-xxx"))
    assert d["ready"] is True
    assert d["needs"] is None


# ── CLI sağlayıcılar ─────────────────────────────────────────────────────────

@pytest.fixture
def cli_durumu(monkeypatch):
    """`cli_doctor`ın gördüğü dünyayı kurar. Doctor bir closure olduğu için
    doğrudan yamalanamıyor; dayandığı tespit fonksiyonları yamalanıyor."""
    from routes import config_routes as cr
    from providers import oneshot_cli

    kutu = {"installed": True}
    monkeypatch.setattr(
        cr, "_resolve_general_cli", lambda ad: "/bin/x" if kutu["installed"] else None
    )
    monkeypatch.setattr(oneshot_cli, "cli_installed", lambda ad: kutu["installed"])
    return kutu


def test_kurulu_olmayan_CLI_sohbeti_ACMIYOR(cli_durumu):
    cli_durumu["installed"] = False
    d = _sor(_db("subscription", "claude-sonnet-4-6"))
    assert d["ready"] is False
    assert d["needs"] == "install"
    assert d["kind"] == "cli"
    assert d["provider"] == "claude"


def test_kurulu_CLI_sohbeti_ACIYOR(cli_durumu):
    cli_durumu["installed"] = True
    d = _sor(_db("subscription", "claude-sonnet-4-6"))
    assert d["ready"] is True
    assert d["needs"] is None


def test_model_adi_DOGRU_CLI_ailesine_esleniyor(cli_durumu):
    """Aile eşlemesi elde yazılmıyor, `env_family` ile yapılıyor. Bu test o bağı
    sabitliyor: yanlış aileye bakan bir kapı, kurulu olmayan bir CLI'ı 'hazır'
    gösterebilir."""
    cli_durumu["installed"] = True
    assert _sor(_db("subscription", "gpt-5.6-codex"))["provider"] == "codex"
    assert _sor(_db("subscription", "gemini-3.6-flash"))["provider"] == "agy"


def test_giris_yapilmadigi_OLCULDUYSE_sohbet_ACILMIYOR(cli_durumu, monkeypatch):
    from routes import config_routes as cr

    cli_durumu["installed"] = True
    # cursor'ın giriş probe'u ölçüyor ve "giriş yok" diyor.
    async def _yok(cmd, family, timeout=10):
        return "not logged in"
    monkeypatch.setattr(cr, "_run_cli_capture", _yok)
    monkeypatch.setattr(cr, "resolve_cli_cmd", lambda ad: ["/bin/cursor"], raising=False)

    d = _sor(_db("subscription", "cursor-composer"))
    assert d["provider"] == "cursor"
    assert d["needs"] == "login"
    assert d["ready"] is False


def test_giris_durumu_OLCULEMEYEN_CLI_kilitlenmiyor(cli_durumu):
    """⭐ ASİMETRİ — bilmemek yokluk değildir.

    `claude`, `codex`, `agy`, `kimi` için `loggedIn` ÖLÇÜLMÜYOR (sabit None).
    None'ı "giriş yapılmamış" saymak, çalışan bir kurulumu olan kullanıcının
    sohbetini kilitlerdi — yani kapı, çözmek istediği problemin aynısını üretirdi.
    Bu test o yönü sabitliyor.
    """
    cli_durumu["installed"] = True
    d = _sor(_db("subscription", "claude-sonnet-4-6"))
    assert d["ready"] is True, "loggedIn=None kilitlemeye yol açmamalı"


# ── Ollama: kurulu olması yetmez, AYAKTA olmalı ──────────────────────────────

@pytest.fixture
def ollama(monkeypatch):
    """Ollama probe'unu KONTROL ALTINA alır.

    İlk yazımda bu testler gerçek `localhost:11434`'e çıkıyordu ve bu makinede
    Ollama AÇIK olduğu için "ayakta değil" testi yeşil sanılırken yanlış sebeple
    kırmızıydı. Ortama bağlı bir test, ölçtüğünü sandığı şeyi ölçmüyor.
    """
    import httpx

    kutu = {"ayakta": False}

    class _Yanit:
        status_code = 200

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            if not kutu["ayakta"]:
                raise httpx.ConnectError("baglanti yok")
            return _Yanit()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    return kutu


def test_ayakta_olmayan_ollama_sohbeti_ACMIYOR(ollama):
    ollama["ayakta"] = False
    d = _sor(_db("ollama", "llama3"))
    assert d["ready"] is False
    assert d["needs"] == "service"
    assert d["kind"] == "local"


def test_ayakta_olan_ollama_sohbeti_ACIYOR(ollama):
    """KARŞIT YÖN: Ollama'sı çalışan kullanıcının sohbeti kilitlenmemeli."""
    ollama["ayakta"] = True
    d = _sor(_db("ollama", "llama3"))
    assert d["ready"] is True
    assert d["needs"] is None


# ── i18n kararının nöbetçisi ─────────────────────────────────────────────────

def test_uc_METIN_dondurmuyor_yalnizca_KOD():
    """Backend'de kullanıcıya görünen ~300 sabit Türkçe metin var ve çeviri
    mekanizması YOK. Bu uç bilerek cümle döndürmüyor; metni frontend kendi
    sözlüğünden kuruyor. Buraya bir gün 'message' eklenirse aynı borç büyür —
    bu test onu yakalar.
    """
    d = _sor(_db("anthropic", "claude-opus-4-6", api_key=""))
    assert set(d.keys()) == {"ready", "kind", "provider", "needs"}
    assert d["needs"] in (None, "apikey", "install", "login", "service")
    assert d["kind"] in ("api", "cli", "local")
