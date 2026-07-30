"""Yetenek kapılarının kendisini sınayan testler.

Neden var: kapı, hangi testlerin koşacağına karar veren ÖLÇÜM ALETİ. Bozuk bir
aletle alınan "yeşil" bir iddia taşımaz. 30 Tem 2026 denetimi bu alette iki
bulgu buldu ve ikisi de burada sınanıyor:

  E-c — ilgisiz bir I/O hatası "yetenek yok" cevabına dönüşüyordu, yani diski
        dolu bir makinede güvenlik testleri sessizce atlanıp koşu yeşil kalıyordu.
  E-e — atlama gerekçesi sabit bir dizeydi ve gerçek sebebi YANLIŞ beyan
        ediyordu ("Windows'ta ayrıcalık gerekiyor: WinError 1314"), sebep
        bambaşkayken bile.

E-e'nin denetim probe'u (`probe_e4_skip_reason_misattributes_cause.py`) bu
düzeltmeden sonra `rc=2` döndürüyor ve bu beklenen: probe, ENOSPC'te bir skip
EKLENDİĞİNİ varsayıp gerekçesini okuyor. Düzeltilmiş kapı o durumda hiç skip
eklemiyor, dolayısıyla probe'un okuyacağı gerekçe kalmıyor. Ölçüm buraya taşındı
— bulgu kapandı diye değil, probe'un ölçtüğü kod yolu artık var olmadığı için.
"""

import errno
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import conftest  # noqa: E402


class _SahteItem:
    def __init__(self, isaret):
        self.keywords = {isaret: True}
        self.markers = []

    def add_marker(self, marker):
        self.markers.append(marker)


def _hata(sinif, kod, mesaj, winerror=None):
    e = sinif(kod, mesaj)
    if winerror is not None:
        e.winerror = winerror
    return e


# ── E-c: ilgisiz hata "yetenek yok" DEĞİLDİR ─────────────────────────────────


@pytest.mark.parametrize(
    "kod,ad",
    [(errno.ENOSPC, "ENOSPC"), (errno.EIO, "EIO"), (errno.EROFS, "EROFS")],
)
def test_symlink_ilgisiz_io_hatasi_olculemedi_donuyor(monkeypatch, kod, ad):
    """Beklenmedik hata `None` olmalı — `False` (yetenek yok) DEĞİL.

    Üç errno birden: tek bir errno'yu geçmek beyaz listenin ters kurulmuş
    olmasını (yani "bu üçü hariç her şey yetenek yokluğu") gizleyebilirdi.
    """
    def patla(*a, **k):
        raise _hata(OSError, kod, f"induced {ad}")

    monkeypatch.setattr(conftest.os, "symlink", patla)
    durum, gerekce = conftest._symlink_olc()
    assert durum is None, f"{ad} yetenek yokluğuna dönüştü"
    assert "ÖLÇÜLEMEDİ" in gerekce


def test_izin_bitleri_chmod_hatasi_olculemedi_donuyor(monkeypatch):
    def patla(*a, **k):
        raise _hata(PermissionError, errno.EACCES, "induced EACCES")

    monkeypatch.setattr(conftest.os, "chmod", patla)
    durum, gerekce = conftest._izin_bitleri_olc()
    assert durum is None
    assert "ÖLÇÜLEMEDİ" in gerekce


def test_olculemeyen_yetenek_testi_ATLAMIYOR(monkeypatch):
    """Kapının asıl işi: `None` görünce skip EKLEMEMELİ."""
    monkeypatch.setattr(conftest, "SYMLINK_VAR", None)
    monkeypatch.setattr(conftest, "SYMLINK_GEREKCE", "ölçülemedi: sınama")
    item = _SahteItem("baglar_gerekli")
    conftest.pytest_collection_modifyitems(None, [item])
    assert item.markers == [], "ölçülemeyen yetenek sessizce atlandı"


def test_olculemeyen_yetenek_FAIL_ediyor(monkeypatch):
    """Negatif kontrol: alet bozulunca suite KIRMIZI olmalı, yeşil-atlamalı değil."""
    monkeypatch.setattr(conftest, "SYMLINK_VAR", None)
    monkeypatch.setattr(conftest, "SYMLINK_GEREKCE", "ölçülemedi: sınama")
    # `pytest.fail.Exception` bilerek: `Failed` BaseException'dan türüyor,
    # `pytest.raises(Exception)` onu YAKALAMIYOR ve test sahte-kırmızı veriyor.
    with pytest.raises(pytest.fail.Exception) as yakalanan:
        conftest.pytest_runtest_setup(_SahteItem("baglar_gerekli"))
    assert "ölçülemedi: sınama" in str(yakalanan.value)


