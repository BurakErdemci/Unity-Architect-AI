from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from app.mcp.unity_mcp_manager import unity_mcp_manager

router = APIRouter(prefix="/mcp", tags=["mcp"])

class MCPInstallRequest(BaseModel):
    workspace_path: str

class MCPStatusResponse(BaseModel):
    is_running: bool
    active_workspace: Optional[str] = None
    mcp_port: int

@router.post("/unity/install")
async def install_unity_mcp(request: MCPInstallRequest):
    """Belirtilen Unity projesine MCP paketini kurar."""
    success = unity_mcp_manager.install_package(request.workspace_path)
    if not success:
        raise HTTPException(status_code=400, detail="Paket kurulumu başarısız oldu. Path doğru mu?")
    return {"status": "success", "message": "Unity MCP paketi başarıyla kuruldu."}

@router.get("/unity/status", response_model=MCPStatusResponse)
async def get_unity_mcp_status():
    """Unity MCP sunucusunun (localhost:8080) durumunu döner."""
    is_running = await unity_mcp_manager.check_health()
    return {
        "is_running": is_running,
        "active_workspace": unity_mcp_manager.active_workspace,
        "mcp_port": unity_mcp_manager.mcp_port
    }

@router.post("/unity/start")
async def start_unity_mcp_monitor(request: MCPInstallRequest):
    """Belirli bir proje için MCP izleyicisini başlatır."""
    unity_mcp_manager.start_server_monitor(request.workspace_path)
    return {"status": "success", "message": f"İzleyici {request.workspace_path} için başlatıldı."}

def create_mcp_router():
    return router
