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

import logging
import os
import stat
import tempfile

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

@pytest.mark.baglar_gerekli
def test_write_refuses_to_follow_a_symlink(tmp_path, token_path):
    """Saldırganın önceden kurduğu bağ sırrı seçtiği dosyaya yönlendiremez."""
    victim = tmp_path / "attacker-chosen.txt"
    victim.write_text("orijinal")
    token_path.symlink_to(victim)

    assert local_token_file.write_local_app_token("s3cret") is False, \
        "bağ üzerinden yazma BAŞARILI oldu — sır saldırganın dosyasına gitti"
    assert victim.read_text() == "orijinal", "kurban dosyanın içeriği değişti"


@pytest.mark.baglar_gerekli
def test_read_refuses_to_follow_a_symlink(tmp_path, token_path):
    """Okuma da bağ takip etmemeli: aksi halde saldırgan SEÇTİĞİ içeriği
    sır diye okutup kendi bildiği bir değeri geçerli kılabilirdi."""
    planted = tmp_path / "planted.txt"
    planted.write_text("saldirganin-bildigi-token")
    token_path.symlink_to(planted)

    assert local_token_file.read_local_app_token() == ""


# ── 2 + 3. Var olan gevşek dosya ────────────────────────────────────────────

@pytest.mark.izin_bitleri_gerekli
def test_existing_loose_file_is_tightened_on_read(token_path):
    """Bu düzeltmenin ASIL değeri mevcut kurulumlarda: dosya çoktan 0644'le
    yaratılmıştı ve yalnız yazma yolunu düzeltmek onu olduğu gibi bırakırdı."""
    token_path.write_text("mevcut-sir")
    os.chmod(token_path, 0o644)

    assert local_token_file.read_local_app_token() == "mevcut-sir"
    assert stat.S_IMODE(os.stat(token_path).st_mode) == 0o600


@pytest.mark.izin_bitleri_gerekli
def test_overwriting_a_loose_file_never_exposes_the_new_secret(token_path):
    """Yazma sırası: aç+boşalt -> fchmod -> yaz. Bytlar hiçbir an 0644'te olmamalı."""
    token_path.write_text("eski")
    os.chmod(token_path, 0o644)

    assert local_token_file.write_local_app_token("yeni-sir")
    assert stat.S_IMODE(os.stat(token_path).st_mode) == 0o600
    assert token_path.read_text() == "yeni-sir"


@pytest.mark.izin_bitleri_gerekli
def test_freshly_created_file_is_owner_only(token_path):
    assert local_token_file.write_local_app_token("s3cret")
    assert stat.S_IMODE(os.stat(token_path).st_mode) == 0o600


# ── 4. Log redaksiyonu ──────────────────────────────────────────────────────

# ── 5. `O_NOFOLLOW` ve izin bitleri OLMAYAN platform — 30 Tem 2026, Windows ──
#
# Bu blok platformdan BAĞIMSIZ koşuyor: modül sabitleri patch'lenerek Windows
# dalı Unix'te de sürülüyor. Sebep ölçülmüş — bu daldaki iki hata yalnız
# Windows'ta ortaya çıkıyordu ve orada testin kendisi de koşamıyordu.

def test_write_survives_missing_o_nofollow(token_path, monkeypatch):
    """`O_NOFOLLOW` yokluğu `AttributeError` SIZDIRMAZ.

    Eski kod bayrağı koşulsuz kullanıyordu; Windows'ta sabit olmadığı için
    `AttributeError` doğuyor ve o bir `OSError` DEĞİL, yani
    `write_local_app_token`'ın `except OSError`'ı onu yakalamıyordu. Ölçülen
    bedeli ürünün tamamı: `main.py` bu fonksiyonu import anında çağırdığı için
    backend Windows'ta hiç ayağa kalkmıyordu.
    """
    monkeypatch.setattr(local_token_file, "_O_NOFOLLOW", 0)
    monkeypatch.setattr(local_token_file, "_POSIX_MODE_BITS", False)

    assert local_token_file.write_local_app_token("s3cret") is True
    assert token_path.read_text() == "s3cret"
    assert local_token_file.read_local_app_token() == "s3cret"


