from pathlib import Path, PurePath
from typing import Any, Optional

from fastapi import Header, HTTPException, status


def session_token_from_header(x_session_token: Optional[str] = Header(default=None)) -> str:
    if not x_session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum bulunamadı.")
    return x_session_token


def get_current_user(db: Any, token: str) -> tuple[int, str]:
    user = db.get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum geçersiz.")
    return user


def require_user(db: Any, token: str, expected_user_id: Optional[int] = None) -> tuple[int, str]:
    user_id, username = get_current_user(db, token)
    if expected_user_id is not None and user_id != expected_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu kaynağa erişim izniniz yok.")
    return user_id, username


def require_conversation_owner(db: Any, token: str, conv_id: int) -> tuple[int, str]:
    user_id, username = get_current_user(db, token)
    owner_id = db.get_conversation_owner(conv_id)
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sohbet bulunamadı.")
    if owner_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu sohbete erişim izniniz yok.")
    return user_id, username


def require_analysis_owner(db: Any, token: str, item_id: int) -> tuple[int, str]:
    user_id, username = get_current_user(db, token)
    owner_id = db.get_analysis_owner(item_id)
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kayıt bulunamadı.")
    if owner_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu kayda erişim izniniz yok.")
    return user_id, username


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
