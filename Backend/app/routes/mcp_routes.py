from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager

router = APIRouter(prefix="/mcp", tags=["mcp"])


class MCPInstallRequest(BaseModel):
    workspace_path: str


class MCPToggleRequest(BaseModel):
    enabled: bool
    workspace_path: Optional[str] = None


@router.post("/unity/toggle")
async def toggle_unity_mcp(req: MCPToggleRequest, background_tasks: BackgroundTasks):
    """
    Unity MCP sunucusunu başlatır veya durdurur.
    Toggle ON için Unity Editor'ün açık olması ZORUNLUDUR.
    """
    if req.enabled:
        # Unity açık değilse hemen hata dön
        if not unity_mcp_manager.is_unity_running():
            raise HTTPException(
                status_code=409,
                detail="Unity Editor açık değil. Lütfen önce Unity'yi açın."
            )

        if unity_mcp_manager.is_running():
            status = await unity_mcp_manager.get_status()
            return {"status": "already_running", **status}

        success = unity_mcp_manager.start_server()
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Unity MCP sunucusu başlatılamadı."
            )

        package_installed = False
        if req.workspace_path:
            # Manifest'i hemen kur ama autoconnect scriptini server hazır olunca yaz.
            # Böylece Unity plugin bağlanmaya çalıştığında server zaten ayakta olur
            # ve Unity Console'da "Connection failed" hatası çıkmaz.
            package_installed = unity_mcp_manager.install_package(req.workspace_path, write_autoconnect=False)
            background_tasks.add_task(unity_mcp_manager.write_autoconnect_when_ready, req.workspace_path)

        return {
            "status": "started",
            "port": unity_mcp_manager.mcp_port,
            "package_installed": package_installed,
        }
    else:
        unity_mcp_manager.stop_server()
        from tools.unity_mcp_tools import unload_unity_tools
        unload_unity_tools()
        if req.workspace_path:
            unity_mcp_manager._write_autoconnect_script(req.workspace_path, auto_start=False)
        return {"status": "stopped"}


@router.get("/unity/status")
async def get_unity_mcp_status():
    """Unity MCP sunucusunun ve Unity Editor bağlantısının durumunu döner."""
    from tools.unity_mcp_tools import get_unity_tool_definitions, load_unity_tools_async
    status = await unity_mcp_manager.get_status()

    # Unity bağlandıysa ve tool listesi boşsa yükle
    if status["status"] == "connected" and not get_unity_tool_definitions():
        import asyncio
        asyncio.create_task(load_unity_tools_async())

    return status


@router.get("/unity/console")
async def get_unity_console():
    """Unity Editor Console loglarını döner (read_console MCP tool)."""
    from tools.unity_mcp_tools import is_unity_tool, get_unity_tool_functions
    if not is_unity_tool("read_console"):
        return {"logs": [], "connected": False}
    try:
        fn = get_unity_tool_functions().get("read_console")
        result = fn(count=50) if fn else {}
        logs = result.get("logs") or result.get("result") or []
        return {"logs": logs, "connected": True}
    except Exception as e:
        return {"logs": [], "connected": False, "error": str(e)}


@router.post("/unity/install")
async def install_unity_mcp(request: MCPInstallRequest):
    """Belirtilen Unity projesine manifest.json üzerinden MCP paketini kurar."""
    success = unity_mcp_manager.install_package(request.workspace_path)
    if not success:
        raise HTTPException(status_code=400, detail="Paket kurulumu başarısız.")
    return {"status": "success", "message": "Unity MCP paketi başarıyla kuruldu."}


def create_mcp_router():
    return router
