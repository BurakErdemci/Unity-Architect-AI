import logging
import os
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


from collections import deque

# In-memory log buffer — son 200 satır tutulur, /logs endpoint'i okur
_LOG_BUFFER: deque = deque(maxlen=200)

class _BufferHandler(logging.Handler):
    """Her log kaydını _LOG_BUFFER'a yazar."""
    _SUPPRESS = ("/mcp/unity/status", "/health", "GET /mcp-pending")
    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        if any(s in msg for s in self._SUPPRESS):
            return
        _LOG_BUFFER.append({
            "ts":      record.created,
            "level":   record.levelname,
            "logger":  record.name,
            "message": msg,
        })

_buf_handler = _BufferHandler()
_buf_handler.setLevel(logging.INFO)
_buf_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"))

# Root logger seviyesini explicit INFO yap — basicConfig() handler zaten varsa no-op olur
logging.basicConfig(level=logging.INFO)
logging.root.setLevel(logging.INFO)
logging.root.addHandler(_buf_handler)

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


@app.get("/logs")
def get_logs(since: float = 0):
    """Son backend loglarını döner. since: Unix timestamp — sadece sonrasını getir."""
    entries = [e for e in _LOG_BUFFER if e["ts"] > since]
    return {"logs": entries}


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    # MCP server subprocess'leri bu URL'yi kullanır
    os.environ["ANTIGRAVITY_URL"] = f"http://{host}:{port}"
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False
    )
