"""8080'i tutanın KİMLİĞİ — canlılıkla karıştırılmasının kapatılması.

Ölçülen arıza: `/health` bilerek kimliksiz, `is_running()` ise onun 200'ünü
"bu sunucu bizim" kanıtı sayıyordu. Sonuç: 8080'de yabancı bir sunucu varken
`/unity/toggle` `already_running` dönüyor, toggle yeşile geçiyor, trafik
yabancıya gidiyor ve eklenecek kapı o yolun İÇİNDE hiç olmuyor.

Buradaki testler gerçek bir HTTP sunucusu ayağa kaldırıyor (mock değil), çünkü
ölçülmek istenen şey tam olarak "bir yanıtı nasıl sınıflandırıyoruz".
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from unity_ai_mcp.mcp_identity import (IDENTITY_MARKERS, ServerIdentity,
                                       probe_port_identity)

# Sunucunun gerçek 401 gövdesinin birebir kopyası (local_auth.py:136-142).
# Ayrışırsa test_sunucu_401_govdesi_probe_ile_uyusuyor ısırır.
GERCEK_401_GOVDESI = {
    "success": False,
    "error": (
        "Missing or invalid X-API-Key. The local MCP transport requires the "
        "shared secret from ~/.unity-mcp/local-api-token."
    ),
}


def _sunucu_baslat(status: int, body, content_type: str = "application/json"):
    """Verilen yanıtı dönen tek kullanımlık HTTP sunucusu. (port, kapat) döner.

    Port 0 ile bağlanıyor: sabit port kullanmak, geliştiricinin makinesinde o
    port doluysa testi sessizce başka bir şeye karşı koşturur.
    """
    payload = json.dumps(body).encode() if not isinstance(body, bytes) else body

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # test çıktısını kirletmesin
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server.server_port, lambda: (server.shutdown(), server.server_close())


@pytest.fixture
def sunucu():
    kapatilacak = []
    def baslat(status, body, content_type="application/json"):
        port, kapat = _sunucu_baslat(status, body, content_type)
        kapatilacak.append(kapat)
        return port
    yield baslat
    for kapat in kapatilacak:
        kapat()


# ─── Sınıflandırma ──────────────────────────────────────────────────────────


def test_kimse_dinlemiyorsa_none():
    # 1 numaralı port ayrıcalıklı ve hiçbir şey dinlemiyor; bağlantı reddedilir.
    assert probe_port_identity(1).identity == ServerIdentity.NONE


def test_bizim_401_govdemiz_ours(sunucu):
    port = sunucu(401, GERCEK_401_GOVDESI)
    sonuc = probe_port_identity(port)
    assert sonuc.identity == ServerIdentity.OURS
    assert sonuc.detail


def test_kimliksiz_kabul_eden_sunucu_foreign(sunucu):
    """Asıl senaryo: upstream mcp-for-unity'de `X-API-Key` kapısı YOK.

    Kimliksiz çağrıyı kabul eden bir sunucu bizim değildir — kapı orada olmaz.
    """
    port = sunucu(200, {"jsonrpc": "2.0", "result": {}})
    assert probe_port_identity(port).identity == ServerIdentity.FOREIGN


def test_baska_bir_401_foreign(sunucu):
    """Jenerik bir auth proxy'si de 401 döner; iz aranmasının sebebi bu."""
    port = sunucu(401, {"success": False, "error": "Unauthorized"})
    assert probe_port_identity(port).identity == ServerIdentity.FOREIGN


def test_yalniz_bir_iz_yetmez(sunucu):
    """Tek iz ("X-API-Key") başka bir üründe de geçebilir; İKİSİ birden aranıyor."""
    port = sunucu(401, {"success": False, "error": "Missing X-API-Key header"})
    assert probe_port_identity(port).identity == ServerIdentity.FOREIGN


def test_mcp_olmayan_servis_foreign(sunucu):
    """8080'de alakasız bir dev server: /mcp diye bir yolu yok."""
    port = sunucu(404, b"<html>Not Found</html>", content_type="text/html")
    assert probe_port_identity(port).identity == ServerIdentity.FOREIGN


