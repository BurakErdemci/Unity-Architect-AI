from fastapi import APIRouter, Header, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from database import DatabaseManager
from linter import lint_csharp
from auth_utils import _check_token
import logging

logger = logging.getLogger("Linter")
router = APIRouter()

class LintRequest(BaseModel):
    code: str
    filename: str
    full_project: bool = False

class LintError(BaseModel):
    file: Optional[str] = None
    line: int
    column: int
    endColumn: Optional[int] = None
    message: str
    severity: str  # 'error' or 'warning'

class LintResponse(BaseModel):
    errors: List[LintError]

def create_lint_router(db: DatabaseManager):
    @router.post("/lint", response_model=LintResponse)
    async def lint_code(request: LintRequest, x_session_token: str = Header(alias="X-Session-Token", default="")):
        _check_token(x_session_token)
        user_id = 1

        print(f"--- LINTER RUNNING FOR: {request.filename} (full_project: {request.full_project}) ---", flush=True)
        logger.info(f"--- LINTER RUNNING FOR: {request.filename} (full_project: {request.full_project}) ---")

        # 1. Try Local Compiler Linting (Zero Cost, High Accuracy)
        workspace_path = db.get_last_workspace(user_id)
        print(f"Resolved workspace path from DB: {workspace_path}", flush=True)
        logger.info(f"Resolved workspace path from DB: {workspace_path}")
        
        if workspace_path:
            try:
                local_errors = lint_csharp(request.code, workspace_path, request.filename, request.full_project)
                print(f"C# Roslyn (csc) compiler raw output errors count: {len(local_errors)}", flush=True)
                logger.info(f"C# Roslyn (csc) compiler raw output errors count: {len(local_errors)}")
                for i, err in enumerate(local_errors, 1):
                    err_msg = f"  [{i}] Line {err.get('line')}, Col {err.get('column')} | Message: '{err.get('message')}' | Severity: {err.get('severity')}"
                    print(err_msg, flush=True)
                    logger.info(err_msg)
                
                if local_errors:
                    return LintResponse(errors=[LintError(**e) for e in local_errors])
                else:
                    print("C# Roslyn (csc) compiler compiled with 0 errors.", flush=True)
                    logger.info("C# Roslyn (csc) compiler compiled with 0 errors.")
            except Exception as e:
                logger.error(f"Local Roslyn csc linting failed: {e}", exc_info=True)

        return LintResponse(errors=[])

    return router
