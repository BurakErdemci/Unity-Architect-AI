from fastapi import APIRouter, Header, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from database import DatabaseManager
from ai_providers import AIProviderManager
from linter import lint_csharp
import json
import re

router = APIRouter()

class LintRequest(BaseModel):
    code: str
    filename: str

class LintError(BaseModel):
    line: int
    column: int
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
        
        # 1. Try Local Compiler Linting (Zero Cost, High Accuracy)
        workspace_path = db.get_last_workspace(user[0])
        if workspace_path:
            try:
                local_errors = lint_csharp(request.code, workspace_path, request.filename)
                if local_errors:
                    return LintResponse(errors=[LintError(**e) for e in local_errors])
            except Exception as e:
                print(f"Local lint failed, falling back to AI: {e}")

        # 2. Fallback to AI (Smart Logic Check)
        config = db.get_ai_config(user[0])
        if not config:
            return LintResponse(errors=[])
        
        # Use Gemini Flash for speed
        lint_config = {
            "provider_type": config[0],
            "model_name": "gemini-2.0-flash" if config[0] == "google" else config[1],
            "api_key": config[2]
        }
        
        try:
            provider = AIProviderManager.get_provider(lint_config)
            
            prompt = f"""
            Analyze the following C# code for Unity. Detect syntax errors.
            Return ONLY a JSON object: {{"errors": [{{"line": 10, "column": 5, "message": "msg", "severity": "error"}}]}}
            
            FILENAME: {request.filename}
            CODE:
            {request.code}
            """
            
            response_text = provider.analyze_code(prompt, max_tokens=1024)
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                return LintResponse(errors=[LintError(**e) for e in data.get("errors", [])])
            
            return LintResponse(errors=[])
            
        except Exception:
            return LintResponse(errors=[])

    return router
