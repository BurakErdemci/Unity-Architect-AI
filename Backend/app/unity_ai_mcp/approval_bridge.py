"""
Approval Bridge — MCP server'dan Antigravity backend'e onay isteği gönderir.

Akış:
  MCP tool çağrısı → approval_bridge → POST /mcp-approval-request (retry ile)
  → Frontend 1s polling ile yakalar → kullanıcı onaylar/reddeder
  → GET /mcp-approval-result/{gate_id} ile sonuç alınır
"""
import uuid
import asyncio
import logging
import httpx
from typing import Any

import os
logger = logging.getLogger(__name__)
BACKEND_URL = os.environ.get("UNITYAI_URL", os.environ.get("ANTIGRAVITY_URL", "http://localhost:8000"))


def _get_headers() -> dict:
    """Backend çağrıları için auth başlığı; token yoksa boş dict (dev modu).

    Token artık ortamda GELMEYEBİLİR: bu süreci claude/codex gibi bir CLI
    başlatıyor ve bizim ortamımızı miras almıyor. Config dosyasına ya da argv'ye
    yazmak yerine 0600 bir dosyadan okunuyor — sebebi local_token_file'da.
    """
    import sys
    _app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _app not in sys.path:
        sys.path.insert(0, _app)
    from local_token_file import read_local_app_token

    token = read_local_app_token()
    if not token:
        logger.warning(
            "[approval_bridge] LOCAL_APP_TOKEN bulunamadı (ne ortamda ne dosyada) "
            "— backend çağrıları kimliksiz gidiyor ve fail-closed kapıda 503 alacak."
        )
    return {"X-Session-Token": token} if token else {}


async def request_approval(
    tool_name: str,
    params: dict[str, Any],
    workspace_path: str,
) -> dict:
    """
    Tehlikeli bir tool çağrısı için kullanıcı onayı ister.
    Backend'e ulaşana kadar 10 saniye boyunca retry yapar.
    Ulaşabilirse 60 saniye kullanıcı cevabını bekler.
    """
    gate_id = uuid.uuid4().hex[:10]
    logger.info(f"[approval_bridge] {tool_name} için onay isteniyor (gate: {gate_id})")

    # POST — 10 saniye boyunca 1s aralıkla retry
    posted = False
    immediate_result = None
    for attempt in range(10):
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    f"{BACKEND_URL}/mcp-approval-request",
                    json={
                        "gate_id": gate_id,
                        "tool": tool_name,
                        "params": params,
                        "workspace_path": workspace_path,
                        "approval_turn_token": os.environ.get(
                            "UNITYAI_APPROVAL_TURN_TOKEN", ""
                        ),
                    },
                    headers=_get_headers(),
                )
                if resp.status_code == 200:
                    posted = True
                    data = resp.json()
                    if data.get("status") == "resolved":
                        immediate_result = data
                    logger.info(f"[approval_bridge] POST başarılı (deneme {attempt+1})")
                    break
        except Exception as e:
            logger.warning(f"[approval_bridge] POST denemesi {attempt+1} başarısız: {e}")
            await asyncio.sleep(1.0)

    if not posted:
        logger.warning(f"[approval_bridge] Backend'e ulaşılamadı — {tool_name} reddediliyor")
        return {
            "approved": False,
            "error": "Onay servisine ulaşılamadı; işlem güvenlik nedeniyle reddedildi.",
        }

    if immediate_result is not None:
        logger.info(
            f"[approval_bridge] Aktif Auto turunda anında çözüldü (gate: {gate_id})"
        )
        return immediate_result

    # Kullanıcı cevabını bekle — 360 × 0.5s = 180 saniye (diff incelemek için makul süre)
    logger.info(f"[approval_bridge] Kullanıcı cevabı bekleniyor (gate: {gate_id})")
    for i in range(360):
        await asyncio.sleep(0.5)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{BACKEND_URL}/mcp-approval-result/{gate_id}", headers=_get_headers())
                data = res.json()
                if data.get("status") != "pending":
                    logger.info(f"[approval_bridge] Cevap alındı: {data}")
                    return data
        except Exception as e:
            if i % 10 == 0:  # Her 5 saniyede bir logla
                logger.warning(f"[approval_bridge] Polling hatası: {e}")
            continue

    logger.warning(f"[approval_bridge] Zaman aşımı (gate: {gate_id})")
    return {"approved": False, "error": "Zaman aşımı (180s)"}
