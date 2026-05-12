import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# .env'yi diğer modüller import edilmeden önce yükle
load_dotenv(Path(__file__).parent.parent / ".env")

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import DatabaseManager
from knowledge import KBEngine
from routes import (
    create_analysis_router,
    create_auth_router,
    create_config_router,
    create_conversation_router,
    create_workspace_router,
    create_lint_router,
    create_mcp_router,
)


logging.basicConfig(level=logging.INFO)
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


db_path = _resolve_db_path()
app = FastAPI(title="Unity Architect AI")
db = DatabaseManager(db_path=db_path)
kb = KBEngine()
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
app.include_router(create_conversation_router(db, kb, PROGRESS_STORE))
app.include_router(create_mcp_router())


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "unity-architect-ai"}


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