def test_json_olmayan_govdede_de_iz_aranir(sunucu):
    """Gövde JSON değilse ham metinde aranıyor — sessizce FOREIGN dememek için."""
    govde = ("Missing or invalid X-API-Key. The local MCP transport requires "
             "the shared secret from ~/.unity-mcp/local-api-token.").encode()
    port = sunucu(401, govde, content_type="text/plain")
    assert probe_port_identity(port).identity == ServerIdentity.OURS


def test_govde_kesilse_bile_patlamaz(sunucu):
    """Yabancı sunucu devasa gövde dönerse okuma sınırlanıyor (DoS yüzeyi)."""
    port = sunucu(401, b"x" * 200_000, content_type="text/plain")
    assert probe_port_identity(port).identity == ServerIdentity.FOREIGN


# ─── Sessiz ayrışma tripwire'ı ──────────────────────────────────────────────


def test_sunucu_401_govdesi_probe_ile_uyusuyor():
    """Probe'un aradığı izleri sunucu gerçekten üretiyor mu?

    ⚠️ Bu bir KAYNAK METİN tripwire'ı, davranış testi DEĞİL: unity-mcp sunucusu
    ayrı bir paket ve bu suite onu import edemiyor. Ölçtüğü tek şey sessiz
    ayrışma — mesaj değişirse probe hiçbir sunucuyu tanıyamaz hale gelir,
    `is_running()` daima False döner ve ürün "8080 hep yabancı" der. Bu, dıştan
    hiç görünmeyen bir arıza; gürültülü hale getiriliyor.
    """
    kok = Path(__file__).resolve().parents[2]
    auth = (kok / "unity-mcp/Server/src/core/local_auth.py").read_text()
    sabitler = (kok / "unity-mcp/Server/src/core/constants.py").read_text()

    # Sabitlerin DEĞERLERİ probe'un aradığı izlerle aynı mı
    assert re.search(r'API_KEY_HEADER\s*=\s*"X-API-Key"', sabitler)
    assert re.search(r'LOCAL_API_TOKEN_FILE_HINT\s*=\s*"~/\.unity-mcp/local-api-token"', auth)

    # ve bu iki sabit gerçekten 401 gövdesinde kullanılıyor mu
    assert "Missing or invalid {API_KEY_HEADER}" in auth
    assert "{LOCAL_API_TOKEN_FILE_HINT}" in auth
    assert "status_code=401" in auth

    # probe'un beklediği izler bu mesajdan üretilebilir mi
    uretilen = GERCEK_401_GOVDESI["error"]
    for iz in IDENTITY_MARKERS:
        assert iz in uretilen, f"{iz!r} sunucunun ürettiği mesajda yok"


# ─── Manager bağlantısı — asıl arızanın yaşadığı yer ────────────────────────


@pytest.fixture
def manager(monkeypatch):
    """Singleton manager, kimlik cache'i temizlenmiş ve kendi sürecimiz yok.

    Cache'i sıfırlamak ŞART: `unity_mcp_manager` modül düzeyinde tek örnek, yani
    bir testin ölçümü 2 sn boyunca diğerine sızıyor.
    """
    from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager as m
    monkeypatch.setattr(m, "process", None)
    m.invalidate_identity_cache()
    yield m
    m.invalidate_identity_cache()


def _kimlik(monkeypatch, identity, detail="test"):
    from unity_ai_mcp import unity_mcp_manager as modul
    from unity_ai_mcp.mcp_identity import Occupant
    monkeypatch.setattr(modul, "probe_port_identity",
                        lambda port, host="127.0.0.1": Occupant(identity, detail))


def test_yabanci_sunucu_ayakta_sayilmaz(manager, monkeypatch):
    """ASIL BULGU. Eskiden `/health` 200 döndüğü için burası True idi."""
    _kimlik(monkeypatch, ServerIdentity.FOREIGN, "/mcp kimliksiz kabul etti (HTTP 200)")
    assert manager.is_running() is False


def test_kimlik_kapisi_olan_sunucu_ayakta_sayilir(manager, monkeypatch):
    _kimlik(monkeypatch, ServerIdentity.OURS, "kimlik kapısı doğrulandı")
    assert manager.is_running() is True


def test_kendi_surecimiz_canliysa_probe_atilmaz(manager, monkeypatch):
    """Süreç sahipliği probe'dan güçlü kanıt; her yoklamada HTTP isteği doğmamalı."""
    cagrildi = []
    from unity_ai_mcp import unity_mcp_manager as modul
    monkeypatch.setattr(modul, "probe_port_identity",
                        lambda *a, **k: cagrildi.append(1))

    class CanliSurec:
        pid = 4242
        def poll(self):
            return None

    monkeypatch.setattr(manager, "process", CanliSurec())
    assert manager.is_running() is True
    assert cagrildi == []


