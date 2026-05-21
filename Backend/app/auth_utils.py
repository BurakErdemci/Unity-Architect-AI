import os
from pathlib import Path, PurePath
from typing import Any

from fastapi import HTTPException

_LOCAL_USER = (1, "local", "local@localhost", None, None)


def _check_token(token) -> None:
    """LOCAL_APP_TOKEN her çağrıda env'den okunur (import-time değil — test güvenliği).
    Token set değilse (dev mode) atlanır."""
    app_token = os.environ.get("LOCAL_APP_TOKEN", "")
    if app_token and token != app_token:
        raise HTTPException(status_code=401, detail="Geçersiz uygulama token'ı")


def require_user(db: Any, token: str, expected_user_id: int = None) -> tuple[int, str]:
    """Local mode: her zaman user_id=1 döner. expected_user_id ignore edilir."""
    _check_token(token)
    return (1, "local")


def get_current_user(db: Any, token: str) -> tuple[int, str, str, None, None]:
    _check_token(token)
    return _LOCAL_USER


# Local mode: tüm kayıtlar user_id=1'e aittir, gerçek ownership kontrolü yok.
def require_conversation_owner(db: Any, token: str, conv_id: int) -> tuple[int, int]:
    _check_token(token)
    return (1, 1)


def require_analysis_owner(db: Any, token: str, item_id: int) -> tuple[int, int]:
    _check_token(token)
    return (1, 1)


def is_path_within_workspace(file_path: str, workspace_path: str) -> bool:
    try:
        resolved_file = Path(file_path).resolve(strict=False)
        resolved_workspace = Path(workspace_path).resolve(strict=False)
        return resolved_workspace == resolved_file or resolved_workspace in resolved_file.parents
    except Exception:
        return False


def is_allowed_unity_script_path(file_path: str, workspace_path: str) -> bool:
    if not is_path_within_workspace(file_path, workspace_path):
        return False

    resolved_file = Path(file_path).resolve(strict=False)
    resolved_workspace = Path(workspace_path).resolve(strict=False)
    try:
        rel_parts = resolved_file.relative_to(resolved_workspace).parts
    except ValueError:
        return False

    if len(rel_parts) < 3:
        return False
    if rel_parts[0] != "Assets" or rel_parts[1] != "Scripts":
        return False

    return PurePath(file_path).suffix.lower() == ".cs"
