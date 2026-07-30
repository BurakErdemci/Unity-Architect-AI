"""8080'i kim tutuyor sorusunun KİMLİK cevabı — "biri dinliyor mu" ile aynı şey değil.

Neden ayrı bir modül: `is_running()` bu iki soruyu tek boolean'a katlıyordu ve
`/health`'in 200'ünü kimlik kanıtı sayıyordu. `/health` bilerek kimliksiz
(`unity-mcp/Server/src/core/local_auth.py:106-119` — bir kez kapatıldı ve toggle
sonsuza kadar sarıda kaldı), yani onu taklit etmek bedava. Ölçülen sonuç: 8080'de
yabancı bir sunucu varken `/unity/toggle` `already_running` dönüyor, toggle
yeşile geçiyor ve trafik yabancı sunucuya gidiyor. Kapı `on_call_tool`'a konsa
bile o yolun İÇİNDE HİÇ OLMUYOR, üstelik UI "her şey yolunda" diyor.

AYIRT EDİCİ: `X-API-Key` kapısı bu fork'un eklediği bir şey (2026-07-27 denetimi);
upstream mcp-for-unity'de yok. Bu yüzden testi KİMLİKSİZ yapıyoruz:

    kimliksiz POST /mcp → 401 + bizim hata gövdemiz  ⇒ kimlik kapısı VAR ⇒ bizim
    başka her yanıt                                   ⇒ kapı yok ⇒ bizim DEĞİL

Anahtarı GÖNDERMİYORUZ, çünkü gönderirsek upstream bir sunucu da kabul eder
(başlığı yok sayar) ve test ayırt ediciliğini kaybeder. Reddedilmeyi ölçmek,
kabul edilmeyi ölçmekten güçlü.

⚠️ DÜRÜST SINIR: bu probe "kimlik kapısı olan bir MCP-for-Unity yapısı" kanıtlar,
"bizim DAĞITTIĞIMIZ sürüm" değil. Kullanıcının diskindeki eski bir kopyamız da
401 döner. Sürüm/yapı kimliği ayrı bir soru ve bu modül onu çözmüyor.
"""

import json
import logging
import socket
import urllib.error
import urllib.request
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Probe'lar aynı makinede, loopback üzerinde. Kısa tutuluyor çünkü is_running()
# senkron ve status endpoint'i sık yokluyor; uzun timeout UI'ı dondurur.
_CONNECT_TIMEOUT_S = 0.3
_HTTP_TIMEOUT_S = 0.8
# Hata gövdesinden okunacak azami bayt. Yabancı sunucu ne döndüreceğini
# bilmiyoruz — sınırsız okumak bir DoS yüzeyidir.
_MAX_BODY_BYTES = 4096

# Sunucunun 401 gövdesinde aradığımız iki iz. İkisi birden aranıyor: tek başına
# "X-API-Key" jenerik bir auth proxy'sinde de geçebilir, dosya ipucu geçemez.
# ⚠️ Bu iki dize sunucunun kaynağına BAĞIMLI (local_auth.py). Sessiz ayrışmayı
# önleyen tripwire: tests/test_mcp_identity.py::test_sunucu_401_govdesi_probe_ile_uyusuyor
IDENTITY_MARKERS = ("X-API-Key", "local-api-token")


class Occupant(NamedTuple):
    """8080'i tutan şeyin kimliği + kullanıcıya gösterilebilir kısa sebep."""

    identity: str
    detail: str


class ServerIdentity:
    NONE = "none"        # port dinlenmiyor
    OURS = "ours"        # kimlik kapısı olan MCP-for-Unity yapısı
    FOREIGN = "foreign"  # dinleyen var ama kimlik kapısı yok / ölçülemedi


def probe_port_identity(port: int, host: str = "127.0.0.1") -> Occupant:
    """8080'i tutanın kimliğini ölç. Bilinmeyen her durum FOREIGN'a düşer.

    Fail-closed yön KASITLI: "ölçemedim"i "bizimki" saymak, düzeltmeye çalıştığımız
    hatanın ta kendisi. Yanlış tarafa düşmenin bedeli yalnızca gereksiz bir
    başlatma denemesi — o denemeyi de port muhafızı karşılıyor.
    """
    try:
        with socket.create_connection((host, port), timeout=_CONNECT_TIMEOUT_S):
            pass
    except OSError:
        return Occupant(ServerIdentity.NONE, "port dinlenmiyor")

    # Gövde bilerek anlamsız: middleware transport'tan ÖNCE çalışıyor, yani
    # geçerli bir MCP çerçevesi kurmamız gerekmiyor. Yabancı sunucuda da bir
    # şey TETİKLEMEMESİ için en zararsız yük seçildi.
    request = urllib.request.Request(
        f"http://{host}:{port}/mcp",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as response:
            # 401 beklerken 2xx aldık: kimlik kapısı yok.
            return Occupant(
                ServerIdentity.FOREIGN,
                f"/mcp kimliksiz kabul etti (HTTP {response.status})",
            )
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            body = exc.read(_MAX_BODY_BYTES).decode("utf-8", errors="replace")
        except Exception:
            body = ""
    except Exception as exc:  # bağlantı düştü, timeout, bozuk yanıt...
        logger.debug("Kimlik probe'u başarısız (port %s): %s", port, exc)
        return Occupant(ServerIdentity.FOREIGN, "yanıt ölçülemedi")

    if status == 401 and _has_identity_markers(body):
        return Occupant(ServerIdentity.OURS, "kimlik kapısı doğrulandı")

    return Occupant(
        ServerIdentity.FOREIGN,
        f"/mcp bizim kimlik kapımızı göstermedi (HTTP {status})",
    )


def _has_identity_markers(body: str) -> bool:
    """401 gövdesi bizim hata mesajımız mı.

    JSON olarak okunabiliyorsa yalnız `error` alanına bakılıyor; okunamıyorsa ham
    gövdeye. Ham gövdeye düşmek bilerek: yabancı bir sunucunun JSON döndürmeme
    ihtimali var ve o durumda da eşleşme aramamak, aramaktan daha yanlış değil.
    """
    haystack = body
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict) and isinstance(parsed.get("error"), str):
            haystack = parsed["error"]
    except (ValueError, TypeError):
        pass
    return all(marker in haystack for marker in IDENTITY_MARKERS)
