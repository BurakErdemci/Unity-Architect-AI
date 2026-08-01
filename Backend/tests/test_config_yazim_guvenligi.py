"""Ürünün config yazımı, workspace DIŞINDAKİ bir dosyayı ezememeli (K4).

Ölçülmüş açık (bu makinede 2026-08-01'de yeniden üretildi, İKİ vektör de
AYRICALIKSIZ): ürünün config yazım noktaları hedefi düz `open(path, "w")` ile
açıyordu ve kullanıcının projesindeki yol yönlendirilmiş olabiliyordu.

    dosyanın KENDİSİ kurbana sabit bağla bağlı   → kurban EZİLDİ
    ANA DİZİN kurbanın dizinine junction'lı      → kurban EZİLDİ

⚠️ Neden `os.path.islink` yetmiyor (ölçüldü): junction'ı GÖRMÜYOR (`False`
döndürüyor) ve sabit bağ zaten bir bağ değil, ikinci bir addır — `O_NOFOLLOW`
da onu reddetmiyor. Ayrıca "önce kontrol et sonra aç" sırası TOCTOU yarışını
kaybediyor. Doğru soru "bu yol bir bağ mı" DEĞİL, **"açtığım şey beklediğim
dosya mı"** — `safe_paths.dogrula_kimlik` ona açıştan SONRA cevap veriyor.

Bu dosya iki katmanı da sınıyor: yardımcının kendisi VE ürünün gerçek yazım
yolları. İkincisi olmadan test bir şey ölçmez — bu depoda tekrarlayan arıza
şekli "yardımcı doğru ama çağrı yeri onu kullanmıyor".
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from providers.workspace_config import guvenli_config_yaz  # noqa: E402

KURBAN = "KURBANIN-ONEMLI-VERISI"


def _junction(bag: str, hedef: str) -> bool:
    """Ayrıcalıksız dizin yönlendirmesi: Windows'ta junction, POSIX'te symlink."""
    try:
        if os.name == "nt":
            r = subprocess.run(["cmd", "/c", "mklink", "/J", bag, hedef],
                               capture_output=True, text=True, timeout=30)
            return r.returncode == 0
        os.symlink(hedef, bag)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _dosya_bagi(bag: str, hedef: str) -> bool:
    """Ayrıcalıksız dosya yönlendirmesi: sabit bağ."""
    try:
        os.link(hedef, bag)
        return True
    except OSError:
        return False


def _kurulum(tmp_path, kurban_adi: str):
    ws = tmp_path / "workspace"
    ws.mkdir()
    disari = tmp_path / "disarisi"
    disari.mkdir()
    kurban = disari / kurban_adi
    kurban.write_text(KURBAN, encoding="utf-8")
    return str(ws), str(disari), kurban


# ── Yardımcının kendisi ───────────────────────────────────────────────────


def test_dosya_kurbana_bagliyken_yazilmiyor(tmp_path):
    ws, _, kurban = _kurulum(tmp_path, ".mcp.json")
    if not _dosya_bagi(os.path.join(ws, ".mcp.json"), str(kurban)):
        pytest.skip("bu makinede sabit bağ kurulamadı")

    yazildi = guvenli_config_yaz(ws, ".mcp.json", '{"urun":"yazdi"}')

    assert yazildi is False, "yönlendirilmiş hedefe yazıldı"
    assert kurban.read_text(encoding="utf-8") == KURBAN, "workspace dışındaki dosya EZİLDİ"


def test_ana_dizin_junction_iken_yazilmiyor(tmp_path):
    ws, disari, kurban = _kurulum(tmp_path, "cli.json")
    if not _junction(os.path.join(ws, ".cursor"), disari):
        pytest.skip("bu makinede junction/symlink kurulamadı")

    yazildi = guvenli_config_yaz(ws, ".cursor/cli.json", '{"urun":"yazdi"}')

    assert yazildi is False
    assert kurban.read_text(encoding="utf-8") == KURBAN, "workspace dışındaki dosya EZİLDİ"


def test_normal_yazim_ve_uzerine_yazim_CALISIYOR(tmp_path):
    """Muhafız, ürünü çalışmaz hâle getirmemeli — yoksa koruma değil arızadır."""
    ws = str(tmp_path)

    assert guvenli_config_yaz(ws, ".mcp.json", '{"a":1}') is True
    assert guvenli_config_yaz(ws, ".cursor/cli.json", '{"b":2}') is True, \
        "ara dizin yaratılamadı"
    assert guvenli_config_yaz(ws, ".mcp.json", '{"a":2}') is True

    # Üzerine yazım ESKİ İÇERİĞİ BIRAKMAMALI: `O_TRUNC` açılışta yok, kısaltma
    # kimlik doğrulamasından sonra yapılıyor; sıra bozulursa kalıntı kalır.
    assert json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8")) == {"a": 2}


def test_kardes_dizin_ON_EK_olarak_eslesmemeli(tmp_path):
    """`/a/bc` düz dize olarak `/a/b` ile başlar ama onun ALTINDA değildir.

    Kapsama kontrolü `startswith` ile yazılsaydı kardeş dizin workspace içi
    sayılırdı. Mutasyon turunda bu vaka yoktu ve `startswith`'e düşürmek testi
    KIRMIYORDU — yani kontrolün doğruluğu ölçülmemişti.
    """
    from providers.workspace_config import _icinde_mi

    kok = str(tmp_path / "b")
    assert _icinde_mi(str(tmp_path / "b" / "icerde.json"), kok)
    assert not _icinde_mi(str(tmp_path / "bc" / "disarda.json"), kok), \
        "kardeş dizin workspace içi sayıldı (ön ek karşılaştırması)"


def test_O_NOFOLLOW_acilista_veriliyor():
    """POSIX'te son bileşen sembolik bağsa açılış reddedilmeli.

    ⚠️ Bu iddia DAVRANIŞLA ölçülemiyor: Windows'ta `os.O_NOFOLLOW` yok ve
    `safe_paths` onu `0`'a düşürüyor, yani bayrağı kaldırmak bu makinede
    hiçbir şeyi değiştirmiyor (mutasyon turunda ölçüldü — test yeşil kaldı).
    Asıl koruma zaten açıştan sonraki kimlik doğrulaması; bu bayrak POSIX'te
    ikinci hat ve kaynak düzeyinde kilitleniyor ki sessizce düşmesin.
    """
    import inspect

    from providers import workspace_config

    kaynak = inspect.getsource(workspace_config.guvenli_config_yaz)

    # ⚠️ Düz "O_NOFOLLOW kaynakta geçiyor mu" YETMEZ: `from safe_paths import
    # O_NOFOLLOW` satırı fonksiyonun İÇİNDE, yani bayrak `os.open` çağrısından
    # düşse bile kaynakta görünmeye devam ediyordu ve test KÖR kalıyordu
    # (mutasyon turunda ölçüldü). Bayrağın AÇILIŞ ÇAĞRISINDA olması aranıyor.
    acilis = [s for s in kaynak.splitlines() if "os.open(" in s]
    assert acilis, "açılış çağrısı bulunamadı"
    assert any("O_NOFOLLOW" in s for s in acilis), \
        "os.open çağrısından O_NOFOLLOW düşmüş"
    assert "dogrula_kimlik" in kaynak, "asıl koruma (kimlik doğrulaması) düşmüş"


def test_workspace_disina_bakan_goreli_yol_reddediliyor(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    disari = tmp_path / "disarisi"
    disari.mkdir()
    kurban = disari / "kurban.json"
    kurban.write_text(KURBAN, encoding="utf-8")

    assert guvenli_config_yaz(str(ws), "../disarisi/kurban.json", "{}") is False
    assert kurban.read_text(encoding="utf-8") == KURBAN


# ── Ürünün GERÇEK yazım yolları ───────────────────────────────────────────
# Yardımcının doğru olması yetmez; çağrı yerleri onu kullanmalı.


def test_cli_base_mcp_json_yolu_korunuyor(tmp_path, monkeypatch):
    from providers.cli_base import BaseCLIProvider

    ws, _, kurban = _kurulum(tmp_path, ".mcp.json")
    if not _dosya_bagi(os.path.join(ws, ".mcp.json"), str(kurban)):
        pytest.skip("bu makinede sabit bağ kurulamadı")

    p = BaseCLIProvider("claude")
    monkeypatch.setattr(p, "_launcher_path", lambda name: "/bin/true")
    monkeypatch.setattr(BaseCLIProvider, "_ensure_exec", staticmethod(lambda path: None))

    p._write_mcp_config(ws)

    assert kurban.read_text(encoding="utf-8") == KURBAN, \
        "cli_base yazım noktası hâlâ yönlendirmeyi takip ediyor"


def _cursor_saglayici():
    from providers.cursor_provider import CursorProvider

    p = CursorProvider.__new__(CursorProvider)
    p._launcher_path = lambda name: "/bin/true"
    p._ensure_exec = lambda path: None
    return p


def test_cursor_mcp_json_yolu_korunuyor(tmp_path):
    """Ana dizin junction'lıyken `.cursor/mcp.json` yazımı kurbanı ezmemeli."""
    ws, disari, kurban = _kurulum(tmp_path, "mcp.json")
    if not _junction(os.path.join(ws, ".cursor"), disari):
        pytest.skip("bu makinede junction/symlink kurulamadı")

    _cursor_saglayici()._register_mcp("/bin/true", ws, "http://localhost:8000")

    assert kurban.read_text(encoding="utf-8") == KURBAN, \
        "cursor mcp.json yazım noktası hâlâ yönlendirmeyi takip ediyor"


