"""Test takımı için ortak fixture'lar.

Neden burası var: `auth_utils._check_token` 2026-07-27 denetiminden sonra
fail-CLOSED oldu — `LOCAL_APP_TOKEN` yoksa istek 503 ile reddediliyor. Testler
o güne kadar fail-OPEN davranışa **örtük olarak** bağlıydı; hiçbiri token
kurmuyordu ve yine de korumalı uçlara vurabiliyordu.

Bağımlılığı silmek yerine görünür kılıyoruz: test ortamı token'sız çalışmayı
burada AÇIKÇA seçiyor. Kapının kendisini sınayan bir test yazılırsa bu değişkeni
monkeypatch ile kaldırıp 503'ü doğrulayabilir.
"""

import os
import stat
import tempfile

import sys

import pytest

# `app/` sys.path'e burada ekleniyor. Mevcut test dosyalarının her biri bunu
# kendisi yapıyordu; sonuç, satırı unutan bir dosyanın YALNIZCA başka bir test
# ondan önce toplandığında çalışmasıydı — yani toplama sırasına bağlı, tek
# başına koşturulunca ModuleNotFoundError veren testler. Burada bir kez yapmak
# o bağımlılığı kaldırıyor; dosyalardaki mevcut satırlar zararsız (idempotent).
_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if _APP not in sys.path:
    sys.path.insert(0, _APP)


@pytest.fixture(autouse=True)
def _allow_tokenless_local_api(monkeypatch):
    monkeypatch.setenv("UNITYAI_ALLOW_NO_TOKEN", "1")
    monkeypatch.delenv("LOCAL_APP_TOKEN", raising=False)
    yield


# ── Platform yeteneği kapıları ───────────────────────────────────────────────
#
# Sorun (ölçüldü 30 Tem 2026, Windows 11 / Python 3.13): aynı ağaç macOS'ta 824
# testle yeşilken bu makinede 30 fail + 40 error veriyordu. Sebebin BÜYÜK kısmı
# ürün değil ORTAM: iki POSIX ilkeli Windows'ta yok ve testler onları örtük
# olarak varsayıyordu —
#
#   • sembolik bağ kurmak `SeCreateSymbolicLinkPrivilege` istiyor
#     (yönetici ya da Geliştirici Modu); yoksa `os.symlink` → WinError 1314
#   • POSIX izin bitleri yok: `os.chmod(p, 0o600)` sonrası `st_mode` hâlâ `0o666`
#
# Atlamak korumayı kaybetmek DEĞİL — CI Linux'ta koşuyor ve bu iddialar orada
# gerçek. Kırmızı bırakmak ise baseline'ı okunmaz yapıyor: okunmayan bir
# baseline'da hiç kimse kendi işinin kapısını ölçemez, ve "42 kırmızının hangisi
# benim" sorusu cevapsız kalır.
#
# Koşullar platform ADINA değil YETENEĞE bakıyor: Geliştirici Modu açık bir
# Windows'ta bağ kurulabiliyor ve o makinede testin koşması GEREKİR. `os.name`
# sabitlemek ölçülebilir bir şeyi varsayıma çevirirdi.


def _symlink_kurulabiliyor_mu() -> bool:
    with tempfile.TemporaryDirectory() as d:
        try:
            os.symlink(os.path.join(d, "hedef"), os.path.join(d, "bag"))
            return True
        except (OSError, NotImplementedError, AttributeError):
            return False


def _izin_bitleri_anlamli_mi() -> bool:
    fd, p = tempfile.mkstemp()
    os.close(fd)
    try:
        os.chmod(p, 0o600)
        return stat.S_IMODE(os.stat(p).st_mode) == 0o600
    except OSError:
        return False
    finally:
        os.remove(p)


# Bir kez ölçülüp saklanıyor: her test için yeniden dosya yaratmak toplama
# süresini gereksiz uzatır ve yetenek koşu ortasında değişmiyor.
SYMLINK_VAR = _symlink_kurulabiliyor_mu()
IZIN_BITLERI_VAR = _izin_bitleri_anlamli_mi()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "baglar_gerekli: sembolik bağ KURULABİLEN bir platform gerektirir",
    )
    config.addinivalue_line(
        "markers",
        "izin_bitleri_gerekli: POSIX izin bitleri (chmod'un etkili olması) gerektirir",
    )


def pytest_collection_modifyitems(config, items):
    atla_bag = pytest.mark.skip(
        reason="sembolik bağ kurulamıyor (Windows'ta ayrıcalık gerekiyor: WinError 1314)"
    )
    atla_izin = pytest.mark.skip(
        reason="POSIX izin bitleri bu platformda yok — chmod st_mode'u değiştirmiyor"
    )
    for item in items:
        if not SYMLINK_VAR and "baglar_gerekli" in item.keywords:
            item.add_marker(atla_bag)
        if not IZIN_BITLERI_VAR and "izin_bitleri_gerekli" in item.keywords:
            item.add_marker(atla_izin)
