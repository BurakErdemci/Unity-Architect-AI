"""Compact CLI oturumunu da küçültmeli — yalnız uygulamanın DB'sini değil.

Arıza (9 Ağu 2026, kullanıcı canlı ölçtü): uygulamada `/compact` atıldı, sohbet
özetlendi, ama hemen ardından `/context` **773k / 1M token (%77)** dedi — yani
compact öncesiyle aynı. Bağlam hiç düşmemişti.

Zincir: compact endpoint'i DB'yi özetliyor ve canlı session'ları `close_session`
ile kapatıyordu, ama `cli_sessions` tablosundaki **resume kimliğine dokunmuyordu.**
Sonraki turda `get_cli_session` o kimliği veriyor → `resume=` → Claude Code
diskteki TAM transcript'i geri yüklüyor. Kapatılan oturum, kapatılmamış gibi
geri geliyordu.

Çifte vuruş: `agent_runner`'da `resume_id` varken compact'in ürettiği özet de
enjekte EDİLMİYOR (aynı konuşmayı iki kez göstermemek için). Yani eski bağlam
geri geliyor, yeni özet hiç gitmiyor.

⚠️ Bu testlerin ölçtüğü şey "fonksiyon çağrıldı" değil, kullanıcıya görünen
sonuç: compact'ten SONRA resume kimliği kalmamalı, çünkü kalırsa bir sonraki tur
büyük bağlamla açılır.
"""
import os
import sys
import tempfile
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from database import DatabaseManager


@pytest.fixture
def db():
    return DatabaseManager(os.path.join(tempfile.mkdtemp(), "t.db"))


# ── Kimlik silme — depo katmanı ──────────────────────────────────────────────

def test_kimlik_silinince_geri_gelmiyor(db):
    db.save_cli_session(7, "claude", "sess-abc", r"C:\ws")
    db.clear_cli_session(7)
    assert db.get_cli_session(7, "claude", r"C:\ws") is None


def test_silme_o_sohbetin_TUM_CLI_lerini_kapsiyor(db):
    """Compact tüm sağlayıcıların canlı oturumunu kapatıyor; kimlikler de
    hepsi için düşmeli. Biri kalırsa o CLI'a geçildiğinde eski bağlam diriliyor."""
    db.save_cli_session(7, "claude", "claude-1", r"C:\ws")
    db.save_cli_session(7, "codex", "codex-1", r"C:\ws")
    db.clear_cli_session(7)
    assert db.get_cli_session(7, "claude", r"C:\ws") is None
    assert db.get_cli_session(7, "codex", r"C:\ws") is None


def test_silme_BASKA_sohbetlere_dokunmuyor(db):
    db.save_cli_session(7, "claude", "yedi", r"C:\ws")
    db.save_cli_session(8, "claude", "sekiz", r"C:\ws")
    db.clear_cli_session(7)
    assert db.get_cli_session(8, "claude", r"C:\ws") == "sekiz"


def test_kimliksiz_sohbette_silme_COKMEZ(db):
    db.clear_cli_session(999)  # istisna atmamalı


def test_sohbet_silinince_kimlik_de_gidiyor(db):
    """Çöp temizliği. `conversations.id` AUTOINCREMENT olduğu için yetim kayıt
    YANLIŞ geçmiş gösteremez; ölçtüğümüz şey doğruluk değil, birikme."""
    conv_id = db.create_conversation(1, "test")
    db.save_cli_session(conv_id, "claude", "sess-abc", r"C:\ws")
    db.delete_conversation(conv_id)
    assert db.get_cli_session(conv_id, "claude", r"C:\ws") is None


# ── Asıl nöbetçi: compact endpoint'i ─────────────────────────────────────────

def _client(db):
    from routes.conversation_routes import create_conversation_router

    app = FastAPI()
    app.include_router(create_conversation_router(db, {}))
    return TestClient(app)


def test_COMPACT_SONRASI_resume_kimligi_KALMIYOR(db):
    """⭐ Regresyonun asıl nöbetçisi.

    Bu satır kırmızıya dönerse belirti şudur: kullanıcı compact atar, sohbet
    özetlenmiş görünür, ama bir sonraki mesajda model hâlâ tüm eski konuşmayı
    taşır ve `/context` düşmez.
    """
    conv_id = db.create_conversation(1, "test")
    for i in range(8):  # endpoint 6 mesajın altını "çok kısa" diye atlıyor
        db.add_message(conv_id, "user" if i % 2 == 0 else "assistant", f"mesaj {i}")
    db.save_cli_session(conv_id, "claude", "sess-eski", r"C:\ws")

    # AI özetleme yolunu deterministik yap: patlasın, mekanik özete düşsün.
    with patch("routes.conversation_routes.AIProviderManager.get_provider",
               side_effect=RuntimeError("test: AI yok")), \
         patch("routes.conversation_routes.require_conversation_owner",
               return_value=(1, None)):
        with _client(db) as client:
            r = client.post(f"/conversations/{conv_id}/compact",
                            headers={"X-Session-Token": "t"})

    assert r.status_code == 200, r.text
    assert db.get_cli_session(conv_id, "claude", r"C:\ws") is None, (
        "compact sonrası resume kimliği duruyor → sonraki tur Claude Code'un "
        "TAM transcript'ini geri yükler ve bağlam hiç düşmez"
    )


def test_KISA_sohbette_de_CLI_oturumu_sifirlaniyor(db):
    """⭐ Arızanın ikinci yarısı (9 Ağu, canlı ölçüldü).

    Kullanıcı compact'e bastı, *"Sohbet çok kısa, özetlemeye gerek yok"* toast'ı
    çıktı — ama `/context` hâlâ **773k / 1M (%77)** diyordu. Sebep: bir önceki
    compact DB'yi zaten temizlemişti (geriye tek özet mesajı kaldı), yani DB
    kısaydı; CLI oturumu ise DOLUYDU. Kısa-devre koşulu DB mesaj sayısını
    ölçüyor, oysa compact'in kullanıcı için anlamı CLI bağlamının düşmesi.

    Yani "özetlenecek bir şey yok" ile "sıfırlanacak bir şey yok" AYNI ŞEY DEĞİL.
    """
    conv_id = db.create_conversation(1, "test")
    db.add_message(conv_id, "assistant", "📝 **Sohbet özetlendi.**\n\nönceki tur")
    db.save_cli_session(conv_id, "claude", "sess-dolu", r"C:\ws")

    with patch("routes.conversation_routes.require_conversation_owner",
               return_value=(1, None)):
        with _client(db) as client:
            r = client.post(f"/conversations/{conv_id}/compact",
                            headers={"X-Session-Token": "t"})

    assert r.status_code == 200, r.text
    assert db.get_cli_session(conv_id, "claude", r"C:\ws") is None, (
        "kısa sohbette erken dönülüyor ve resume kimliği kalıyor → kullanıcı "
        "compact'e basıyor, 'çok kısa' toast'ı görüyor, bağlam %77'de kalıyor"
    )
