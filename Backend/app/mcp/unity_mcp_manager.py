import os
import json
import subprocess
import asyncio
import httpx
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class UnityMCPManager:
    """
    Unity MCP Sunucusu ve Paket Yönetimi Sorumlusu.
    Herhangi bir Unity projesine MCP desteği ekler ve sunucu durumunu izler.
    """
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.active_workspace: Optional[str] = None
        self.mcp_port = 8080
        # Proje kök dizinini bul (unityaıPython)
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.local_mcp_source = os.path.join(self.project_root, "unity-mcp", "MCPForUnity")
        # Unity manifest için yerel dosya referansı
        self.unity_mcp_repo = f"file:{self.local_mcp_source}"

    def install_package(self, workspace_path: str) -> bool:
        """
        Verilen Unity projesinin manifest.json dosyasına unity-mcp paketini ekler.
        Bu işlem 'General' yapıda olup her proje için çalışır.
        """
        if not workspace_path:
            logger.error("Workspace yolu belirtilmedi.")
            return False

        manifest_path = os.path.join(workspace_path, "Packages", "manifest.json")
        if not os.path.exists(manifest_path):
            logger.error(f"Unity Manifest dosyası bulunamadı: {manifest_path}")
            return False

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            if "dependencies" not in manifest:
                manifest["dependencies"] = {}

            # Paketi ekle veya güncelle
            pkg_name = "com.coplaydev.unity-mcp"
            manifest["dependencies"][pkg_name] = self.unity_mcp_repo

            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)
            
            logger.info(f"Muvaffakiyetle tamamlandı: {pkg_name} -> {workspace_path}")
            return True
        except Exception as e:
            logger.error(f"Paket kurulumu sırasında hata oluştu: {str(e)}")
            return False

    async def check_health(self) -> bool:
        """Unity Editor içindeki MCP sunucusunun aktifliğini kontrol eder."""
        try:
            async with httpx.AsyncClient() as client:
                # Roadmap'teki adrese göre sağlık kontrolü
                response = await client.get(f"http://localhost:{self.mcp_port}/health", timeout=2.0)
                return response.status_code == 200
        except Exception:
            return False

    def start_server_monitor(self, workspace_path: str):
        """Unity MCP sunucusunun durumunu izlemeye başlar."""
        self.active_workspace = workspace_path
        logger.info(f"Unity MCP İzleyici başlatıldı. Hedef: {workspace_path}")
        # Not: Gelecekte burada eğer standalone bir server gerekiyorsa subprocess başlatılabilir.

    def stop_server_monitor(self):
        """İzleyiciyi ve varsa süreçleri durdurur."""
        if self.process:
            self.process.terminate()
            self.process = None
        logger.info("Unity MCP İzleyici durduruldu.")

# Global instance
unity_mcp_manager = UnityMCPManager()
