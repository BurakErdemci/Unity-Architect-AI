"""Backend bearer token'ının (LOCAL_APP_TOKEN) süreçler arası TEK aktarım yolu.

Sorun (2026-07-27 denetimi, C grubu): token yedi sağlayıcı yolunda ayrı ayrı
çoğaltılıyordu ve iki yerde okunabilir hâlde duruyordu —

  1. ``workspace/.mcp.json`` içine düz metin yazılıyordu. Bu dosya MODELİN kendi
     projesinin içinde: sıradan bir okuma aracı, bir commit ya da bir arşiv onu
     ifşa ediyordu. Token backend'de sohbet, API anahtarı değiştirme, workspace
     işlemleri ve Unity MCP kontrolü için tek yetki kanıtı.
  2. ``codex mcp add --env LOCAL_APP_TOKEN=<sır>`` ve ``claude mcp add -e ...``
     komut satırlarında geçiyordu. ``--env`` çocuğun ortamını kurar ama EBEVEYNİN
     argv'sini gizlemez; kayıt sürerken ``ps`` çalıştıran her aynı-kullanıcı
     süreci token'ı okuyabiliyordu.

Çözüm, Unity MCP tarafında zaten işe yarayan kalıbın aynısı: sır 0600 izinli bir
dosyada durur, onu okuması gereken çocuk süreç dosyadan okur. Config dosyalarına
ve komut satırlarına hiç girmez.

Neden ortam değişkeni tek başına yetmiyor: MCP sunucusunu BİZ başlatmıyoruz —
claude/codex/cursor gibi CLI'lar başlatıyor, dolayısıyla bizim ortamımızı miras
almıyorlar. Aktarım için ya config dosyası ya argv ya da bu dosya kalıyor; ilk
ikisi okunabilir olduğu için üçüncüsü seçildi.
"""

import logging
import os
import stat

logger = logging.getLogger(__name__)

_TOKEN_DIR = os.path.join(os.path.expanduser("~"), ".unity_architect_ai")
_TOKEN_PATH = os.path.join(_TOKEN_DIR, "local-app-token")

# ── Sır dosyası ilkelleri — iki sır da (backend bearer'ı ve Unity MCP paylaşımlı
#    sırrı) buradan geçer. 2026-07-27 denetiminin üç bulgusu tek kökten çıktı ve
#    üçü de burada kapanıyor:
#
#      1. Yazıcılar sembolik bağı TAKİP EDİYORDU. `~/.unity-mcp/local-api-token`
#         yerine önceden bir bağ kurabilen saldırgan, sırrı seçtiği dosyaya
#         yazdırabiliyordu. Kanıtlandı, probe ile üretildi.
#      2. Dosya ZATEN 0644 ile varsa hiç sıkılaştırılmıyordu: okuma yolu erken
#         dönüyor, yazma yolunda O_CREAT modu var olan dosyaya uygulanmıyor.
#      3. Var olan gevşek dosyaya bytlar önce yazılıp SONRA chmod ediliyordu —
#         aradaki pencerede sır 0644'te okunabilir duruyordu.
#
# ── Windows (ölçüldü 2026-07-30, Python 3.13/win32) — iki POSIX varsayımı çöktü:
#
#      1. `os.O_NOFOLLOW` YOK. Koşulsuz kullanmak `AttributeError` üretiyordu ve
#         `AttributeError` bir `OSError` DEĞİL, yani aşağıdaki `except OSError`
#         onu yakalamıyor, hata çağırana sızıyordu. Ölçülen bedeli ürünün
#         tamamı: `main.py` bu modülü import anında çağırdığı için **backend
#         Windows'ta hiç ayağa kalkmıyordu**; `unity_mcp_manager.start_server()`
#         False dönüyordu (Unity MCP hiç başlamıyor) ve `approval_bridge`
#         token'ı okuyamadığı için **her onay isteğini reddediyordu.**
#      2. POSIX izin bitleri YOK. `os.chmod(path, 0o600)` sonrası `st_mode`
#         hâlâ `0o666` — ama `os.fchmod` VAR ve hata VERMİYOR. Yani eski kod
#         "izni 0600'e çekildi" diye uyarı basıp hiçbir şey yapmıyordu, ve
#         maske (`0o666 & 0o077 = 0o66`) her seferinde tuttuğu için bu yalan
#         HER OKUMADA tekrarlanıyordu. Bu depoda kapatılmış bir sınıf:
#         olmamış işleme "oldu" demek.
#
# Windows'ta sırrın korunması bu yüzden dosyanın KONUMUNA dayanıyor
# (`%USERPROFILE%\.unity_architect_ai`, NTFS profil ACL'i). Bu bir taviz ve
# aynı gerekçeye dayanıyor: tek kullanıcılı makinede aynı kullanıcı sırrı
# zaten okuyabiliyor.

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


