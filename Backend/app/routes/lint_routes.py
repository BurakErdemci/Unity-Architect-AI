from fastapi import APIRouter, Header, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from database import DatabaseManager
from ai_providers import AIProviderManager
from linter import lint_csharp
import json
import re
import logging
import asyncio

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
    async def lint_code(request: LintRequest, x_session_token: Optional[str] = Header(None)):
        if not x_session_token:
            raise HTTPException(status_code=401, detail="Session token missing")
        
        user = db.get_user_by_session(x_session_token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid session")
        
        print(f"--- LINTER RUNNING FOR: {request.filename} (full_project: {request.full_project}) ---", flush=True)
        logger.info(f"--- LINTER RUNNING FOR: {request.filename} (full_project: {request.full_project}) ---")
        
        # 1. Try Local Compiler Linting (Zero Cost, High Accuracy)
        workspace_path = db.get_last_workspace(user[0])
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

        # 2. Fallback to AI (Smart Logic Check)
        config = db.get_ai_config(user[0])
        if not config:
            logger.info("AI fallback skipped (no AI config defined). Returning 0 errors.")
            return LintResponse(errors=[])
        
        # Use Gemini Flash for speed
        lint_config = {
            "provider_type": config[0],
            "model_name": "gemini-2.0-flash" if config[0] == "google" else config[1],
            "api_key": config[2]
        }
        
        logger.info(f"Falling back to AI Linter using provider: {lint_config['provider_type']} ({lint_config['model_name']})")
        try:
            provider = AIProviderManager.get_provider(lint_config)
            
            prompt = f"""
            Analyze the following C# code for Unity. Detect syntax errors.
            Return ONLY a JSON object: {{"errors": [{{"line": 10, "column": 5, "message": "msg", "severity": "error"}}]}}
            
            FILENAME: {request.filename}
            CODE:
            {request.code}
            """
            
            raw_response = provider.analyze_code(prompt, max_tokens=1024)
            
            # Resolve if response is an async generator or coroutine
            if hasattr(raw_response, "__anext__"):
                response_text = ""
                async for event in raw_response:
                    if isinstance(event, dict) and event.get("type") == "final":
                        response_text = event.get("text", "")
            elif hasattr(raw_response, "__await__") or asyncio.iscoroutine(raw_response):
                response_text = await raw_response
            else:
                response_text = raw_response
                
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                ai_errors = data.get("errors", [])
                logger.info(f"AI Linter returned {len(ai_errors)} errors.")
                for i, err in enumerate(ai_errors, 1):
                    logger.info(f"  [AI {i}] Line {err.get('line')}, Col {err.get('column')} | Message: '{err.get('message')}' | Severity: {err.get('severity')}")
                return LintResponse(errors=[LintError(**e) for e in ai_errors])
            
            logger.info("AI Linter returned empty/invalid response. Returning 0 errors.")
            return LintResponse(errors=[])
            
        except Exception as exc:
            logger.error(f"AI Linter failed: {exc}", exc_info=True)
            return LintResponse(errors=[])

    return router