def test_cursor_cli_json_yolu_korunuyor(tmp_path):
    """`.cursor/cli.json` K4'ün EN SİNSİ vakası.

    Cursor'un `Write`/`Shell` deny-list'ini taşıyor: yönlendirilirse görünen
    sonuç bir dosyanın ezilmesi değil, POLİTİKANIN SESSİZCE KAYBI olur.

    ⚠️ Yönlendirme DOSYANIN KENDİSİNE kuruluyor, ana dizine değil. İlk yazımda
    junction `.cursor` dizinine kuruluyordu ve kod `mcp.json` başarısız olunca
    erken dönüyordu — yani test cli.json yoluna HİÇ ULAŞMIYORDU ve adının
    iddia ettiği şeyi ölçmüyordu (mutasyon turunda yakalandı: cli.json yazımını
    düz `open`'a çevirmek testi kırmıyordu).
    """
    ws, _, kurban = _kurulum(tmp_path, "cli.json")
    os.makedirs(os.path.join(ws, ".cursor"), exist_ok=True)
    if not _dosya_bagi(os.path.join(ws, ".cursor", "cli.json"), str(kurban)):
        pytest.skip("bu makinede sabit bağ kurulamadı")

    _cursor_saglayici()._register_mcp("/bin/true", ws, "http://localhost:8000")

    assert kurban.read_text(encoding="utf-8") == KURBAN, \
        "cursor cli.json yazım noktası hâlâ yönlendirmeyi takip ediyor"


