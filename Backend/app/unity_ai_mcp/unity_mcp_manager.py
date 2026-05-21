import os
import subprocess
import asyncio
import httpx
import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)

# Unity bağlantı durumu
class UnityMCPStatus:
    OFF = "off"            # Sunucu kapalı
    STARTING = "starting"  # Sunucu başlatılıyor
    RUNNING = "running"    # Sunucu açık, Unity henüz bağlanmadı
    CONNECTED = "connected" # Sunucu açık + Unity bağlı


class UnityMCPManager:
    """
    Unity MCP Python sunucusunu (unity-mcp/Server) subprocess olarak yönetir.
    Toggle ON → HTTP sunucu başlar (localhost:8080)
    Unity Editor (plugin yüklüyse) bu sunucuya WebSocket ile bağlanır.
    """

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.mcp_port = 8080
        self._starting = False  # Çift başlatmayı önler
        self.project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        self.server_dir = os.path.join(self.project_root, "unity-mcp", "Server")
        self.local_mcp_source = os.path.join(self.project_root, "unity-mcp", "MCPForUnity")
        self.unity_mcp_repo = f"file:{self.local_mcp_source}"

    # ─── Subprocess Yönetimi ─────────────────────────────────────────────────

    def is_running(self) -> bool:
        """Port 8080'i dinleyen bir süreç varsa True döner (bizim veya Unity'nin başlattığı)."""
        import socket
        try:
            with socket.create_connection(("127.0.0.1", self.mcp_port), timeout=0.5):
                return True
        except OSError:
            return False

    def is_unity_running(self) -> bool:
        """Unity Editor süreci çalışıyor mu kontrol eder."""
        import platform
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq Unity.exe"],
                    capture_output=True, text=True, timeout=3,
                )
                return "Unity.exe" in result.stdout
            else:
                # Unity Hub'ı filtrele — sadece Unity Editor binary'sini eşleştir
                result = subprocess.run(
                    ["pgrep", "-f", "Unity.app/Contents/MacOS/Unity"],
                    capture_output=True, text=True, timeout=3,
                )
                return bool(result.stdout.strip())
        except Exception:
            return False

    def _get_uvx(self) -> str:
        """uvx binary'sini bulur."""
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, ".local", "bin", "uvx"),
            "/usr/local/bin/uvx",
            "uvx",
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        return "uvx"

    def start_server(self) -> bool:
        """
        Unity MCP HTTP sunucusunu başlatır.
        Unity'nin kendi arayüzüyle aynı komutu kullanır (uvx).
        Zaten çalışıyorsa veya başlatılıyorsa True döner (idempotent).
        """
        if self._starting or self.is_running():
            return True
        self._starting = True

        uvx = self._get_uvx()
        cmd = [
            uvx,
            "--no-cache",
            "--from", self.server_dir,
            "mcp-for-unity",
            "--transport", "http",
            "--http-url", f"http://127.0.0.1:{self.mcp_port}",
            "--project-scoped-tools",
        ]

        log_path = os.path.join(self.project_root, "Backend", "unity_mcp_server.log")
        try:
            log_file = open(log_path, "a", encoding="utf-8")
            mcp_env = {**os.environ, "LOCAL_APP_TOKEN": os.environ.get("LOCAL_APP_TOKEN", "")}
            self.process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=log_file,
                env=mcp_env,
            )
            logger.info(f"[UnityMCP] Sunucu başlatıldı (PID: {self.process.pid}, port: {self.mcp_port})")
            self._starting = False
            return True
        except Exception as e:
            logger.error(f"[UnityMCP] Başlatılamadı: {e}")
            self._starting = False
            return False

    def stop_server(self) -> None:
        """
        MCP sunucusunu durdurur.
        Kendi subprocess'imiz varsa onu, yoksa port 8080'deki süreci öldürür.
        """
        # Kendi subprocess'imizi durdur
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

        # Port 8080'i sadece LISTEN state'inde tutan süreçleri öldür.
        # -sTCP:LISTEN olmadan Unity Editor gibi CLIENT bağlantıları da listede çıkar
        # ve onları öldürmek tüm Unity'yi kapatır.
        if self.is_running():
            import signal
            try:
                result = subprocess.run(
                    ["lsof", "-ti", f":{self.mcp_port}", "-sTCP:LISTEN"],
                    capture_output=True, text=True
                )
                pids = [p for p in result.stdout.strip().split() if p]
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                if pids:
                    logger.info(f"[UnityMCP] Port {self.mcp_port} LISTEN temizlendi (PID'ler: {pids})")
            except Exception as e:
                logger.warning(f"[UnityMCP] Port temizlenemedi: {e}")

        self._starting = False
        logger.info("[UnityMCP] Sunucu durduruldu.")

    # ─── Health & Status ─────────────────────────────────────────────────────

    async def check_health(self) -> bool:
        """HTTP sunucusunun ayakta olduğunu kontrol eder (/health)."""
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"http://localhost:{self.mcp_port}/health", timeout=2.0
                )
                return res.status_code == 200
        except Exception:
            return False

    async def check_unity_connected(self) -> bool:
        """Unity Editor'ün (plugin) sunucuya bağlı olup olmadığını kontrol eder."""
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"http://localhost:{self.mcp_port}/api/instances", timeout=2.0
                )
                if res.status_code == 200:
                    data = res.json()
                    return bool(data.get("instances"))
        except Exception:
            pass
        return False

    async def get_status(self) -> dict:
        """
        Tam durum bilgisini döner:
        {
          "status": "off" | "starting" | "running" | "connected",
          "pid": int | None,
          "port": 8080,
          "instances": [...]
        }
        """
        if not self.is_running():
            return {"status": UnityMCPStatus.OFF, "pid": None, "port": self.mcp_port, "instances": []}

        pid = self.process.pid if self.process else None

        healthy = await self.check_health()
        if not healthy:
            return {"status": UnityMCPStatus.STARTING, "pid": pid, "port": self.mcp_port, "instances": []}

        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"http://localhost:{self.mcp_port}/api/instances", timeout=2.0
                )
                instances = res.json().get("instances", []) if res.status_code == 200 else []
        except Exception:
            instances = []

        unity_status = UnityMCPStatus.CONNECTED if instances else UnityMCPStatus.RUNNING
        return {
            "status": unity_status,
            "pid": pid,
            "port": self.mcp_port,
            "instances": instances,
        }

    # ─── Unity Paket Kurulumu ────────────────────────────────────────────────

    async def write_autoconnect_when_ready(self, workspace_path: str, timeout: int = 60) -> bool:
        """
        Server port'u açılana kadar bekler, sonra autoconnect scriptini yazar.
        Bu sayede Unity plugin'i bağlanmaya çalıştığında server zaten hazırdır.
        """
        for _ in range(timeout * 2):
            await asyncio.sleep(0.5)
            if self.is_running():
                await asyncio.sleep(1)  # Port açık ama HTTP handler tam init olmamış olabilir
                self._write_autoconnect_script(workspace_path, auto_start=True)
                logger.info("[UnityMCP] Server hazır — autoconnect scripti yazıldı.")
                return True
        logger.warning("[UnityMCP] Server %ds içinde hazır olmadı, autoconnect scripti yazılmadı.", timeout)
        return False

    def install_package(self, workspace_path: str, write_autoconnect: bool = True) -> bool:
        """
        Unity projesine unity-mcp paketini kurar ve otomatik bağlantı scriptini yazar.
        1. Packages/manifest.json → paket bağımlılığı eklenir
        2. Assets/Editor/UnityArchitectAIMCPSetup.cs → [InitializeOnLoad] script
           Bu script Unity açıldığında EditorPrefs'leri set ederek otomatik session başlatır.
        """
        if not workspace_path:
            return False
        manifest_path = os.path.join(workspace_path, "Packages", "manifest.json")
        if not os.path.exists(manifest_path):
            logger.error(f"[UnityMCP] manifest.json bulunamadı: {manifest_path}")
            return False
        try:
            # 1. Paketi manifest.json'a ekle
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            manifest.setdefault("dependencies", {})["com.coplaydev.unity-mcp"] = self.unity_mcp_repo
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

            # 2. Otomatik bağlantı scriptini yaz (write_autoconnect=False ise çağıran handle eder)
            if write_autoconnect:
                self._write_autoconnect_script(workspace_path, auto_start=True)

            logger.info(f"[UnityMCP] Paket + auto-connect scripti kuruldu: {workspace_path}")
            return True
        except Exception as e:
            logger.error(f"[UnityMCP] Paket kurulumu hatası: {e}")
            return False

    def _write_autoconnect_script(self, workspace_path: str, auto_start: bool = False):
        """
        Unity projesi Assets/Editor/ altına [InitializeOnLoad] C# scripti yazar.
        auto_start=True → AutoStartOnLoad=true + domain reload tetiklenir (Unity açıksa anında bağlanır)
        auto_start=False → AutoStartOnLoad=false (Unity açılınca bile bağlanmaz)
        """
        import time
        editor_dir = os.path.join(workspace_path, "Assets", "Editor")
        os.makedirs(editor_dir, exist_ok=True)
        script_path = os.path.join(editor_dir, "UnityArchitectAIMCPSetup.cs")

        auto_start_val = "true" if auto_start else "false"
        timestamp = int(time.time())

        script = f"""\
// Unity Architect AI — MCP bağlantı yapılandırması (güncelleme: {timestamp})
// Bu dosya Unity Architect AI tarafından oluşturulmuştur. Silmeyin.
#if UNITY_EDITOR
using UnityEditor;

namespace UnityArchitectAI
{{
    [InitializeOnLoad]
    internal static class MCPAutoSetup
    {{
        static MCPAutoSetup()
        {{
            EditorPrefs.SetBool("MCPForUnity.UseHttpTransport", true);
            EditorPrefs.SetString("MCPForUnity.HttpUrl", "http://127.0.0.1:{self.mcp_port}");
            EditorPrefs.SetBool("MCPForUnity.AutoStartOnLoad", {auto_start_val});
            EditorPrefs.SetBool("MCPForUnity.ResumeHttpAfterReload", {auto_start_val});
        }}
    }}
}}
#endif
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)
        logger.info(f"[UnityMCP] Auto-connect scripti yazıldı (auto_start={auto_start}): {script_path}")


# Global singleton
unity_mcp_manager = UnityMCPManager()
