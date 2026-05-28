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
    """Return auth header for backend calls. Empty dict if LOCAL_APP_TOKEN not set (dev mode)."""
    token = os.environ.get("LOCAL_APP_TOKEN", "")
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
                    },
                    headers=_get_headers(),
                )
                if resp.status_code == 200:
                    posted = True
                    logger.info(f"[approval_bridge] POST başarılı (deneme {attempt+1})")
                    break
        except Exception as e:
            logger.warning(f"[approval_bridge] POST denemesi {attempt+1} başarısız: {e}")
            await asyncio.sleep(1.0)

    if not posted:
        logger.warning(f"[approval_bridge] Backend'e ulaşılamadı — {tool_name} otomatik onaylanıyor")
        return {"approved": True, "auto": True}

    # Kullanıcı cevabını bekle — 120 × 0.5s = 60 saniye
    logger.info(f"[approval_bridge] Kullanıcı cevabı bekleniyor (gate: {gate_id})")
    for i in range(120):
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
    return {"approved": False, "error": "Zaman aşımı (60s)"}
