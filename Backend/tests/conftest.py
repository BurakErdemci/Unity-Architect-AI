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
