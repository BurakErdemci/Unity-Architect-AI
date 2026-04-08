import asyncio
import json
import logging
import urllib.request

from fastapi import APIRouter, Header, HTTPException

from auth_utils import get_current_user, require_user
from schemas import AIConfigRequest, APIKeySaveRequest


logger = logging.getLogger(__name__)


def create_config_router(db):
    router = APIRouter()

    @router.post("/save-ai-config")
    async def save_config(req: AIConfigRequest, x_session_token: str = Header(alias="X-Session-Token")):
        user_id, _ = require_user(db, x_session_token, req.user_id)
        if req.api_key and req.provider_type not in ("ollama", "kb"):
            db.save_api_key(user_id, req.provider_type, req.api_key)
        db.save_ai_config(user_id, req.provider_type, req.model_name, "", req.use_multi_agent, req.force_claude_coder)
        return {"status": "success"}

    @router.get("/get-ai-config/{user_id}")
    async def get_config(user_id: int, x_session_token: str = Header(alias="X-Session-Token")):
        require_user(db, x_session_token, user_id)
        provider_type, model_name, _old_key, use_multi_agent, force_claude_coder = db.get_ai_config(user_id)
        has_key = False
        if provider_type not in ("ollama", "kb"):
            has_key = bool(db.get_api_key(user_id, provider_type))
        return {
            "provider_type": provider_type,
            "model_name": model_name,
            "use_multi_agent": use_multi_agent,
            "force_claude_coder": force_claude_coder,
            "has_key": has_key,
        }

    @router.get("/api-keys/{user_id}")
    async def get_api_keys(user_id: int, x_session_token: str = Header(alias="X-Session-Token")):
        require_user(db, x_session_token, user_id)
        keys = db.get_all_api_keys(user_id)
        masked = {}
        for provider, key in keys.items():
            if len(key) > 8:
                masked[provider] = f"{'•' * (len(key) - 4)}{key[-4:]}"
            else:
                masked[provider] = "••••••••"
        return {"keys": masked, "providers_with_keys": list(keys.keys())}

    @router.post("/api-keys/save")
    async def save_api_key(req: APIKeySaveRequest, x_session_token: str = Header(alias="X-Session-Token")):
        user_id, _ = get_current_user(db, x_session_token)
        if not req.provider_type:
            raise HTTPException(400, "provider_type gerekli.")
        if not req.api_key:
            raise HTTPException(400, "API key boş olamaz.")
        db.save_api_key(user_id, req.provider_type, req.api_key)
        return {"status": "success", "message": f"{req.provider_type} API key kaydedildi."}

    @router.delete("/api-keys/{user_id}/{provider_type}")
    async def delete_api_key(user_id: int, provider_type: str, x_session_token: str = Header(alias="X-Session-Token")):
        require_user(db, x_session_token, user_id)
        db.delete_api_key(user_id, provider_type)
        return {"status": "success"}

    @router.get("/available-models")
    async def get_available_models():
        models = {
            "local": [],
            "cloud": [
                {"id": "claude-sonnet-4-6", "name": "Claude 4.6 Sonnet", "provider": "anthropic"},
                {"id": "claude-opus-4-6", "name": "Claude 4.6 Opus", "provider": "anthropic"},
                {"id": "claude-haiku-4-6", "name": "Claude 4.6 Haiku", "provider": "anthropic"},
                {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B (Groq)", "provider": "groq"},
                {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "provider": "google"},
                {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "provider": "google"},
                {"id": "gpt-5.4-mini", "name": "GPT-5.4 Mini", "provider": "openai"},
                {"id": "gpt-5.4", "name": "GPT-5.4", "provider": "openai"},
                {"id": "gpt-5.4-nano", "name": "GPT-5.4 Nano", "provider": "openai"},
                {"id": "deepseek-chat", "name": "DeepSeek V3", "provider": "deepseek"},
                {"id": "openai/gpt-5.4-mini", "name": "GPT-5.4 Mini (OpenRouter)", "provider": "openrouter"},
                {"id": "openai/gpt-5.4", "name": "GPT-5.4 (OpenRouter)", "provider": "openrouter"},
                {"id": "openai/gpt-5.4-nano", "name": "GPT-5.4 Nano (OpenRouter)", "provider": "openrouter"},
                {"id": "moonshotai/kimi-k2.5", "name": "Kimi K2.5 (Moonshot)", "provider": "openrouter"},
            ],
        }

        try:
            def fetch_ollama():
                req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
                with urllib.request.urlopen(req, timeout=3) as response:
                    return json.loads(response.read())

            ollama_data = await asyncio.to_thread(fetch_ollama)
            for model in ollama_data.get("models", []):
                model_name = model.get("name", "")
                if model_name:
                    models["local"].append(
                        {
                            "id": model_name,
                            "name": model_name.split(":")[0].title() + " (Local)",
                            "provider": "ollama",
                        }
                    )
        except Exception as exc:
            logger.warning(f"Ollama list fetch failed: {exc}")

        return models

    return router
