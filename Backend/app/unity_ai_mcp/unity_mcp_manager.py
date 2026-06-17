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
        self._health_cache_ts = 0.0   # is_running() HTTP probe cache (perf)
        self._health_cache_val = False
        import sys
        if getattr(sys, "frozen", False):
            # Frozen build: backend.exe = .../resources/Backend/backend.exe →
            # paket kökü (resources) = backend.exe'nin iki üst dizini. unity-mcp ve uv
            # buraya extraResources ile kopyalanır.
            self.project_root = os.path.dirname(os.path.dirname(sys.executable))
        else:
            self.project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..")
            )
        self.server_dir = os.path.join(self.project_root, "unity-mcp", "Server")
        self.local_mcp_source = os.path.join(self.project_root, "unity-mcp", "MCPForUnity")
        self.unity_mcp_repo = f"file:{self.local_mcp_source}"

    def _ensure_writable_resources(self) -> None:
        """Frozen build: bundled Server/MCPForUnity Program Files altında (yazılamaz).
        - uvx, paketi --from kaynağının içine egg-info yazarak derler → 'Erişim engellendi'
        - Unity, paket dizinine ~UnityDirMonSyncFile~ yazar → 'Couldn't create'
        Bu yüzden ikisini de yazılabilir kullanıcı dizinine kopyalar ve server_dir /
        local_mcp_source / unity_mcp_repo yollarını oraya yöneltir. Idempotent (mtime'a
        göre yeniden kopyalar). Asla exception fırlatmaz."""
        import sys
        if not getattr(sys, "frozen", False):
            return  # Dev: kaynak repo zaten yazılabilir
        import shutil
        base = os.path.join(os.path.expanduser("~"), ".unity_architect_ai", "unity-mcp")
        targets = [("Server", "pyproject.toml", "server_dir"),
                   ("MCPForUnity", "package.json", "local_mcp_source")]
        for sub, marker, attr in targets:
            src = os.path.join(self.project_root, "unity-mcp", sub)
            dst = os.path.join(base, sub)
            try:
                if not os.path.isdir(src):
                    continue
                need = not os.path.isdir(dst)
                if not need:
                    s, d = os.path.join(src, marker), os.path.join(dst, marker)
                    need = (not os.path.isfile(d)) or (
                        os.path.isfile(s) and os.path.getmtime(s) > os.path.getmtime(d)
                    )
                if need:
                    if os.path.isdir(dst):
                        shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst)
                setattr(self, attr, dst)
            except Exception as e:
                logger.warning(f"[UnityMCP] {sub} yazılabilir dizine kopyalanamadı: {e}")
        self.unity_mcp_repo = f"file:{self.local_mcp_source}"

    # ─── Subprocess Yönetimi ─────────────────────────────────────────────────

    def is_running(self) -> bool:
        """Unity MCP server'ımız GERÇEKTEN ayakta mı?

        ÖNEMLİ: 8080 çok yaygın bir port — sadece "biri dinliyor mu" kontrolü yanıltıcıydı:
        alakasız bir servis (örn. başka bir dev server) 8080'deyse toggle yanlışlıkla
        sarıya dönüyor ve CLI config'lerine unityMCP ekleniyordu. Bu yüzden:
          1. Kendi başlattığımız subprocess canlıysa → kesin bizimki.
          2. Değilse → 8080'de gerçekten MCP server mı var, /health (200) ile kimlik doğrula.
        Sonuç 2sn cache'lenir (status endpoint sık polling yapıyor)."""
        if self.process and self.process.poll() is None:
            return True
        import time
        now = time.monotonic()
        if now - self._health_cache_ts < 2.0:
            return self._health_cache_val
        self._health_cache_val = self._probe_mcp_health_sync()
        self._health_cache_ts = now
        return self._health_cache_val

    def _probe_mcp_health_sync(self) -> bool:
        """8080 açık VE gerçekten MCP server mı (/health 200) — senkron, kısa timeout."""
        import socket
        try:
            with socket.create_connection(("127.0.0.1", self.mcp_port), timeout=0.3):
                pass
        except OSError:
            return False  # port hiç dinlenmiyor
        import urllib.request
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{self.mcp_port}/health", timeout=0.6
            ) as r:
                return r.status == 200
        except Exception:
            return False  # port dolu ama MCP server değil (alakasız servis)

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
        """uvx binary'sini bulur (gömülü > PATH > yaygın kurulum dizinleri)."""
        import shutil, sys
        # Paketlenmiş app: uv installer'a gömülü (resources/uv/). Kullanıcının PC'sinde
        # uv kurulu olmasa da MCP çalışsın diye önce burayı dene.
        bundled = os.path.join(
            self.project_root, "uv", "uvx.exe" if sys.platform == "win32" else "uvx"
        )
        if os.path.isfile(bundled):
            return bundled
        found = shutil.which("uvx")
        if found:
            return found
        home = os.path.expanduser("~")
        if sys.platform == "win32":
            candidates = [
                os.path.join(home, ".local", "bin", "uvx.exe"),
                os.path.join(os.environ.get("APPDATA", ""), "uv", "bin", "uvx.exe"),
                "uvx",
            ]
        else:
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

        self._ensure_writable_resources()  # frozen: Server'ı yazılabilir dizine taşı
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

        # Log yazılabilir kullanıcı dizinine — project_root paketlenmiş app'te
        # Program Files'ı gösterebilir (yazma korumalı → PermissionError → start_server
        # patlıyordu). DB/app_data ile aynı kök.
        log_dir = os.path.join(os.path.expanduser("~"), ".unity_architect_ai")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "unity_mcp_server.log")
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
            import signal, sys
            try:
                if sys.platform == "win32":
                    # Windows: netstat ile LISTENING port sahibini bul, taskkill /T ile öldür.
                    result = subprocess.run(
                        ["netstat", "-ano", "-p", "TCP"],
                        capture_output=True, text=True
                    )
                    pids = set()
                    for line in result.stdout.splitlines():
                        parts = line.split()
                        if (len(parts) >= 5 and parts[3] == "LISTENING"
                                and parts[1].endswith(f":{self.mcp_port}")):
                            pids.add(parts[4])
                    for pid in pids:
                        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"],
                                       capture_output=True)
                    if pids:
                        logger.info(f"[UnityMCP] Port {self.mcp_port} LISTEN temizlendi (PID'ler: {sorted(pids)})")
                else:
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
        self._ensure_writable_resources()  # frozen: MCPForUnity'yi yazılabilir dizine taşı
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

        # Unity MCP eklentisi sistem PATH'inde uv/uvx arıyor; kullanıcının PC'sinde uv
        # kurulu olmasa da bizim gömülü uvx'imizi kullansın diye eklentinin uvx yol
        # override'ını (EditorPrefs "MCPForUnity.UvxPath") set ediyoruz. C# string için
        # ileri eğik çizgi kullanılır (kaçış gerektirmez; .NET Windows'ta da kabul eder).
        uvx_path = self._get_uvx()
        uvx_override = ""
        if os.path.isabs(uvx_path) and os.path.isfile(uvx_path):
            uvx_cs = uvx_path.replace("\\", "/")
            uvx_override = f'            EditorPrefs.SetString("MCPForUnity.UvxPath", "{uvx_cs}");\n'

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
{uvx_override}        }}
    }}
}}
#endif
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)
        logger.info(f"[UnityMCP] Auto-connect scripti yazıldı (auto_start={auto_start}): {script_path}")


# Global singleton
unity_mcp_manager = UnityMCPManager()
