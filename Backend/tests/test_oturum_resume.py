"""Kaldığın yerden devam: kimlik saklanıyor, geri veriliyor, SDK'ya ulaşıyor.

Arıza (8 Ağu 2026, gerçek sohbette ölçüldü): uygulama yeniden başlayınca CLI
oturumu ölüyor ve geçmiş yalnız 20.000 karakterlik bir DB enjeksiyonuyla geri
veriliyordu — 48 mesajın 17'si geçti, karakterlerin **%71'i** kayboldu. CLI ise
tam transcript'i kendi diskinde tutuyor; tek eksik onu geri çağıracak kimlikti.
"""
import asyncio
import os
import tempfile

import pytest

from database import DatabaseManager
from routes.conversation_routes import _oturum_saglayici_anahtari


@pytest.fixture
def db():
    return DatabaseManager(os.path.join(tempfile.mkdtemp(), "t.db"))


# ── Kimlik deposu ────────────────────────────────────────────────────────────

def test_kimlik_saklanip_geri_veriliyor(db):
    db.save_cli_session(7, "claude", "sess-abc", r"C:\ws")
    assert db.get_cli_session(7, "claude", r"C:\ws") == "sess-abc"


def test_WORKSPACE_degistiyse_kimlik_KULLANILMIYOR(db):
    """⭐ Bu testin koruduğu şey bir veri kaybı değil, YANLIŞ VERİ gösterimi.

    CLI oturumları proje diziniyle anahtarlı. Başka klasörde açılmış bir kimliği
    resume etmek, kullanıcıya BAŞKA BİR PROJENİN geçmişini açardı — sessizce.
    """
    db.save_cli_session(7, "claude", "sess-abc", r"C:\proje-A")
    assert db.get_cli_session(7, "claude", r"C:\proje-B") is None


def test_ayni_sohbette_FARKLI_CLI_lerin_kimlikleri_karismiyor(db):
    """Aynı sohbette Claude'dan Codex'e geçilebiliyor; biri diğerinin kimliğiyle
    resume edilmeye çalışılırsa oturum hiç açılmaz."""
    db.save_cli_session(7, "claude", "claude-1", r"C:\ws")
    db.save_cli_session(7, "codex", "codex-1", r"C:\ws")
    assert db.get_cli_session(7, "claude", r"C:\ws") == "claude-1"
    assert db.get_cli_session(7, "codex", r"C:\ws") == "codex-1"


def test_uzerine_yaziliyor_ikinci_kayit_birikmıyor(db):
    db.save_cli_session(7, "claude", "eski", r"C:\ws")
    db.save_cli_session(7, "claude", "yeni", r"C:\ws")
    assert db.get_cli_session(7, "claude", r"C:\ws") == "yeni"


def test_kimlik_yoksa_None_COKMEZ(db):
    assert db.get_cli_session(999, "claude", r"C:\ws") is None


# ── Sağlayıcı anahtarı ───────────────────────────────────────────────────────

def test_abonelik_yolunda_anahtar_CLI_AILESI(db):
    assert _oturum_saglayici_anahtari("subscription", "claude-sonnet-5") == "claude"
    assert _oturum_saglayici_anahtari("subscription", "gpt-5.6-codex") == "codex"
    assert _oturum_saglayici_anahtari("subscription", "gemini-3.6-flash") == "agy"


def test_bulut_yolunda_anahtar_SAGLAYICI_TIPI(db):
    assert _oturum_saglayici_anahtari("anthropic", "claude-opus-5") == "anthropic"


# ── Kimlik GERÇEKTEN SDK'ya ulaşıyor mu ──────────────────────────────────────

def _secenekler(resume_id):
    """`start()`'ı gerçekten koşturup SDK'ya giden options'ı yakalar.

    Kaynak taraması değil DAVRANIŞ: bu depoda "fonksiyon şu dizeyi içeriyor"
    diyen testlerin mutasyona kör olduğu birden çok kez ölçüldü.
    """
    import claude_agent_sdk
    from providers.claude_sdk_session import ClaudeSDKSession

    yakalanan = {}

    class _SahteClient:
        def __init__(self, options=None):
            yakalanan["options"] = options

        async def __aenter__(self):
            return self

        async def receive_messages(self):
            # `start()` bir reader görevi başlatıyor. Bu stub OLMAZSA görev
            # AttributeError'la düşüyor ve test, kendi iddiası yerine o gürültüyle
            # kırmızıya dönüyordu — yani mutasyona duyarlı ama sebebi YANLIŞ bir
            # test olurdu. Ölçüldü: mutasyon turunda tam bu oldu.
            if False:
                yield {}
            return

    gercek = claude_agent_sdk.ClaudeSDKClient
    claude_agent_sdk.ClaudeSDKClient = _SahteClient
    try:
        asyncio.run(ClaudeSDKSession(conversation_id=1, resume_id=resume_id).start())
    finally:
        claude_agent_sdk.ClaudeSDKClient = gercek
    return yakalanan["options"]


def test_kimlik_SDK_ye_resume_olarak_ulasiyor():
    o = _secenekler("sess-xyz")
    assert getattr(o, "resume", None) == "sess-xyz"


def test_kimlik_YOKSA_resume_HIC_verilmiyor():
    """KARŞIT YÖN: boş bir `resume` göndermek SDK'nın kendi davranışını bozabilir;
    anahtar hiç konmamalı."""
    o = _secenekler(None)
    assert not getattr(o, "resume", None)
