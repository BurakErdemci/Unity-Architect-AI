"""
Unity MCP Client — unity-mcp sunucusuna MCP protokolüyle bağlanır.

Tool listesi ve tanımları sunucudan dinamik olarak çekilir.
Elle wrapper yazmaya gerek yok — unity-mcp'deki 40+ tool otomatik gelir.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)

UNITY_MCP_URL = "http://127.0.0.1:8080"
UNITY_MCP_ENDPOINT = f"{UNITY_MCP_URL}/mcp"

# Cache — toggle açıldığında doldurulur
_cached_tools: List[Dict] = []
_cached_functions: Dict[str, Any] = {}


# ── MCP Client ────────────────────────────────────────────────────────────────

async def _fetch_tools_from_server() -> List:
    """MCP tools/list ile sunucudaki tüm tool'ları çeker."""
    async with streamablehttp_client(UNITY_MCP_ENDPOINT) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return result.tools


async def _call_tool_on_server(tool_name: str, params: Dict[str, Any]):
    """MCP tools/call ile unity-mcp'de bir tool çalıştırır."""
    async with streamablehttp_client(UNITY_MCP_ENDPOINT) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, params)
            return result


# ── Sync Wrappers ─────────────────────────────────────────────────────────────

def _run_async(coro):
    """Async coroutine'i senkron context'ten çalıştırır."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Zaten async context içindeyiz — thread'de çalıştır
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=15)
        return loop.run_until_complete(coro)
    except Exception:
        return asyncio.run(coro)


def _make_tool_function(tool_name: str):
    """Verilen tool adı için çağrılabilir bir wrapper fonksiyon üretir."""
    def tool_fn(**kwargs) -> Dict[str, Any]:
        # None değerleri filtrele
        params = {k: v for k, v in kwargs.items() if v is not None}
        try:
            result = _run_async(_call_tool_on_server(tool_name, params))
            # MCP CallToolResult → dict'e çevir
            if hasattr(result, 'content'):
                text_parts = [c.text for c in result.content if hasattr(c, 'text')]
                return {"success": not result.isError, "result": "\n".join(text_parts)}
            return {"success": True, "result": str(result)}
        except httpx.ConnectError:
            return {"success": False, "error": "Unity MCP bağlantısı kurulamadı. Toggle açık mı?"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    tool_fn.__name__ = tool_name
    return tool_fn


def _mcp_schema_to_tool_def(mcp_tool) -> Dict:
    """MCP Tool nesnesini tool_registry formatına çevirir."""
    schema = {}
    if hasattr(mcp_tool, 'inputSchema') and mcp_tool.inputSchema:
        s = mcp_tool.inputSchema
        schema = {
            "type": s.get("type", "object"),
            "properties": s.get("properties", {}),
            "required": s.get("required", []),
        }
    else:
        schema = {"type": "object", "properties": {}, "required": []}

    return {
        "name": mcp_tool.name,
        "description": mcp_tool.description or f"Unity MCP: {mcp_tool.name}",
        "parameters": schema,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def load_unity_tools() -> bool:
    """Sync versiyon — CLI/test context'inden çağrılır."""
    global _cached_tools, _cached_functions
    try:
        mcp_tools = _run_async(_fetch_tools_from_server())
        _cached_tools = [_mcp_schema_to_tool_def(t) for t in mcp_tools]
        _cached_functions = {t.name: _make_tool_function(t.name) for t in mcp_tools}
        logger.info(f"[UnityMCP] {len(_cached_tools)} tool yüklendi: {[t['name'] for t in _cached_tools]}")
        return True
    except Exception as e:
        logger.warning(f"[UnityMCP] Tool listesi alınamadı: {e}")
        _cached_tools = []
        _cached_functions = {}
        return False


async def load_unity_tools_async() -> bool:
    """Async versiyon — FastAPI route context'inden çağrılır (event loop çakışmasını önler)."""
    global _cached_tools, _cached_functions
    try:
        mcp_tools = await _fetch_tools_from_server()
        _cached_tools = [_mcp_schema_to_tool_def(t) for t in mcp_tools]
        _cached_functions = {t.name: _make_tool_function(t.name) for t in mcp_tools}
        logger.info(f"[UnityMCP] {len(_cached_tools)} tool yüklendi: {[t['name'] for t in _cached_tools]}")
        # Bağlantı kurulunca Unity Console'a bilgi logu gönder
        try:
            await _call_tool_on_server("execute_code", {
                "code": 'UnityEngine.Debug.Log("<color=#4FC3F7><b>[Unity Architect AI]</b></color> MCP bağlantısı kuruldu ✓ — AI artık Unity Editor\'ı kontrol edebilir.");'
            })
        except Exception:
            pass  # Log gönderilemese bile tool yüklemesi başarılı sayılır
        return True
    except Exception as e:
        logger.debug(f"[UnityMCP] Tool listesi alınamadı (Unity henüz bağlanmadı): {e}")
        _cached_tools = []
        _cached_functions = {}
        return False


def unload_unity_tools():
    """Toggle OFF olduğunda cache'i temizler."""
    global _cached_tools, _cached_functions
    _cached_tools = []
    _cached_functions = {}
    logger.info("[UnityMCP] Tool'lar kaldırıldı.")


def get_unity_tool_definitions() -> List[Dict]:
    return list(_cached_tools)


def get_unity_tool_functions() -> Dict[str, Any]:
    return dict(_cached_functions)


def is_unity_tool(tool_name: str) -> bool:
    return tool_name in _cached_functions
