import logging
import os
import sys

# ── PATH augmentasyonu (GUI-launched app fix) ─────────────────────────────
# Finder/dmg'den açılan macOS uygulamaları minimal PATH alır (/usr/bin:/bin) —
# kullanıcının CLI'ları (claude/codex → /opt/homebrew/bin, agy → ~/.local/bin)
# bu PATH'te olmadığı için bulunamaz ve spawn patlar (terminalden açınca çalışıyordu).
# Yaygın kurulum dizinlerini PATH'e ekle ki hem shutil.which (cli-availability)
# hem de CLI subprocess spawn'ları çalışsın.
_extra_paths = [
    os.path.expanduser("~/.local/bin"),
    "/opt/homebrew/bin", "/opt/homebrew/sbin",
    "/usr/local/bin", "/usr/local/sbin",
    os.path.expanduser("~/.npm-global/bin"),
    os.path.expanduser("~/bin"),
]
_cur_path = os.environ.get("PATH", "").split(os.pathsep)
os.environ["PATH"] = os.pathsep.join(
    [p for p in _extra_paths if p and p not in _cur_path] + _cur_path
)

# ── Frozen binary subcommand dispatch ─────────────────────────────────────
# Paketlenmiş app'te venv/python yok; launcher scriptleri donmuş 'backend'
# binary'sini alt-komutlarla çağırır:
#   backend mcp-server [--workspace X]  → unity_ai_mcp.server.main (Claude/Codex MCP)
#   backend unityai <save-file|...>     → unityai_cli.main (agy köprüsü)
# FastAPI/uvicorn app'i kurmadan erken dön — bu komutlar HTTP server başlatmaz.
if len(sys.argv) > 1 and sys.argv[1] in ("mcp-server", "unityai"):
    _sub_mode = sys.argv[1]
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    if _sub_mode == "mcp-server":
        from unity_ai_mcp.server import main as _sub_main
        _sub_main()
        sys.exit(0)
    else:  # unityai
        from unityai_cli import main as _sub_main
        sys.exit(_sub_main())

from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

# .env'yi diğer modüller import edilmeden önce yükle
load_dotenv(Path(__file__).parent.parent / ".env")

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import DatabaseManager
from routes import (
    create_analysis_router,
    create_auth_router,
    create_config_router,
    create_conversation_router,
    create_workspace_router,
    create_lint_router,
    create_mcp_router,
)


# Root logger seviyesini explicit INFO yap
logging.basicConfig(level=logging.INFO)
logging.root.setLevel(logging.INFO)

logger = logging.getLogger(__name__)

class _SuppressPollingEndpoints(logging.Filter):
    """Yüksek frekanslı polling endpoint loglarını filtreler (CPU & log spam azaltma)."""
    _SUPPRESS = ("/mcp-pending", "/health")
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(ep in msg for ep in self._SUPPRESS)

logging.getLogger("uvicorn.access").addFilter(_SuppressPollingEndpoints())

# MCP server subprocess'leri için ANTIGRAVITY_URL'yi şimdiden set et
# (PORT env var Electron tarafından dinamik olarak geçilir)
_host = os.environ.get("HOST", "127.0.0.1")
_port = os.environ.get("PORT", "8000")
os.environ["ANTIGRAVITY_URL"] = f"http://{_host}:{_port}"  # Her başlatmada güncelle


def _resolve_db_path() -> str:
    db_path = os.environ.get("DB_PATH")
    if db_path:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return db_path

    home_dir = str(Path.home())
    db_folder = os.path.join(home_dir, ".unity_architect_ai")
    os.makedirs(db_folder, exist_ok=True)
    return os.path.join(db_folder, "unity_master_v3.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Backend başlarken: 8080'de orphan süreç varsa temizle (geçen oturumdan kalmış olabilir)
    try:
        import subprocess, signal, os as _os
        # Sadece LISTEN state'indeki server process'lerini temizle —
        # Unity Editor client olarak bağlıysa onun PID'si de listede çıkar
        # ve öldürmek Unity'yi kapatır.
        result = subprocess.run(
            ["lsof", "-ti", ":8080", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=3
        )
        pids = [p for p in result.stdout.strip().split() if p]
        for pid in pids:
            try:
                _os.kill(int(pid), signal.SIGTERM)
                logger.info(f"[Startup] Orphan MCP süreci temizlendi (PID: {pid})")
            except ProcessLookupError:
                pass
    except Exception as e:
        logger.debug(f"[Startup] Port temizleme atlandı: {e}")

    yield

    # Backend kapanınca Unity MCP subprocess'i de durdur
    try:
        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
        from tools.unity_mcp_tools import unload_unity_tools
        unity_mcp_manager.stop_server()
        unload_unity_tools()
        logger.info("[Shutdown] Unity MCP sunucusu durduruldu.")
    except Exception as e:
        logger.warning(f"[Shutdown] Unity MCP durdurulamadı: {e}")


db_path = _resolve_db_path()
app = FastAPI(title="Unity Architect AI", lifespan=lifespan)
db = DatabaseManager(db_path=db_path)
PROGRESS_STORE = {}

_ALLOWED_ORIGINS = [
    "http://localhost:8888",    # Nextron dev renderer
    "http://127.0.0.1:8888",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "app://.",                  # Electron production scheme
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Session-Token"],
)

app.include_router(create_auth_router(db))
app.include_router(create_config_router(db))
app.include_router(create_analysis_router(db))
app.include_router(create_workspace_router(db))
app.include_router(create_lint_router(db))
app.include_router(create_conversation_router(db, PROGRESS_STORE))
app.include_router(create_mcp_router())


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "unity-architect-ai"}




if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    # MCP server subprocess'leri bu URL'yi kullanır
    os.environ["ANTIGRAVITY_URL"] = f"http://{host}:{port}"
    # app objesini doğrudan ver — string "main:app" frozen binary'de import edilemiyor
    # ("Could not import module 'main'"). reload=False olduğu için obje geçişi sorunsuz.
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False
    )
