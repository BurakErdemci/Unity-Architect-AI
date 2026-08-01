"""Yol kimliği doğrulama — bir yolun DEĞİL, AÇILAN ŞEYİN beklenen dosya olduğunu sınar.

Bu modül `local_token_file`'dan ÇIKARILDI (2026-08-01, K4). Kod aynı kod; taşınma
sebebi tek: aynı korumaya ikinci bir çağıran geldi (`workspace_config`, ürünün
kullanıcı projesine yazdığı config dosyaları) ve bu depoda **güvenlik kararını
KOPYALAMAK** adı konmuş, tekrar tekrar ölçülmüş bir arıza sınıfı — kopya,
düzeltmenin kopyalardan yalnız birine uygulanması demek.

Buradaki her kural bir ölçümün sonucu; ayrıntılar fonksiyon docstring'lerinde.
Özet, çünkü çağıranın bilmesi gereken şey bu:

  **Doğru soru "bu yol bir bağ mı" DEĞİL, "AÇTIĞIM ŞEY beklediğim dosya mı".**

Ölçüldü (2026-07-30, `IsUserAnAdmin()==0` ile, yani ayrıcalıksız):

    os.symlink  → RED (winerror 1314, ayrıcalık gerekiyor)
    os.link     → OK   (sabit bağ, ayrıcalıksız)
    mklink /J   → OK   (junction, ayrıcalıksız)

Yani yönlendirmenin ayrıcalıksız İKİ yolu var ve `os.path.islink()` ikisini de
görmüyor (junction için ölçüldü: `False`), `O_NOFOLLOW` da yalnız sembolik bağı
reddediyor. Açmadan önce bakan her kontrol hem bu iki biçime kör, hem de
kontrol ile açma arasındaki yarışı kaybediyor. `dogrula_kimlik` açıştan SONRA
tanıtıcının kimliğini sorduğu için ikisine de kapalı.
"""

import logging
import os

logger = logging.getLogger(__name__)


_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
# `os.name` üzerinden, `hasattr(os, "fchmod")` üzerinden DEĞİL: Windows'ta
# `fchmod` var ama etkisiz, yani varlığı yanlış soruya doğru cevap veriyor.
_POSIX_MODE_BITS = os.name == "posix"


def _refuse_symlink(path: str) -> None:
    """Açmadan ÖNCEKİ ucuz eleme. Tek başına YETMEZ — asıl kontrol açıştan sonra.

    ⚠️ Bu fonksiyonun eski gerekçesi *"saldırganın zaten yükseltilmiş yetkisi
    olması gerekiyor"* diyordu ve bu ÖLÇÜLEREK YANLIŞLANDI (30 Tem 2026,
    `IsUserAnAdmin()==0`):

        os.symlink  → RED (winerror 1314, ayrıcalık gerekiyor)
        os.link     → OK   (sabit bağ, ayrıcalıksız)
        mklink /J   → OK   (junction, ayrıcalıksız)

    Yani ayrıcalık yalnız SEMBOLİK bağ için gerekiyordu; sırrı yönlendirmenin
    ayrıcalıksız iki yolu daha vardı. Üstelik `os.path.islink()` ikisini de
    görmüyor (junction için ölçüldü: `False`), `O_NOFOLLOW` da yalnız sembolik
    bağı reddediyor. Kontrol, kendisini atlatan yöntemlere kördü.

    Doğru soru "bu yol bir bağ mı" değil, "AÇTIĞIM ŞEY beklediğim dosya mı" —
    ona `_dogrula_kimlik` cevap veriyor ve TOCTOU'ya da o kapalı.
    """
    if _O_NOFOLLOW:
        return
    if os.path.islink(path):
        raise OSError(f"{path} bir sembolik bağ; sır dosyası olarak kullanılmayacak.")