def test_yabanci_port_durumu_blocked_ve_sebepli(manager, monkeypatch):
    """`off` ile `blocked` ayrı olmalı: biri kullanıcı eylemi gerektiriyor."""
    import asyncio

    from unity_ai_mcp import mcp_port_guard as guard
    _kimlik(monkeypatch, ServerIdentity.FOREIGN, "/mcp kimliksiz kabul etti (HTTP 200)")
    monkeypatch.setattr(
        guard, "foreign_port_owner_infos",
        lambda port=8080: [guard.ProcessInfo(
            pid=4242, ppid=1,
            command="/usr/local/bin/nextjs-dev --port 8080 --token s3cr3t-of-another-app")],
    )

    durum = asyncio.run(manager.get_status())
    assert durum["status"] == "blocked"
    assert "8080" in durum["reason"]
    # Kullanıcıya PID değil ADI da söylenmeli — "PID 4242'yi kapatın" uygulanabilir
    # bir talimat değil.
    assert "nextjs-dev" in durum["reason"]
    assert "4242" in durum["reason"]
    # AMA tam komut satırı GÖSTERİLMEMELİ: başka bir programın argv'si onun
    # sırrını taşıyabilir ve biz onu kullanıcı arayüzüne taşımış oluruz.
    # Bu assertion olmadan "adı göster" düzeltmesi "her şeyi göster"e kayabilir
    # ve hiçbir test ısırmaz.
    assert "s3cr3t-of-another-app" not in durum["reason"]
    assert "--port" not in durum["reason"]


def test_surec_tablosu_okunamazsa_sebep_yine_verilir(manager, monkeypatch):
    """`lsof` yoksa ad söylenemez ama SESSİZ KALINMAZ — asıl düzeltilen buydu."""
    import asyncio

    from unity_ai_mcp import mcp_port_guard as guard
    _kimlik(monkeypatch, ServerIdentity.FOREIGN, "/mcp kimliksiz kabul etti (HTTP 200)")
    monkeypatch.setattr(guard, "foreign_port_owner_infos", lambda port=8080: [])

    durum = asyncio.run(manager.get_status())
    assert durum["status"] == "blocked"
    assert durum["reason"]
    assert "8080" in durum["reason"]


def test_kapali_port_off_dondurur_reason_bos(manager, monkeypatch):
    """Fazla-geniş yön: hiçbir şey dinlemiyorken 'blocked' demek ürünü kırar."""
    import asyncio

    _kimlik(monkeypatch, ServerIdentity.NONE, "port dinlenmiyor")
    durum = asyncio.run(manager.get_status())
    assert durum["status"] == "off"
    assert durum["reason"] is None


def test_baslatma_lsof_olmadan_da_reddedilir(manager, monkeypatch):
    """İkinci muhafız: süreç sorgusu fail-open olsa bile kimlik probe'u tutuyor.

    `list_listening_pids` boş dönüyor (lsof yok senaryosu) — eski tek muhafız
    bu durumda hiçbir şey yapmıyor ve uvx sessizce bind edemeden ölüyordu.
    """
    from unity_ai_mcp import mcp_port_guard as guard
    _kimlik(monkeypatch, ServerIdentity.FOREIGN, "/mcp kimliksiz kabul etti (HTTP 200)")
    monkeypatch.setattr(guard, "list_listening_pids", lambda port: [])
    monkeypatch.setattr(manager, "_starting", False)

    # Buraya kadar gelirse gerçek uvx spawn'ı olurdu.
    assert manager.start_server() is False
    assert "8080" in (manager.last_error or "")


def test_cache_baslatma_sonrasi_dusuyor(manager, monkeypatch):
    """Başlattığımız sunucu 2 sn boyunca 'yabancı' görünmemeli."""
    _kimlik(monkeypatch, ServerIdentity.FOREIGN)
    assert manager.is_running() is False

    _kimlik(monkeypatch, ServerIdentity.OURS)
    assert manager.is_running() is False, "cache henüz düşmedi — beklenen"

    manager.invalidate_identity_cache()
    assert manager.is_running() is True