def test_opencode_json_yolu_korunuyor(tmp_path):
    from providers.opencode_provider import OpenCodeProvider

    ws, _, kurban = _kurulum(tmp_path, "opencode.json")
    if not _dosya_bagi(os.path.join(ws, "opencode.json"), str(kurban)):
        pytest.skip("bu makinede sabit bağ kurulamadı")

    p = OpenCodeProvider.__new__(OpenCodeProvider)
    p._launcher_path = lambda name: "/bin/true"
    p._ensure_exec = lambda path: None
    p._approval_turn_token = ""
    p.binary_name = "opencode:opencode/grok-code"

    p._register_mcp("/bin/true", ws, "http://localhost:8000")

    assert kurban.read_text(encoding="utf-8") == KURBAN, \
        "opencode yazım noktası hâlâ yönlendirmeyi takip ediyor"


def test_hicbir_yazim_noktasi_duz_open_kullanmiyor():
    """Sınıf muhafızı: yeni bir yazım noktası eski desene dönmesin.

    Bu depoda tekrarlayan arıza şekli "yardımcı doğru ama bir çağrı yeri onu
    kullanmayı unuttu" — K3'te `.cursor/mcp.json` tam olarak öyle kapsam dışı
    kalmıştı. Tek tek davranış testleri o sınıfı kapatmaz, bu kapatır.
    """
    import inspect

    from providers import cli_base, cursor_provider, opencode_provider

    for modul, dosyalar in (
        (cli_base, [".mcp.json"]),
        (cursor_provider, [".cursor/mcp.json", ".cursor/cli.json"]),
        (opencode_provider, ["opencode.json"]),
    ):
        kaynak = inspect.getsource(modul)
        assert "guvenli_config_yaz" in kaynak, (
            f"{modul.__name__} config yazımı güvenli yola bağlı değil ({dosyalar})"
        )
