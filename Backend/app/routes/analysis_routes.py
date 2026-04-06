import asyncio
import json
import logging
import re

from fastapi import APIRouter, Header, HTTPException, status

from ai_providers import AIProviderManager
from analyzer import UnityAnalyzer
from auth_utils import require_analysis_owner, require_user
from code_detector import CodeDetector
from pipelines.agents.intent_classifier import IntentClassifierAgent
from prompts import PROMPT_GREETING, get_language_instr
from report_engine import ReportEngine
from schemas import AnalysisRequest, RenameRequest, UpdateFileRequest
from validator import ResponseValidator


logger = logging.getLogger(__name__)


def clean_response(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def create_analysis_router(db):
    router = APIRouter()

    @router.post("/analyze")
    async def analyze_code(request: AnalysisRequest, x_session_token: str = Header(alias="X-Session-Token")):
        user_id, _ = require_user(db, x_session_token, request.user_id)
        logger.info(f"Analiz İsteği - User ID: {user_id}")

        is_csharp = CodeDetector.is_csharp(request.code)
        provider_type, model_name, _, _use_multi_agent = db.get_ai_config(user_id)
        api_key = (db.get_api_key(user_id, provider_type) or "") if provider_type not in ("ollama", "kb") else ""

        try:
            provider = AIProviderManager.get_provider(
                {"provider_type": provider_type, "model_name": model_name, "api_key": api_key}
            )
        except ValueError as exc:
            return {"intent": "ERROR", "ai_suggestion": str(exc), "static_results": {"smells": []}}

        classifier = IntentClassifierAgent(provider)
        intent = await classifier.classify_async(request.code)

        if intent == "GREETING" and not is_csharp:
            return {"intent": "GREETING", "ai_suggestion": PROMPT_GREETING, "static_results": {"smells": []}}

        static_results = {"smells": [], "stats": {"total_lines": 0, "class_name": "Analiz"}}
        if is_csharp:
            static_results = UnityAnalyzer(request.code).analyze()

        lang_instr = get_language_instr(request.language)
        if provider_type == "ollama":
            prompt = (
                f"Unity C# kodunu analiz et. {lang_instr}\n"
                f"Kod: {request.code}\n"
                f"Statik bulgular: {json.dumps(static_results['smells'], ensure_ascii=False)}"
            )
            final_suggestion = ""
            clean_res = ""
            for _ in range(2):
                response = await asyncio.to_thread(provider.analyze_code, prompt, max_tokens=8192)
                clean_res = clean_response(response)
                is_valid, _ = ResponseValidator.validate(clean_res)
                if is_valid:
                    final_suggestion = clean_res
                    break
                prompt = "HATALARINI DÜZELT: Kod bloğu (```csharp) eksik!\n" + prompt
            if not final_suggestion:
                final_suggestion = clean_res
        else:
            prompt = f"""
        Sen Senior Unity Mimarsın. {lang_instr}
        Şu Unity kodunu analiz et ve [PERF_001], [PHYS_001], [LOGIC_001] kodlarıyla hataları açıkla.
        Ardından hataların tamamen düzeltildiği TAM bir C# kodu yaz.

        KOD: {request.code}
        STATİK BULGULAR: {static_results['smells']}
        """
            final_suggestion = await asyncio.to_thread(provider.analyze_code, prompt)

        title = static_results.get("stats", {}).get("class_name", "Analiz")
        db.save_analysis(user_id, title, intent, request.code, final_suggestion, static_results["smells"])
        return {"intent": intent, "static_results": static_results, "ai_suggestion": final_suggestion}

    @router.get("/history/{user_id}")
    async def get_history(user_id: int, x_session_token: str = Header(alias="X-Session-Token")):
        require_user(db, x_session_token, user_id)
        rows = db.get_user_history(user_id)
        return [{"id": row[0], "timestamp": row[1], "title": row[2], "intent": row[3]} for row in rows]

    @router.get("/analysis-detail/{item_id}")
    async def get_detail(item_id: int, x_session_token: str = Header(alias="X-Session-Token")):
        require_analysis_owner(db, x_session_token, item_id)
        detail = db.get_analysis_detail(item_id)
        if not detail:
            raise HTTPException(404)
        return detail

    @router.delete("/history/{item_id}")
    async def delete_item(item_id: int, x_session_token: str = Header(alias="X-Session-Token")):
        require_analysis_owner(db, x_session_token, item_id)
        db.delete_analysis(item_id)
        return {"status": "success"}

    @router.put("/history/{item_id}")
    async def rename_item(item_id: int, req: RenameRequest, x_session_token: str = Header(alias="X-Session-Token")):
        require_analysis_owner(db, x_session_token, item_id)
        db.rename_analysis(item_id, req.title)
        return {"status": "success"}

    @router.post("/update-file")
    async def update_file(_req: UpdateFileRequest):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Bu endpoint devre dışı bırakıldı. Güvenli workspace export kullanın.",
        )

    return router
