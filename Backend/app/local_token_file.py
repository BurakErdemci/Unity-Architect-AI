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


def _open_secret_for_write(path: str) -> int:
    """Sır yazmak için fd döndürür; dosya açıldığı anda 0600 ve bağ değil.

    Sıra önemli: O_TRUNC ile içerik açılışta boşalıyor, fchmod ondan SONRA ama
    ilk bayttan ÖNCE koşuyor. Böylece sır hiçbir an gevşek izinle diskte
    bulunmuyor — (3) numaralı bulgu buydu.

    O_NOFOLLOW yalnız SON bileşeni korur; ara dizinler için ayrı bir saldırı
    gerekir (~/.unity-mcp dizininin kendisini ele geçirmek), ki o noktada
    saldırgan zaten ev dizinine yazabiliyor demektir.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
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
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return ""
    try:
        mode = stat.S_IMODE(os.fstat(fd).st_mode)
        if mode & 0o077:
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