def _ayni_dosya(fd: int, yol: str) -> bool:
    """Açık tanıtıcı ile `yol` AYNI dosya mı — ada değil kimliğe bakarak.

    Ölçüldü (31 Tem 2026, Windows, `Backend\\venv`): `os.fstat` bu platformda da
    anlamlı `st_ino`/`st_dev` dolduruyor — aynı yolun `stat`'ı tanıtıcıyla
    eşleşti, başka bir dosya eşleşmedi.

    Ölçemediğimiz her durumda `False` dönüyor (kimlik alınamadı, dosya yok,
    `st_ino` sıfır). Çağıran bunu ek bir VE koşulu olarak kullanıyor, yani
    ölçememek kabule değil REDDE dönüşüyor.
    """
    try:
        st1 = os.fstat(fd)
        st2 = os.stat(yol)
    except OSError:
        return False
    if not st1.st_ino:
        # Kimliği olmayan bir dosya sistemi (bazı ağ/FAT birimleri): iddia
        # üretmiyoruz. `0 == 0` eşitliği sahte bir "aynı dosya" olurdu.
        return False
    return (st1.st_ino, st1.st_dev) == (st2.st_ino, st2.st_dev)


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
    # `_yol_esitle`). O yüzden bu dar dalda ada değil KİMLİĞE bakıyoruz.
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
        if not _ayni_dosya(fd, beklenen_yol):
            raise OSError(
                f"{beklenen_yol} ile açılan dosya ({gercek}) yalnızca büyük/küçük "
                "harfte ayrışıyor ve AYNI dosya değil (case-sensitive dizin); "
                "sır dosyası olarak kullanılmayacak."
            )


def _open_secret_for_write(path: str) -> int:
    """Sır yazmak için fd döndürür; dosya açıldığı anda 0600 ve bağ değil.

    Sıra önemli: O_TRUNC ile içerik açılışta boşalıyor, fchmod ondan SONRA ama
    ilk bayttan ÖNCE koşuyor. Böylece sır hiçbir an gevşek izinle diskte
    bulunmuyor — (3) numaralı bulgu buydu.

    ⚠️ `O_TRUNC` açılıştan ÇIKARILDI. Eskiden açılışta içerik boşalıyordu; ana
    dizin junction ise bu, saldırganın seçtiği dosyayı kimlik doğrulanmadan
    KESMEK demekti. Şimdi sıra: aç → kimliği doğrula → izni sıkılaştır →
    kısalt → yaz. Sır hâlâ hiçbir an gevşek izinle diskte bulunmuyor, ama
    yönlendirme durumunda hedef dosyaya hiç dokunulmuyor.
    """
    _refuse_symlink(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | _O_NOFOLLOW, 0o600)
    try:
        _dogrula_kimlik(fd, path)
        if _POSIX_MODE_BITS:
            os.fchmod(fd, 0o600)
        os.ftruncate(fd, 0)
    except OSError:
        os.close(fd)
        raise
    return fd


def read_secret_file(path: str) -> str:
    """Sır dosyasını bağ takip etmeden okur ve gevşek izin bulursa SIKILAŞTIRIR.

    Sıkılaştırma burada, çünkü tek okunan yer burası: yalnız yazma yolunu
    düzeltmek yetmiyordu — mevcut kurulumlarda dosya çoktan 0644'le yaratılmıştı
    ve okuma yolu erken dönüp onu olduğu gibi bırakıyordu ((2) numaralı bulgu).
    """
    try:
        _refuse_symlink(path)
        fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
    except OSError:
        return ""
    try:
        # Okuma yolu da doğrulanıyor: junction'lı bir ana dizin, saldırganın
        # yerleştirdiği token'ı ürüne KABUL ETTİRİYORDU (probe ile üretildi).
        # Yönlendirme varsa boş dönüyoruz — sahte bir sırla devam etmek,
        # sırrı sızdırmak kadar tehlikeli.
        try:
            _dogrula_kimlik(fd, path)
        except OSError as e:
            logger.error(f"[local-token] {path} kimliği doğrulanamadı: {e}")
            return ""
        mode = stat.S_IMODE(os.fstat(fd).st_mode)
        # İzin ölçümü ve düzeltmesi yalnız POSIX'te anlamlı. Windows'ta `st_mode`
        # ACL'den türetilmiyor (`0o666` sabit gelir) ve `fchmod` etkisiz; koşulu
        # kaldırmak "sıkılaştırdım" diyen ama hiçbir şey yapmayan bir uyarıyı
        # her okumada bastırırdı.
        if _POSIX_MODE_BITS and mode & 0o077:
            try:
                os.fchmod(fd, 0o600)
                logger.warning(
                    f"[local-token] {path} izni {oct(mode)} idi, 0600'e çekildi."
                )
            except OSError as e:
                logger.error(f"[local-token] {path} sıkılaştırılamadı: {e}")
        with os.fdopen(os.dup(fd), "r", encoding="utf-8") as f:
            return f.read().strip()
    finally:
        os.close(fd)


def token_path() -> str:
    return _TOKEN_PATH


def write_local_app_token(token: str) -> bool:
    """Token'ı 0600 izinle diske yazar. Boş token dosyayı SİLER.

    Boşta silme kasıtlı: uygulama token'sız (dev) başlatıldığında önceki
    oturumdan kalan geçerli bir sırrın diskte kalması, kapalı sanılan bir kapıyı
    açık bırakırdı.
    """
    try:
        if not token:
            if os.path.exists(_TOKEN_PATH):
                os.remove(_TOKEN_PATH)
            return True
        os.makedirs(_TOKEN_DIR, exist_ok=True)
        with os.fdopen(_open_secret_for_write(_TOKEN_PATH), "w", encoding="utf-8") as f:
            f.write(token)
        return True
    except OSError as e:
        logger.error(f"[local-token] yazılamadı: {e}")
        return False


def read_local_app_token() -> str:
    """Önce ortam, sonra dosya.

    Sıra önemli: backend'in KENDİ sürecinde token ortamda var ve dosyadan daha
    günceldir. MCP sunucusu gibi ayrı başlatılan çocuklarda ortam boştur ve
    dosya devreye girer.
    """
    token = os.environ.get("LOCAL_APP_TOKEN", "")
    if token:
        return token
    return read_secret_file(_TOKEN_PATH)