def _fd_gercek_yol(fd: int) -> "str | None":
    """Açık tanıtıcının çekirdeğe göre GERÇEK yolu; sorulamıyorsa ``None``.

    Windows'ta `GetFinalPathNameByHandleW` junction/symlink zincirini çözüp
    tanıtıcının fiilen hangi dosyaya bağlandığını söylüyor. Ölçüldü: junction'lı
    bir ana dizinde açılan tanıtıcı `...\\saldirgan\\local-app-token` döndürüyor,
    oysa istenen `...\\token-home\\local-app-token` idi.

    POSIX'te taşınabilir bir karşılığı yok (Linux `/proc/self/fd`, macOS
    `F_GETPATH` — ikisi de platforma özgü), o yüzden `None` dönüyor ve çağıran
    `realpath` karşılaştırmasına düşüyor.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetFinalPathNameByHandleW.argtypes = [
            wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD
        ]
        kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        tampon = ctypes.create_unicode_buffer(32768)
        n = kernel32.GetFinalPathNameByHandleW(
            msvcrt.get_osfhandle(fd), tampon, 32767, 0
        )
        return tampon.value if n else None
    except (OSError, ImportError, ValueError):
        return None


def _harf_duyarsiz_kip() -> bool:
    """Yol karşılaştırması büyük/küçük harfi YOK SAYSIN mı (Windows) sayması mı?

    Ayrı bir fonksiyon, çünkü bu kapının iki yarısı var ve her makine yalnız
    kendi yarısını çalıştırıyor — CI `ubuntu-latest`'te koşuyor, ürünün ana
    kitlesi Windows ([[windows-test-kapisi]]'nde ölçülmüş sınıf). Dikiş
    olmadan harf-duyarsızlık guard'ı yalnız bir Windows makinesinde ölçülür.
    Taklit gerçek bir ölçüm: karşılaştırılan dosyalar testte de GERÇEK ve
    kimlikleri gerçekten farklı; taklit edilen tek şey hangi dalın seçildiği.
    """
    return os.name == "nt"


def _yol_normalize(yol: str) -> str:
    """Uzun-yol önekini atar ve `normpath` uygular — harf DÖNÜŞÜMÜ YAPMAZ.

    `_yol_esitle`'den ayrı durmasının sebebi: büyük/küçük harf farkının
    kaybolduğu yer tam olarak orası, ve `_dogrula_kimlik`'in bu farkı görmesi
    gerekiyor (aşağıdaki case-sensitivity guard'ı). Aynı normalleştirmeyi iki
    yerde tekrarlamak, ikisinin zamanla ayrışması demekti.
    """
    if yol.startswith("\\\\?\\UNC\\"):
        # \\?\UNC\server\share\... → \\server\share\...
        yol = "\\\\" + yol[8:]
    elif yol.startswith("\\\\?\\"):
        yol = yol[4:]
    return os.path.normpath(yol)


def _yol_esitle(yol: str) -> str:
    """Karşılaştırma için yolu tek biçime indirger.

    `GetFinalPathNameByHandleW` `\\\\?\\C:\\...` önekiyle dönüyor, `abspath` ise
    öneksiz. Büyük/küçük harf de Windows'ta anlamsız. Bu ikisi normalize
    edilmezse kontrol HER ZAMAN "yönlendirilmiş" derdi ve ürün açılmazdı.

    ⚠️ UNC'nin ayrı ele alınması ŞART (doğrulama turu bulgusu, 30 Tem 2026).
    Uzun-yol önekinin UNC biçimi `\\\\?\\UNC\\server\\share\\...` ve düz kesme
    ondan `UNC\\server\\share\\...` bırakıyor — oysa `abspath` aynı dosya için
    `\\\\server\\share\\...` üretiyor. İkisi eşleşmediği için ev dizini bir ağ
    paylaşımında olan kullanıcıda token dosyası "yönlendirilmiş" sayılıp
    REDDEDİLİYORDU: fail-closed, ama ürünü açılmaz hale getiren cinsten.
    Ölçüldü: `unc\\server\\share\\token` != `\\\\server\\share\\token`.

    ⚠️ Harf dönüşümü bir VARSAYIMA dayanıyor: *"token dizini case-insensitive"*.
    Windows'ta varsayılan öyle, ama zorunlu değil — ölçüldü (31 Tem 2026, bu
    makine, AYRICALIKSIZ): `fsutil file setCaseSensitiveInfo <dizin> enable`
    **rc=0** döndü, ardından `token` ile `Token` aynı dizinde yan yana durdu ve
    `st_ino`'ları FARKLI çıktı. Yani iki ayrı dosya burada tek dosya gibi
    görünebiliyor. Varsayımı kod zorlamadığı için bu fonksiyon değil,
    `_dogrula_kimlik` ek bir kimlik ölçümüyle kapatıyor.
    """
    yol = _yol_normalize(yol)
    return yol.lower() if _harf_duyarsiz_kip() else yol


def _bilesenler(yol: str) -> "list[tuple[str, str]]":
    """Yolu kökten yaprağa `(ebeveyn_dizin, ad)` çiftlerine ayırır.

    ⚠️ `yol.split(os.sep)` ile elle bölmek YANLIŞ ve sebebi ölçüldü (31 Tem
    2026): öyle bölünce sürücüye yakın bir bileşenin ebeveyni `"C:"` çıkıyor ve
    `os.listdir("C:")` kökü DEĞİL o sürücünün çalışma dizinini listeliyor —
    ölçüldü, `listdir("C:")` ile `listdir("C:\\\\")` farklı kümeler döndürdü.
    UNC'de de sunucu/paylaşım bileşenleri elle bölmeyi bozuyor. `os.path.split`
    bu kuralları kendisi biliyor, o yüzden ayrıştırma ona bırakıldı.
    """
    parcalar = []
    p = yol
    while True:
        ust, ad = os.path.split(p)
        if not ad or ust == p:
            break
        parcalar.append((ust, ad))
        p = ust
    parcalar.reverse()
    return parcalar


def _harf_farki_GERCEK_mi(gercek: str, beklenen: str) -> bool:
    """İki yol yalnız harfte ayrışıyor: aynı adın farklı yazımı mı, İKİ AYRI ad mı?

    ⚠️ Bu fonksiyon bir öncekinin (`_ayni_dosya`, kimlik karşılaştırması) YERİNE
    geçti ve sebebi ölçüldü — 3. doğrulama turu, 31 Tem 2026. Kimlik
    karşılaştırması bu soruyu CEVAPLAYAMIYOR, çünkü `os.stat(beklenen)` de
    yönlendirmeyi takip ediyor:

        case-sensitive üst dizin içinde
            TOKEN-HOME\\local-app-token   ← saldırganın dosyası
            token-home  → junction → TOKEN-HOME

    Burada tanıtıcı da `os.stat(beklenen)` da AYNI saldırgan dosyaya çıkıyor,
    yani `st_ino`/`st_dev` eşleşiyor ve kimlik kontrolü "aynı dosya" diyordu.
    Ölçüldü: `read_secret_file` saldırganın token'ını DÖNDÜRDÜ. Guard, kapattığını
    sandığı sınıfı açık bırakmıştı.

    Doğru ayırt edici kimlik değil ADLANDIRMA: dosya sistemi bu iki yazımı ayrı
    iki dizin girişi olarak mı tutuyor? Üst dizinin listesi bunu yönlendirmeyi
    takip etmeden söylüyor — yukarıdaki kurulumda `os.listdir` ölçüldü ve
    `['TOKEN-HOME', 'token-home']` döndü.

    `True` = harf farkı GERÇEK, reddet. Ölçemediğimiz her durum da `True`
    (fail-CLOSED): listeleyemediğimiz bir dizin hakkında iddia üretmiyoruz.
    """
    g = _bilesenler(_yol_normalize(gercek))
    b = _bilesenler(_yol_normalize(beklenen))
    if len(g) != len(b):
        # Bileşen sayısı farklıysa bu bir harf farkı değil, yapı farkı.
        return True
    for (_, g_ad), (ust, b_ad) in zip(g, b):
        if g_ad == b_ad:
            continue
        if g_ad.lower() != b_ad.lower():
            return True  # harf dışı fark — çağıran zaten reddetmiş olmalıydı
        try:
            girisler = set(os.listdir(ust))
        except OSError:
            return True
        if g_ad in girisler and b_ad in girisler:
            # İki yazım da AYRI birer giriş: case-sensitive dizin, iki farklı ad.
            return True
    return False


def _dogrula_kimlik(fd: int, beklenen_yol: str) -> None:
    """AÇILAN tanıtıcı gerçekten beklenen dosya mı? Değilse `OSError`.

    Kontrolün açıştan SONRA yapılması TOCTOU'yu kapatıyor: kontrol ile açma
    arasına bağ sokulsa bile, elimizdeki tanıtıcı zaten yönlendirilmiş dosyaya
    bağlı ve kimliği o hâliyle sorgulanıyor. Açmadan önce bakan her kontrol
    (eski `_refuse_symlink` dahil) o yarışı kaybediyordu.

    İki ayrı yönlendirme biçimi ölçülüyor:

      • **Yol yönlendirmesi** (junction / symlink, ana dizin dahil): tanıtıcının
        gerçek yolu istenen yolla eşleşmeli.
      • **Sabit bağ**: aynı içeriğin başka bir adı varsa (`st_nlink > 1`) sır
        o addan da okunabilir. `islink()` bunu görmüyor (ölçüldü: `False`),
        `O_NOFOLLOW` da reddetmiyor — sabit bağ bir bağ değil, ikinci bir addır.
    """
    st = os.fstat(fd)
    nlink = getattr(st, "st_nlink", 1)
    if nlink > 1:
        raise OSError(
            f"{beklenen_yol} için açılan dosyanın {nlink} adı var (sabit bağ); "
            "sır dosyası olarak kullanılmayacak."
        )

    gercek = _fd_gercek_yol(fd)
    if gercek is None:
        # POSIX dalı: tanıtıcıdan yol sorulamıyor. `O_NOFOLLOW` son bileşeni
        # zaten koruyor; kalan risk ARA DİZİN sembolik bağı ve o, ev dizinine
        # yazma yetkisi gerektiriyor. Bu dal bu makinede ÖLÇÜLEMEDİ —
        # `test_local_token_file.py`'deki karşılığı da o yüzden atlanıyor.
        if _yol_esitle(os.path.realpath(beklenen_yol)) != _yol_esitle(
            os.path.abspath(beklenen_yol)
        ):
            raise OSError(
                f"{beklenen_yol} yolunda sembolik bağ var; sır dosyası olarak "
                "kullanılmayacak."
            )
        return

    beklenen_mutlak = os.path.abspath(beklenen_yol)
    if _yol_esitle(gercek) != _yol_esitle(beklenen_mutlak):
        raise OSError(
            f"{beklenen_yol} başka bir dosyaya yönlendirilmiş ({gercek}); "
            "sır dosyası olarak kullanılmayacak."
        )

    # Buraya gelindiyse yollar EŞİT sayıldı. Ama yalnızca harf farkı silindiği
    # için mi eşit sayıldılar? Öyleyse `_yol_esitle`'nin varsayımı ("dizin
    # case-insensitive") devrede demektir ve o varsayım case-sensitive bir NTFS
    # dizininde ÇÖKÜYOR: `token` ile `Token` iki ayrı dosya (ölçüldü, bkz.
    # `_yol_esitle`). Bu dar dalda bu yüzden ADLANDIRMAYA bakılıyor.
    #
    # ⚠️ Burada önce KİMLİK karşılaştırması vardı (`_ayni_dosya`) ve 3. doğrulama
    # turu onu ÖLÇEREK yanlışladı: `os.stat(beklenen)` yönlendirmeyi takip
    # ettiği için saldırganın dosyası kendisiyle karşılaştırılıyordu ve kontrol
    # "aynı dosya" diyordu. Ayrıntı ve ölçüm `_harf_farki_GERCEK_mi`'de.
    #
    # Neden bu bir TOCTOU riski DEĞİL: kontrol yalnız EK bir VE koşulu. Zaten
    # reddedilen hiçbir durumu kabule çeviremez, yalnızca kabul edilecek dar bir
    # durumu reddedebilir. Yarışı kaybetmenin sonucu fail-CLOSED.
    #
    # Sınıfın BAŞKA İKİ yazımı adlandırılıp ÖLÇÜLDÜ (31 Tem 2026) — ikisi de
    # buraya hiç gelmiyor, ilk karşılaştırmada fail-CLOSED düşüyorlar:
    #   • 8.3 kısa ad (`UZUNAD~1\token.txt`) → RED. Bu red ürünü açılmaz
    #     yapabilirdi (UNC blocker'ıyla aynı sınıf), ama erişilemez: ölçüldü,
    #     `_TOKEN_DIR` = `C:\Users\burcu\.unity_architect_ai`, yani ürün yolu
    #     `expanduser` ile UZUN formda üretiyor, kısa form yalnız çağıran onu
    #     elle verirse oluşur.
    #   • Unicode NFC/NFD (`étiket.txt`) → RED. Windows'ta NFD adı zaten
    #     açılamıyor (`os.path.exists` → False), yani senaryo bu platformda
    #     kurulamıyor; macOS'ta kurulabilir ve orada da fail-CLOSED.
    if _yol_normalize(gercek) != _yol_normalize(beklenen_mutlak):
        if _harf_farki_GERCEK_mi(gercek, beklenen_mutlak):
            raise OSError(
                f"{beklenen_yol} ile açılan dosya ({gercek}) yalnızca büyük/küçük "
                "harfte ayrışıyor ve bunlar AYRI iki ad (case-sensitive dizin); "
                "sır dosyası olarak kullanılmayacak."
            )




# ── Dışarıya açılan adlar ────────────────────────────────────────────────
# Modül içi çağrılar ALT ÇİZGİLİ adları kullanmaya devam ediyor; bunlar yalnız
# okunabilir birer takma ad. Testler bir davranışı ezmek istediğinde ALT
# ÇİZGİLİ adı ezmeli — modül kendi içinde onu okuyor.
O_NOFOLLOW = _O_NOFOLLOW
refuse_symlink = _refuse_symlink
fd_gercek_yol = _fd_gercek_yol
dogrula_kimlik = _dogrula_kimlik
