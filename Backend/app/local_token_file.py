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

logger = logging.getLogger(__name__)

_TOKEN_DIR = os.path.join(os.path.expanduser("~"), ".unity_architect_ai")
_TOKEN_PATH = os.path.join(_TOKEN_DIR, "local-app-token")


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
        # os.open + 0o600: dosya ilk baytı yazılmadan doğru izinle doğar.
        # open() + sonradan chmod, aradaki pencerede sırrı umask'ın izin
        # verdiği herkese okuturdu.
        fd = os.open(_TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(token)
        # Dosya daha önce gevşek izinle var idiyse O_CREAT modu uygulanmaz.
        try:
            os.chmod(_TOKEN_PATH, 0o600)
        except OSError:
            pass
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
    try:
        with open(_TOKEN_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""
