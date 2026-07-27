"""Sır dosyalarının izin ve bağ davranışı — 2026-07-27 ikinci denetiminin bulguları.

Dört ayrı bulgu, tek kök: sır yazan iki yol (backend bearer'ı ve Unity MCP
paylaşımlı sırrı) dosya sistemini fazla güveniyordu.

  1. secret-write-symlink-follow   — yazıcı sembolik bağı takip ediyordu
  2. insecure-secret-file-mode     — var olan 0644 dosya hiç sıkılaştırılmıyordu
  3. write-before-permission-tightening — bytlar önce yazılıp sonra chmod ediliyordu
  4. secret-in-log                 — başarısız kayıt denemesi sırrı loga yazıyordu

Probe'lar diskte kaldı; buraya giren şey onların İDDİASI. Bir düzeltme geri
alınırsa bu testler kırmızıya döner — probe'ları kimse yeniden koşturmasa bile.
"""

import os
import stat

import pytest

import local_token_file
from secret_redaction import redact_secrets


@pytest.fixture
def token_path(tmp_path, monkeypatch):
    p = tmp_path / "local-app-token"
    monkeypatch.setattr(local_token_file, "_TOKEN_DIR", str(tmp_path))
    monkeypatch.setattr(local_token_file, "_TOKEN_PATH", str(p))
    monkeypatch.delenv("LOCAL_APP_TOKEN", raising=False)
    return p


# ── 1. Sembolik bağ takibi ──────────────────────────────────────────────────

def test_write_refuses_to_follow_a_symlink(tmp_path, token_path):
    """Saldırganın önceden kurduğu bağ sırrı seçtiği dosyaya yönlendiremez."""
    victim = tmp_path / "attacker-chosen.txt"
    victim.write_text("orijinal")
    token_path.symlink_to(victim)

    assert local_token_file.write_local_app_token("s3cret") is False, \
        "bağ üzerinden yazma BAŞARILI oldu — sır saldırganın dosyasına gitti"
    assert victim.read_text() == "orijinal", "kurban dosyanın içeriği değişti"


def test_read_refuses_to_follow_a_symlink(tmp_path, token_path):
    """Okuma da bağ takip etmemeli: aksi halde saldırgan SEÇTİĞİ içeriği
    sır diye okutup kendi bildiği bir değeri geçerli kılabilirdi."""
    planted = tmp_path / "planted.txt"
    planted.write_text("saldirganin-bildigi-token")
    token_path.symlink_to(planted)

    assert local_token_file.read_local_app_token() == ""


# ── 2 + 3. Var olan gevşek dosya ────────────────────────────────────────────

def test_existing_loose_file_is_tightened_on_read(token_path):
    """Bu düzeltmenin ASIL değeri mevcut kurulumlarda: dosya çoktan 0644'le
    yaratılmıştı ve yalnız yazma yolunu düzeltmek onu olduğu gibi bırakırdı."""
    token_path.write_text("mevcut-sir")
    os.chmod(token_path, 0o644)

    assert local_token_file.read_local_app_token() == "mevcut-sir"
    assert stat.S_IMODE(os.stat(token_path).st_mode) == 0o600


def test_overwriting_a_loose_file_never_exposes_the_new_secret(token_path):
    """Yazma sırası: aç+boşalt -> fchmod -> yaz. Bytlar hiçbir an 0644'te olmamalı."""
    token_path.write_text("eski")
    os.chmod(token_path, 0o644)

    assert local_token_file.write_local_app_token("yeni-sir")
    assert stat.S_IMODE(os.stat(token_path).st_mode) == 0o600
    assert token_path.read_text() == "yeni-sir"


def test_freshly_created_file_is_owner_only(token_path):
    assert local_token_file.write_local_app_token("s3cret")
    assert stat.S_IMODE(os.stat(token_path).st_mode) == 0o600


# ── 4. Log redaksiyonu ──────────────────────────────────────────────────────

def test_mcp_url_secret_is_redacted():
    """Asıl arıza: CalledProcessError.str() komut listesinin tamamını taşıyor."""
    err = ("Command '['codex', 'mcp', 'add', '--env', "
           "'UNITY_MCP_URL=http://127.0.0.1:8080/mcp/Ab3xK9mQ2pL7vN4tR8wY1zC5', "
           "'--']' returned non-zero exit status 1.")
    out = redact_secrets(err)
    assert "Ab3xK9mQ2pL7vN4tR8wY1zC5" not in out
    assert "/mcp/<REDACTED>" in out
    # Teşhis bilgisi KORUNMALI — sırf sır var diye hatayı atmak da bir kayıp.
    assert "codex" in out and "non-zero exit status 1" in out


def test_env_assignment_secrets_are_redacted():
    for raw in ("LOCAL_APP_TOKEN=s3cr3t", "ANTHROPIC_API_KEY=sk-abc123",
                "MY_SECRET=hunter2"):
        assert redact_secrets(raw).endswith("=<REDACTED>"), raw


def test_ordinary_text_is_left_alone():
    """Bu yön olmadan her şeyi <REDACTED> yapan bir fonksiyon da testi geçerdi
    ve logları teşhis için işe yaramaz hale getirirdi."""
    plain = "connection refused: http://127.0.0.1:8080/health"
    assert redact_secrets(plain) == plain
    assert redact_secrets("/mcp/hub/plugin") == "/mcp/hub/plugin"
