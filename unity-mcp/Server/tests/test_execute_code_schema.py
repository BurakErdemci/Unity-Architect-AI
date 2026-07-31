"""`execute_code`'un ŞEMASI bypass'ı öğretmemeli.

Canlı testte ölçüldü (31 Tem 2026): engellenen bir desenle karşılaşan model
kullanıcıya şunu söyledi —

    "execute_code'un güvenlik filtresi AssetDatabase.DeleteAsset kalıbını
     engelledi. Bunu geçmek için safety_checks: false ile çalıştırmam
     gerekiyor — onaylıyor musun?"

O sırada C# hata mesajı ZATEN düzeltilmişti (`ExecuteCode.cs`, bypass'ı öneren
cümle kaldırılmıştı). Model bilgiyi başka yerden alıyordu: aracın kendi
tanımından ve `safety_checks` parametresinin açıklamasından. İkisi de şu iki
cümleyi taşıyordu:

    "Not a full sandbox — advanced bypass is possible."
    "NOTE: safety_checks blocks known dangerous patterns but is not a full sandbox."

Ders — ve bu dosyanın var olma sebebi: **hata mesajı yalnız engellendiğinde
görünür, şema HER çağrıda okunur.** Yani şema daha güçlü bir öğretme yüzeyi ve
bir sınıfı kapatırken sayılması gereken giriş noktalarından biri. Bir önceki
turda C# mesajı ve `replay` mirası sayılmış, şema sayılmamıştı.

Test iki yönlü: yasak ifadeler YOK, ama açıklama da BOŞ DEĞİL — "düzeltme"
adına dokümantasyonu silmek modeli parametre hakkında kör bırakırdı.
"""
import typing

import pytest

from services.registry import get_registered_tools
from services.tools.execute_code import execute_code


# Modelin okuduğu metinde geçmemesi gerekenler. Hepsi ya engelin nasıl
# aşılacağını söylüyor ya da korumayı "zaten delik" diye sunuyor — ikisi de
# modeli bypass'a yönlendiriyor.
YASAK_IFADELER = (
    "bypass",
    "not a full sandbox",
    "safety_checks=false",
    "safety_checks: false",
    "disable safety",
)


def _aracin_tanimi() -> str:
    kayit = next(t for t in get_registered_tools() if t["name"] == "execute_code")
    return kayit["description"]


def _safety_checks_aciklamasi() -> str:
    ipuclari = typing.get_type_hints(execute_code, include_extras=True)
    annotated = ipuclari["safety_checks"]
    # Annotated[bool, "açıklama"] → metadata ilk eleman
    metadata = getattr(annotated, "__metadata__", ())
    return " ".join(str(m) for m in metadata)


@pytest.mark.parametrize("okuyucu", [_aracin_tanimi, _safety_checks_aciklamasi],
                         ids=["arac_tanimi", "safety_checks_aciklamasi"])
def test_model_okur_metin_bypass_OGRETMEZ(okuyucu):
    metin = okuyucu().lower()
    bulunan = [ifade for ifade in YASAK_IFADELER if ifade in metin]
    assert not bulunan, (
        f"Modelin okuduğu metin bypass'ı öğretiyor: {bulunan}. "
        "Bir savunmanın şeması, o savunmanın kullanım kılavuzu olamaz — "
        "geliştiriciye yönelik uyarılar kod yorumuna yazılmalı."
    )


def test_TERS_YON_aciklama_silinerek_gecilmez():
    # Testi "yeşile boyamanın" en kolay yolu açıklamayı tamamen silmek olurdu;
    # o da modeli parametre hakkında kör bırakır ve yanlış kullanıma açar.
    aciklama = _safety_checks_aciklamasi().strip()
    assert len(aciklama) > 40, "safety_checks açıklaması silinmiş ya da anlamsız kısalıkta"


def test_aciklama_modeli_VARSAYILANA_yonlendirir():
    # Pozitif yön: metin yalnız "şunu deme" değil, "şunu yap" da demeli.
    # Aksi halde model boşlukta kalır ve engeli aşmayı yine kendisi icat eder.
    metin = _safety_checks_aciklamasi().lower()
    assert "default" in metin and ("rewrite" in metin or "ask the user" in metin), (
        "Açıklama modele ne YAPACAĞINI söylemiyor; engellenen desende "
        "kodu yeniden yazmak ya da kullanıcıya sormak yönlendirmesi olmalı."
    )
