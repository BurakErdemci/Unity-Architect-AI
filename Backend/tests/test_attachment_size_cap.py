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


def test_cikti_gercekten_KUCULTME_KENARINA_iniyor():
    """Bayt küçüldü diye piksel küçüldüğü sanılmamalı.

    Doğrulama turu ölçtü: `_KUCULTME_KENARI` 2048'den 8192'ye çıkarıldığında 12
    testin 12'si yeşil kaldı, çünkü hiçbiri çıktının PİKSEL boyutuna bakmıyordu —
    3000 px'lik fixture yeniden örneklenmeden yalnız JPEG'e çevriliyor ve bayt
    düştüğü için "küçültüldü" sayılıyordu. Asıl maliyet baytta değil, ajanın
    çözeceği piksel sayısında.
    """
    from PIL import Image

    # ⚠️ Sayı BİLEREK sabitten okunmuyor, elle yazılıyor. İlk yazımı
    # `_KUCULTME_KENARI`'yi import edip ona karşı doğruluyordu; mutasyon turunda
    # ölçüldü: sabit 8192 yapılınca ölçüt de 8192 oluyor ve test yeşil kalıyor —
    # yani kendi kendini doğrulayan, hiçbir şey korumayan bir test. Sınırı
    # değiştirmek isteyen bu satırı da bilerek değiştirsin.
    AZAMI_KENAR = 2048

    kucuk = kucult(_gorsel_uret(3000))
    img = Image.open(io.BytesIO(kucuk))

    assert max(img.size) <= AZAMI_KENAR, (
        f"çıktı {img.size} — {AZAMI_KENAR} px kenar sınırı uygulanmamış"
    )


# ── Şeffaflık: doğrulama turunun blocker'ı ────────────────────────────────


def _seffaf_png(kenar: int) -> bytes:
    """Gerçekçi yük: şeffaf zemin üzerinde OPAK, koyu bir içerik.

    Uç yük (bütünüyle şeffaf) bu sınıfı ölçmek için yanıltıcı: PNG `optimize`
    zaten görünmez piksellerin RGB'sini sıfırlıyor, dolayısıyla "siyah mı" sorusu
    orada anlamsız. Zararın gerçek biçimi bu: şeffaf arka planlı bir UI ekran
    görüntüsündeki KOYU metin, alfa bir zemine bindirilmeden atılırsa siyah
    üstünde siyah kalıp görünmez oluyor.
    """
    import random

    from PIL import Image

    rnd = random.Random(99)
    img = Image.new("RGBA", (kenar, kenar), (0, 0, 0, 0))
    # Ortada opak koyu bir blok (metni temsil eder) + gürültü, sıkışmasın diye.
    for y in range(kenar // 3, 2 * kenar // 3):
        for x in range(kenar // 3, 2 * kenar // 3):
            img.putpixel((x, y), (20, 20, 20, 255))
    for _ in range(kenar * kenar // 4):
        img.putpixel((rnd.randrange(kenar), rnd.randrange(kenar)),
                     (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256), 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_seffaf_gorselin_ALFASI_korunuyor():
    """Ajan, kullanıcının yapıştırdığından FARKLI bir görüntü analiz etmemeli.

    Ölçülmüş arıza (doğrulama turu, blocker): `convert("RGB")` alfayı bir zemine
    bindirmeden ATIYORDU. Şeffaf piksel siyaha dönüyor, şeffaf zeminli bir UI
    görüntüsündeki koyu metin siyah üstünde siyah kalıyordu. Üstelik boyuta
    bağlıydı — aynı görselin küçüğü olduğu gibi geçtiği için tutarsızdı.

    Bu, küçültmenin KAYBINDAN farklı bir sınıf: kayıp değil SESSİZ BOZULMA;
    ne kullanıcı ne ajan fark ediyor.
    """
    from PIL import Image

    ham = _seffaf_png(2200)
    assert len(ham) > _KUCULTME_ESIGI_BAYT, "yük eşiği aşmıyor — küçültme yolu hiç çalışmaz"

    kucuk = kucult(ham)
    assert kucuk is not None, "şeffaf görsel bütünüyle düşürüldü"

    img = Image.open(io.BytesIO(kucuk))
    assert img.mode in ("RGBA", "LA") or "transparency" in img.info, (
        f"çıktı {img.mode} — alfa kanalı düşürülmüş; şeffaf bölgeler siyaha döner"
    )

    # Ve içerik gerçekten oradaysa: opak blok hâlâ opak olmalı.
    alfa = img.convert("RGBA").split()[-1]
    assert alfa.getextrema() != (255, 255), "her şey opaklaşmış — şeffaflık zemine gömülmüş"
    assert alfa.getextrema()[1] == 255, "opak içerik de saydamlaşmış"


def test_seffaf_gorselin_BICIMI_korunuyor():
    """Şeffaflık varken çıktı PNG kalmalı; JPEG alfa taşıyamaz."""
    from providers._attachments import _uzanti

    assert _uzanti(kucult(_seffaf_png(2200))) == "png"


def test_kucultulemeyen_dev_gorsel_ATLANIYOR():
    """Fail-closed yön: küçültülemeyen dev bir içerik yazılmaktansa düşürülür.

    Tek bir eki kaybetmek, kullanıcının bütün sohbet bağlamını kaybetmesinden
    iyidir — gerekçe `_attachments.py`'de yazılı.
    """
    bozuk_ama_dev = b"\x00\xff" * (_MUTLAK_TAVAN_BAYT // 2 + 1024)  # PIL açamaz
    assert kucult(bozuk_ama_dev) is None


def test_KUCULTULDUGU_HALDE_dev_kalan_sonuc_da_atiliyor():
    """"Küçülttüm" demek sığdığını göstermez — ölçüt çıkan bayt.

    Mutasyon turunda ölçüldü: bu kol nöbetsizdi. `test_kucultulemeyen_dev_gorsel_ATLANIYOR`
    PIL'in hiç açamadığı veriyle BAŞKA bir kolu (istisna dalını) vuruyor; küçültme
    başarıyla çalışıp yine de tavanı aşan sonucun geri döndürülmesi serbestti.
    """
    from providers._attachments import _MUTLAK_TAVAN_BAYT, _sonucu_dogrula

    hala_dev = b"x" * (_MUTLAK_TAVAN_BAYT + 1)
    assert _sonucu_dogrula(b"ham", hala_dev) is None, (
        "küçültme sonrası hâlâ tavanı aşan içerik yazılmak üzere döndürüldü"
    )
    # Ters yön: sığan sonuç geri gelmeli, yoksa düzeltme eki tamamen yutar.
    sigan = b"x" * 1024
    assert _sonucu_dogrula(b"ham", sigan) == sigan


def test_kucultulemeyen_KUCUK_gorsel_korunuyor():
    """Aynı fail-closed kolu masum veriyi yutmamalı.

    PIL açamayan ama zaten küçük bir içerik (ör. desteklenmeyen bir biçim)
    olduğu gibi geçmeli; aksi hâlde düzeltme bir yetenek kaybına dönüşür.
    """
    kucuk_ama_acilamaz = b"\x00\xff" * 1024
    assert kucult(kucuk_ama_acilamaz) == kucuk_ama_acilamaz