def test_symlink_still_refused_without_o_nofollow(token_path, monkeypatch):
    """Bayrak yokken bağ reddi ikinci hattan geliyor — koruma tamamen düşmüyor.

    Gerçek bir bağ kurulmuyor: Windows'ta bu ayrıcalık istiyor (ölçüldü,
    WinError 1314) ve ölçülen şey bağın varlığı değil, `islink` doğru dönünce
    yazmanın REDDEDİLMESİ.
    """
    monkeypatch.setattr(local_token_file, "_O_NOFOLLOW", 0)
    monkeypatch.setattr(local_token_file, "_POSIX_MODE_BITS", False)
    monkeypatch.setattr(
        os.path, "islink", lambda p: str(p) == str(token_path)
    )

    assert local_token_file.write_local_app_token("s3cret") is False, \
        "bağ olduğu bildirilen yola sır yazıldı"
    assert not token_path.exists(), "reddedilen yazma yine de dosya yarattı"


def test_no_false_hardening_claim_when_mode_bits_are_meaningless(
    token_path, monkeypatch, caplog
):
    """Windows'ta "izni 0600'e çekildi" YALANI basılmıyor.

    Ölçüldü (Python 3.13/win32): `st_mode` `0o666` sabit gelir, `chmod` onu
    değiştirmiyor, ama `fchmod` hata da VERMİYOR. Yani koşul kaldırılırsa kod
    her okumada "sıkılaştırdım" diye uyarı basar ve hiçbir şey yapmaz — bu
    depoda kapatılmış bir sınıf: olmamış işleme "oldu" demek.
    """
    token_path.write_text("s3cret")
    monkeypatch.setattr(local_token_file, "_POSIX_MODE_BITS", False)

    with caplog.at_level(logging.WARNING):
        assert local_token_file.read_secret_file(str(token_path)) == "s3cret"

    yalanlar = [r.getMessage() for r in caplog.records if "0600" in r.getMessage()]
    assert not yalanlar, f"yapılmamış sıkılaştırma iddia edildi: {yalanlar}"


def test_platform_flags_match_measured_reality():
    """Bayraklar SABİT yazılmamış — gerçekten ölçülene uyuyor.

    Mutasyonla bulundu (30 Tem 2026): `_POSIX_MODE_BITS = True` yazmak hiçbir
    testi kırmıyordu, çünkü davranış testleri bayrağı monkeypatch ile kendileri
    zorluyor. Yani "bayrak doğru hesaplanıyor mu" sorusunu kimse sormuyordu —
    ve yanlış hesaplanan bir bayrak, Windows'ta yapılmamış sıkılaştırmayı
    "yapıldı" diye loglamaya geri dönerdi.

    Bu test iki yönde de çalışıyor: Windows'ta `True` yazımını, POSIX'te
    `False` yazımını yakalıyor.
    """
    fd, p = tempfile.mkstemp()
    os.close(fd)
    try:
        os.chmod(p, 0o600)
        chmod_gercekten_etkili = stat.S_IMODE(os.stat(p).st_mode) == 0o600
    finally:
        os.remove(p)

    assert local_token_file._POSIX_MODE_BITS is chmod_gercekten_etkili, \
        "izin biti bayrağı gerçekliğe uymuyor — sabit yazılmış olabilir"
    assert bool(local_token_file._O_NOFOLLOW) is hasattr(os, "O_NOFOLLOW"), \
        "O_NOFOLLOW bayrağı gerçekliğe uymuyor"


def test_o_nofollow_is_still_used_where_the_platform_has_it():
    """TERS YÖN: POSIX'te çekirdek reddi kaybolmadı.

    `getattr(os, "O_NOFOLLOW", 0)` yazımı bir refactor'da sessizce 0'a düşerse
    Unix'te atomik koruma gider ve yalnız TOCTOU'ya açık `islink` kontrolü
    kalır. Tek yönlü bir test bunu göremezdi.
    """
    if os.name != "posix":
        pytest.skip("O_NOFOLLOW yalnız POSIX'te var — bu makinede ölçülemez")
    assert local_token_file._O_NOFOLLOW != 0
    assert local_token_file._POSIX_MODE_BITS is True


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