def test_yetenek_varken_ne_atlama_ne_fail(monkeypatch):
    """Ters yön: `True` olduğunda kapı hiçbir şey yapmamalı.

    Bu olmadan yukarıdaki iddialar "kapı her şeyi fail ediyor" ile de geçerdi.
    """
    monkeypatch.setattr(conftest, "SYMLINK_VAR", True)
    item = _SahteItem("baglar_gerekli")
    conftest.pytest_collection_modifyitems(None, [item])
    assert item.markers == []
    conftest.pytest_runtest_setup(item)  # patlamamalı


# ── E-e: gerekçe ÖLÇÜLEN sebebi söylüyor, sabit bir iddiayı değil ────────────


def test_ayricalik_yoklugu_gerekcesi_olculmus_sebebi_tasiyor(monkeypatch):
    def patla(*a, **k):
        raise _hata(OSError, errno.EPERM, "privilege not held", winerror=1314)

    monkeypatch.setattr(conftest.os, "symlink", patla)
    durum, gerekce = conftest._symlink_olc()
    assert durum is False
    assert "1314" in gerekce and "ölçüldü" in gerekce


def test_ilgisiz_hata_gerekcesi_ayricalik_IDDIA_ETMIYOR(monkeypatch):
    """E-e'nin çekirdeği: ENOSPC'in gerekçesi Windows ayrıcalığından bahsedemez."""
    def patla(*a, **k):
        raise _hata(OSError, errno.ENOSPC, "disk full")

    monkeypatch.setattr(conftest.os, "symlink", patla)
    _, gerekce = conftest._symlink_olc()
    for yalan in ("1314", "ayrıcalık", "Windows"):
        assert yalan not in gerekce, f"gerekçe ölçülmemiş bir sebep iddia ediyor: {yalan}"
    assert "ENOSPC" in gerekce


# ── Faz 2'nin ön koşulu: symlink dışındaki bağ türleri AYRI kapılarda ────────


def test_sabit_bag_ve_junction_symlinkten_ayri_olculuyor():
    """Üç bağ türü tek kapıya bağlanmamalı.

    Ölçüldü (bu makine, ayrıcalıksız): `os.symlink` winerror 1314 ile reddediliyor
    ama `os.link` ve `mklink /J` çalışıyor. Tek kapı, kurulabilen iki bağ türünün
    testlerini de atlatırdı — ve `os.path.islink()` kontrolünü delen tam olarak
    o iki tür.
    """
    assert conftest.HARDLINK_VAR is not None, conftest.HARDLINK_GEREKCE
    assert conftest.JUNCTION_VAR is not None, conftest.JUNCTION_GEREKCE
    if os.name == "nt":
        assert conftest.HARDLINK_VAR is True, (
            f"NTFS'te sabit bağ kurulabilmeli: {conftest.HARDLINK_GEREKCE}"
        )
        assert conftest.JUNCTION_VAR is True, (
            f"Windows'ta junction kurulabilmeli: {conftest.JUNCTION_GEREKCE}"
        )


@pytest.mark.sabit_bag_gerekli
def test_sabit_bag_kapisi_GERCEKTEN_kosuyor(tmp_path):
    """Bu test atlanırsa Faz 2'nin koruması ölü demektir — kapı bunu ölçüyor."""
    kaynak = tmp_path / "kaynak"
    kaynak.write_text("sır", encoding="utf-8")
    bag = tmp_path / "bag"
    os.link(kaynak, bag)
    assert bag.stat().st_nlink == 2
    # Sınıfın çekirdeği: sabit bağ sembolik bağ DEĞİL, `islink` onu görmüyor.
    assert not os.path.islink(bag)


@pytest.mark.junction_gerekli
def test_junction_kapisi_GERCEKTEN_kosuyor(tmp_path):
    hedef = tmp_path / "hedef"
    hedef.mkdir()
    bag = tmp_path / "bag"
    import subprocess

    r = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(bag), str(hedef)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert not os.path.islink(bag), "islink junction'ı görüyorsa sınıf değişmiş"
    assert os.path.realpath(bag) != str(bag)


def test_izin_bitleri_gerekcesi_olculen_modu_tasiyor():
    """Meşru yetenek yokluğunda bile gerekçe ÖLÇÜMÜ göstermeli.

    Bu makinede (Windows) gerçekten `False` bekleniyor; POSIX'te `True`.
    İki durumda da iddia anlamlı olsun diye dallanıyor — sabitlenmiş bir
    platform beklentisi, ölçülebilir bir şeyi varsayıma çevirirdi.
    """
    durum, gerekce = conftest._izin_bitleri_olc()
    assert durum is not None, "izin biti yeteneği bu makinede ölçülemedi"
    if durum is False:
        assert "st_mode=0o" in gerekce
    else:
        assert gerekce == ""
