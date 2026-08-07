"""Yapıştırılan görsel, ajanın CEVABINDA oturumu öldüremeyecek boyutta yazılmalı.

Bu dosyanın varlık sebebi bir denetim bulgusu: satır tavanını 1 MiB'den 32 MiB'ye
çıkarmak çökmeyi çözmüyor, ERTELİYORDU. Zincir şu — buraya yazılan dosyayı ajan
`Read` ile açıyor, `Read` görseli base64 olarak tek bir NDJSON satırına koyuyor,
ve o satırın tavanı aşılınca oturum komple düşüyor.

base64 ham boyutun ~4/3'ü olduğundan ~24 MiB'lik TEK bir görsel 32 MiB tavanını
yine aşıyordu; iki bağımsız denetim lane'i bunu ayrı ayrı buldu ve probe ana
ağaçta `rc=1` verdi. Yani doğru sınır tavanda değil, KAYNAKTA.

Testler dizeye değil davranışa bakıyor: gerçek görseller üretilip
`materialize_images` çağrılıyor ve DİSKE NE YAZILDIĞI ölçülüyor.
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from providers._attachments import (  # noqa: E402
    _KUCULTME_ESIGI_BAYT,
    _MUTLAK_TAVAN_BAYT,
    kucult,
    materialize_images,
)

PIL = pytest.importorskip("PIL.Image", reason="küçültme PIL'e dayanıyor")


def _gorsel_uret(kenar: int, fmt: str = "PNG") -> bytes:
    """Sıkışmayan (gürültülü) bir görsel — düz renk üretmek testi kandırırdı.

    Düz beyaz bir 4000x4000 PNG birkaç KB'a iniyor ve eşiği hiç aşmıyor; o
    yükle test küçültmeyi ölçtüğünü sanıp hiçbir şey ölçmezdi.
    """
    import random

    from PIL import Image

    rnd = random.Random(1234)
    img = Image.new("RGB", (kenar, kenar))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                 for _ in range(kenar * kenar)])
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _data_uri(ham: bytes, media: str = "image/png") -> str:
    import base64

    return f"data:{media};base64," + base64.b64encode(ham).decode()


# ── Yükün kendisi geçerli mi (pozitif kontrol) ────────────────────────────


def test_test_yuku_gercekten_esigi_asiyor():
    """Fixture canlı mı? Eşiği aşmayan bir yükle bütün dosya hiçbir şey ölçmez.

    Bu depoda ölçülmüş bir sahte-yeşil biçimi: sınanan koşulu hiç tetiklemeyen
    bir fixture, koruma silinse bile yeşil kalıyor.
    """
    ham = _gorsel_uret(3000)
    assert len(ham) > _KUCULTME_ESIGI_BAYT, (
        f"test yükü yalnız {len(ham)} bayt — küçültme yolu hiç çalışmaz"
    )


# ── Asıl iddia ────────────────────────────────────────────────────────────


def test_buyuk_gorsel_diske_KUCULTULEREK_yaziliyor(tmp_path):
    """Kullanıcının yapıştırdığı büyük görsel, diskte küçülmüş olmalı."""
    ham = _gorsel_uret(3000)
    yollar, klasor = materialize_images([_data_uri(ham)], str(tmp_path), "test")

    assert yollar, "görsel hiç yazılmadı — küçültme yolu eki düşürüyor"
    yazilan = os.path.getsize(yollar[0])
    assert yazilan < len(ham), f"görsel küçültülmeden yazıldı ({yazilan} bayt)"
    assert yazilan <= _MUTLAK_TAVAN_BAYT


def test_yazilan_dosyanin_base64u_SATIR_TAVANININ_altinda(tmp_path):
    """Asıl ölçüt bayt sayısı değil, ajanın cevabında üreteceği SATIR.

    Testi buraya bağlamak önemli: "küçüldü" demek yetmez, "artık tavanı
    aşamıyor" demek gerekir — bulgunun kendisi tam olarak bu ayrımdı.
    """
    from providers.claude_sdk_session import _SDK_STDOUT_LIMIT_BYTES

    ham = _gorsel_uret(3000)
    yollar, _ = materialize_images([_data_uri(ham)], str(tmp_path), "test")

    satir = os.path.getsize(yollar[0]) * 4 // 3  # base64 + zarf payı
    assert satir < _SDK_STDOUT_LIMIT_BYTES, (
        f"yazılan dosyanın base64'ü ~{satir} bayt — {_SDK_STDOUT_LIMIT_BYTES} "
        "baytlık satır tavanını aşar ve oturumu düşürür"
    )


def test_kucuk_gorsel_OLDUGU_GIBI_kaliyor(tmp_path):
    """Ters yön: küçük bir görseli yeniden kodlamak kaliteyi boşuna düşürürdü.

    Bu test olmadan "her şeyi 2048'e indir" gibi bir sadeleştirme sessizce
    geçerdi ve ekran görüntülerindeki yazılar okunamaz hâle gelirdi.
    """
    ham = _gorsel_uret(200)
    assert len(ham) < _KUCULTME_ESIGI_BAYT  # yükün küçük olduğu kesin

    yollar, _ = materialize_images([_data_uri(ham)], str(tmp_path), "test")

    assert os.path.getsize(yollar[0]) == len(ham), "küçük görsel gereksiz yere yeniden kodlandı"
    assert yollar[0].endswith(".png"), "küçük görselin biçimi korunmalı"


def test_kucultulmus_gorselin_UZANTISI_jpg(tmp_path):
    """İçerik JPEG olurken adın `.png` kalması ajanı yanlış çözmeye iter."""
    yollar, _ = materialize_images([_data_uri(_gorsel_uret(3000))], str(tmp_path), "test")
    assert yollar[0].endswith(".jpg")


def test_kucultulemeyen_dev_gorsel_ATLANIYOR():
    """Fail-closed yön: küçültülemeyen dev bir içerik yazılmaktansa düşürülür.

    Tek bir eki kaybetmek, kullanıcının bütün sohbet bağlamını kaybetmesinden
    iyidir — gerekçe `_attachments.py`'de yazılı.
    """
    bozuk_ama_dev = b"\x00\xff" * (_MUTLAK_TAVAN_BAYT // 2 + 1024)  # PIL açamaz
    assert kucult(bozuk_ama_dev) is None


def test_kucultulemeyen_KUCUK_gorsel_korunuyor():
    """Aynı fail-closed kolu masum veriyi yutmamalı.

    PIL açamayan ama zaten küçük bir içerik (ör. desteklenmeyen bir biçim)
    olduğu gibi geçmeli; aksi hâlde düzeltme bir yetenek kaybına dönüşür.
    """
    kucuk_ama_acilamaz = b"\x00\xff" * 1024
    assert kucult(kucuk_ama_acilamaz) == kucuk_ama_acilamaz
