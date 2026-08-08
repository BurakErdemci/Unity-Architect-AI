"""Windows'ta npm kabuğunun arkasındaki gerçek `claude.exe` bulunmalı.

Saha arızası (8 Ağu 2026, v3.0.0 kurulduktan sonra kullanıcıda): gömülü
`claude.exe` paketten çıkarılınca SDK PATH'e düştü, ama Claude Code'un npm
kurulumu PATH'e yalnız `claude.cmd` koyuyor ve SDK toplu-iş kabuğu çalıştırmayı
BİLEREK reddediyor (cmd.exe argüman enjeksiyonu). Sonuç: Claude Code KURULU
olduğu hâlde oturum açılmıyordu —

    Refusing to execute batch script '…\\claude.CMD'

⚠️ Bu dosyadaki testler GERÇEK makineye BAKMAZ. `shutil.which` ve dosya sistemi
tamamen kontrol altında. Sebep bugün iki kez ölçüldü: gerçek ortama bakan bir
test, o makinede tesadüfen doğru olan bir şey yüzünden geçiyor ve başka bir
makinede (ya da CI'da) çöküyor — yani ölçtüğünü sanmıyor.
"""
import os
import sys
import pytest

from providers import claude_sdk_session as css

KABUK_ICERIGI = (
    '@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n'
    ':start\r\nSETLOCAL\r\nCALL :find_dp0\r\n'
    '"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\bin\\claude.exe"   %*\r\n'
)


@pytest.fixture
def win(monkeypatch):
    """Platformu Windows'a sabitler; `which` sonucunu test belirler."""
    monkeypatch.setattr(sys, "platform", "win32")
    kutu = {"claude": None, "claude.exe": None}
    monkeypatch.setattr(css.__dict__.get("shutil", __import__("shutil")),
                        "which", lambda ad: kutu.get(ad))
    return kutu


def test_windows_disinda_KARISMIYOR(monkeypatch):
    """`.cmd` sorunu yalnız Windows'ta var; başka platformda SDK'nın kendi
    arama sırasına dokunmamak gerekiyor."""
    monkeypatch.setattr(sys, "platform", "darwin")
    assert css.claude_ikilisini_coz() is None


def test_PATH_te_native_exe_varsa_dogrudan_kullanilir(win):
    win["claude.exe"] = r"C:\tools\claude.exe"
    assert css.claude_ikilisini_coz() == r"C:\tools\claude.exe"


def test_kabugun_ICINDEKI_yol_okunuyor(win, tmp_path):
    """En doğru yol: hedef kabuğun içinde düz metin yazıyor, tahmin gerekmiyor."""
    kabuk = tmp_path / "claude.cmd"
    kabuk.write_text(KABUK_ICERIGI, encoding="utf-8")
    hedef = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    hedef.parent.mkdir(parents=True)
    hedef.write_bytes(b"MZ")            # gerçek dosya OLMALI, yoksa aday reddedilir
    win["claude"] = str(kabuk)

    assert css.claude_ikilisini_coz() == os.path.normpath(str(hedef))


def test_kabuk_OKUNAMAZ_hale_gelse_bile_bilinen_yerlesim_deneniyor(win, tmp_path):
    """KARŞIT YÖN: kabuk beklenmedik biçimdeyse tek dayanak kalmamalı."""
    kabuk = tmp_path / "claude.cmd"
    kabuk.write_text("@echo off\r\nrem hicbir yol yok\r\n", encoding="utf-8")
    hedef = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    hedef.parent.mkdir(parents=True)
    hedef.write_bytes(b"MZ")
    win["claude"] = str(kabuk)

    assert css.claude_ikilisini_coz() == str(hedef)


def test_hicbir_sey_bulunamazsa_None_doner_COKMEZ(win, tmp_path):
    """None = "SDK kendi işini yapsın". İstisna fırlatmak oturumu hiç
    açtırmazdı; bu fonksiyon bir iyileştirme, zorunlu bir bağımlılık değil."""
    kabuk = tmp_path / "claude.cmd"
    kabuk.write_text("@echo off\r\n", encoding="utf-8")
    win["claude"] = str(kabuk)
    assert css.claude_ikilisini_coz() is None


def test_PATH_te_hic_claude_yoksa_None(win):
    assert css.claude_ikilisini_coz() is None


def test_zaten_native_ise_kabuk_aramasina_girmiyor(win, tmp_path):
    """`which('claude')` bir `.exe` döndürüyorsa dokunma — SDK onu zaten çalıştırır."""
    exe = tmp_path / "claude.exe"
    exe.write_bytes(b"MZ")
    win["claude"] = str(exe)
    assert css.claude_ikilisini_coz() is None
