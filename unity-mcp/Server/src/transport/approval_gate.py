"""Onay kapısı — unityMCP mutasyon araçları kullanıcı onayı olmadan geçmez.

Bu modül K1'in boğazı. Gerekçesi ölçüldü (28–29 Tem 2026): 9 sağlayıcının
9'u da Unity'ye aynı uçtan (`127.0.0.1:8080/mcp`) gidiyor ve hiçbiri kendi
kapısını kurmuyor — Cursor `--trust --approve-mcps --force` ile, Copilot
`--allow-tool unityMCP` ile, Codex `default_tools_approval_mode="approve"` ile
geliyor. Ürünün kendi izin geri çağırımı yalnız Anthropic yolunu kapsıyordu,
yani altı sağlayıcıda mutasyon araçları onaysız çalışıyordu. Kapıyı buraya
koymanın sebebi bu: **tek boğaz, sağlayıcıdan bağımsız.**

Tasarımın iki kuralı:

1. **Politika burada DEĞİL.** Sunucu yalnız "bu çağrı yazma mı" sorusunu kütükten
   cevaplar ve yazma ise backend'e sorar. Modun (auto/plan/step) ne olduğunu,
   kartın kime gideceğini, oto-onay verilip verilmeyeceğini backend bilir. İki
   yerde politika tutmak, ikisinin zamanla ayrışması demektir.
2. **Fail-CLOSED.** Backend'e ulaşılamıyorsa (ürün kapalı, port kapalı, token
   yok) mutasyon REDDEDİLİR, okumalar çalışmaya devam eder. Kullanıcı kararı
   (29 Tem): reddedilen alternatif *"ürün yoksa kapıyı hiç kurma"* idi — o,
   güvenlik sınırını "uygulama açık mı" sorusuna bağlar ve kapı "ürünü kapat"
   denerek atlatılır.

⚠️ Sır ORTAMDAN okunuyor, dosyadan değil. Ürün token'ı zaten bu sürecin
ortamına koyuyor (`unity_mcp_manager.py` → `overrides={"LOCAL_APP_TOKEN": ...}`)
ve ürünün kendi doğruluk kaynağı da ortam (`main.py` onu dosyaya YAZAN taraf).
Sırrın ikinci bir okuyucusunu buraya yazmak, `local_token_file`'da sertleştirilen
bağ/junction/TOCTOU korumalarının sertleştirilmemiş bir kopyasını üretirdi.
Token yoksa backend kimliksiz çağrıyı reddeder ve kapı fail-closed davranır —
yani eksik token kabule değil REDDE dönüşür.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Mapping

import httpx

from services.registry.tool_actions import classify

logger = logging.getLogger("mcp-for-unity-server")

_BACKEND_URL = os.environ.get(
    "UNITYAI_URL", os.environ.get("ANTIGRAVITY_URL", "http://localhost:8000")
)

# `approval_bridge.py` ile BİLEREK aynı: aynı uçları, aynı bekleme bütçesiyle
# kullanan iki istemcinin farklı zaman aşımlarına sahip olması, aynı kartın bir
# tarafta yaşayıp diğerinde ölmesi demek olurdu.
_POST_DENEME = 10          # 10 × 1 sn — ürün henüz açılıyorsa yetişsin
_BEKLEME_ADIMI = 0.5
_BEKLEME_ADEDI = 360       # 180 sn: diff okuyup karar vermek için makul süre


class ApprovalDenied(RuntimeError):
    """Kapı reddetti. FastMCP bunu araç hatasına çeviriyor, çağrı ÇALIŞMIYOR."""


def _headers() -> dict[str, str]:
    token = os.environ.get("LOCAL_APP_TOKEN", "")
    if not token:
        logger.warning(
            "[approval-gate] LOCAL_APP_TOKEN ortamda yok — onay çağrısı kimliksiz "
            "gidiyor ve backend'in fail-closed kapısında reddedilecek."
        )
    return {"X-Session-Token": token} if token else {}


async def _onay_iste(tool_name: str, params: Mapping[str, Any]) -> dict:
    """Backend'e sorar. Dönen sözlükte `approved` bool'u vardır."""
    gate_id = uuid.uuid4().hex[:10]
    govde = {
        "gate_id": gate_id,
        "tool": tool_name,
        "params": dict(params or {}),
        # Workspace'i BİLEREK boş gönderiyoruz: bu süreç ürünün açtığı tek
        # sunucu ve workspace oturum ortasında değişebiliyor, yani başlangıçta
        # geçirilen bir değer bayat olurdu. Backend hangi workspace'in aktif
        # olduğunu kendi bilir.
        "workspace_path": "",
    }

    gonderildi = False
    for deneme in range(_POST_DENEME):
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    f"{_BACKEND_URL}/mcp-approval-request",
                    json=govde,
                    headers=_headers(),
                )
            if resp.status_code == 200:
                veri = resp.json()
                if veri.get("status") == "resolved":
                    return veri
                gonderildi = True
                break
            # 401/503: kimlik ya da fail-closed kapı. Yeniden denemek bunu
            # değiştirmez, ve 10 sn boşuna beklemek kullanıcıyı bekletir.
            if resp.status_code in (401, 403):
                return {
                    "approved": False,
                    "error": f"Onay servisi kimliği reddetti (HTTP {resp.status_code}).",
                }
        except Exception as e:
            logger.warning("[approval-gate] POST %s başarısız: %s", deneme + 1, e)
        await asyncio.sleep(1.0)

    if not gonderildi:
        return {
            "approved": False,
            "error": "Onay servisine ulaşılamadı; işlem güvenlik nedeniyle reddedildi.",
        }

    for i in range(_BEKLEME_ADEDI):
        await asyncio.sleep(_BEKLEME_ADIMI)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    f"{_BACKEND_URL}/mcp-approval-result/{gate_id}",
                    headers=_headers(),
                )
            veri = res.json()
            if veri.get("status") != "pending":
                return veri
        except Exception as e:
            if i % 20 == 0:
                logger.warning("[approval-gate] sonuç yoklaması hatası: %s", e)

    return {"approved": False, "error": "Onay zaman aşımına uğradı (180 sn)."}


async def kapiyi_gec(tool_name: str, params: Mapping[str, Any] | None) -> None:
    """Yazma ise onay ister; onay yoksa `ApprovalDenied` fırlatır.

    Okuma araçlarında hiçbir ağ çağrısı yapılmaz — keşif araçları (hiyerarşi
    okuma, konsol okuma) her turda çağrılıyor ve onlara ağ maliyeti bindirmek
    kapıyı kullanıcının kapatmak isteyeceği bir şeye çevirirdi.

    Sınıflandırma kütükten geliyor (`tool_actions.json`, 45 araç) ve kütük
    FAIL-CLOSED: bilinmeyen araç ya da bilinmeyen action `write` sayılıyor.
    `batch_execute` gibi alt-çağrı taşıyan araçlarda `classify` özyineliyor,
    yani dış ada bakıp iç mutasyonu kaçırmıyor.
    """
    if classify(tool_name, params or {}) == "read":
        return

    sonuc = await _onay_iste(tool_name, params or {})
    if sonuc.get("approved"):
        if sonuc.get("automatic"):
            logger.info("[approval-gate] %s otomatik onaylandı (aktif auto turu).", tool_name)
        else:
            logger.info("[approval-gate] %s kullanıcı tarafından onaylandı.", tool_name)
        return

    sebep = sonuc.get("error") or "Kullanıcı onayı verilmedi."
    logger.warning("[approval-gate] %s REDDEDİLDİ: %s", tool_name, sebep)
    raise ApprovalDenied(
        f"'{tool_name}' onay gerektiriyor ve onaylanmadı: {sebep}"
    )
