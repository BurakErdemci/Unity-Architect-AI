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


def _yol_esitle(yol: str) -> str:
    """Karşılaştırma için yolu tek biçime indirger.

    `GetFinalPathNameByHandleW` `\\\\?\\C:\\...` önekiyle dönüyor, `abspath` ise
    öneksiz. Büyük/küçük harf de Windows'ta anlamsız. Bu ikisi normalize
    edilmezse kontrol HER ZAMAN "yönlendirilmiş" derdi ve ürün açılmazdı.
    """
    if yol.startswith("\\\\?\\"):
        yol = yol[4:]
    yol = os.path.normpath(yol)
    return yol.lower() if os.name == "nt" else yol


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

    if _yol_esitle(gercek) != _yol_esitle(os.path.abspath(beklenen_yol)):
        raise OSError(
            f"{beklenen_yol} başka bir dosyaya yönlendirilmiş ({gercek}); "
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
