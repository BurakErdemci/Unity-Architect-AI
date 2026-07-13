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
        if req.api_key and req.provider_type != "ollama":
            db.save_api_key(user_id, req.provider_type, req.api_key)
        db.save_ai_config(user_id, req.provider_type, req.model_name, "")
        return {"status": "success"}

    @router.get("/get-ai-config/{user_id}")
    async def get_config(user_id: int, x_session_token: str = Header(alias="X-Session-Token")):
        require_user(db, x_session_token, user_id)
        provider_type, model_name, _, _ = db.get_ai_config(user_id)
        has_key = provider_type != "ollama" and bool(db.get_api_key(user_id, provider_type))
        return {
            "provider_type": provider_type,
            "model_name": model_name,
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
                {"id": "claude-sonnet-5",          "name": "Claude Sonnet 5",    "provider": "anthropic", "openrouter_id": "anthropic/claude-sonnet-5"},
                {"id": "claude-fable-5",           "name": "Claude Fable 5",     "provider": "anthropic", "openrouter_id": "anthropic/claude-fable-5"},
                {"id": "claude-opus-4-8",          "name": "Claude 4.8 Opus",    "provider": "anthropic", "openrouter_id": "anthropic/claude-opus-4-8"},
                {"id": "claude-sonnet-4-6",       "name": "Claude 4.6 Sonnet",  "provider": "anthropic", "openrouter_id": "anthropic/claude-sonnet-4-6"},
                {"id": "claude-haiku-4-5",         "name": "Claude 4.5 Haiku",   "provider": "anthropic", "openrouter_id": "anthropic/claude-haiku-4-5"},
                {"id": "llama-3.3-70b-versatile",  "name": "Llama 3.3 70B",      "provider": "groq",      "openrouter_id": "meta-llama/llama-3.3-70b-instruct"},
                {"id": "gemini-3.5-flash",              "name": "Gemini 3.5 Flash",      "provider": "google", "openrouter_id": "google/gemini-3.5-flash"},
                {"id": "gemini-3-flash-preview",        "name": "Gemini 3 Flash",        "provider": "google", "openrouter_id": "google/gemini-3-flash-preview"},
                {"id": "gemini-3.1-flash-lite-preview", "name": "Gemini 3.1 Flash Lite", "provider": "google", "openrouter_id": "google/gemini-3.1-flash-lite-preview"},
                {"id": "gemini-3.1-pro-preview",        "name": "Gemini 3.1 Pro",        "provider": "google", "openrouter_id": "google/gemini-3.1-pro-preview", "paid": True},
                {"id": "gpt-5.6-sol",              "name": "GPT-5.6 Sol",        "provider": "openai",    "openrouter_id": "openai/gpt-5.6-sol"},
                {"id": "gpt-5.6-terra",            "name": "GPT-5.6 Terra",      "provider": "openai",    "openrouter_id": "openai/gpt-5.6-terra"},
                {"id": "gpt-5.6-luna",             "name": "GPT-5.6 Luna",       "provider": "openai",    "openrouter_id": "openai/gpt-5.6-luna"},
                {"id": "gpt-5.5",                  "name": "GPT-5.5",            "provider": "openai",    "openrouter_id": "openai/gpt-5.5"},
                {"id": "gpt-5.5-pro",              "name": "GPT-5.5 Pro",        "provider": "openai",    "openrouter_id": "openai/gpt-5.5-pro"},
                {"id": "gpt-5.4",                  "name": "GPT-5.4",            "provider": "openai",    "openrouter_id": "openai/gpt-5.4"},
                {"id": "gpt-5.4-mini",             "name": "GPT-5.4 Mini",       "provider": "openai",    "openrouter_id": "openai/gpt-5.4-mini"},
                {"id": "deepseek-v4-pro",          "name": "DeepSeek V4 Pro",    "provider": "deepseek",  "openrouter_id": "deepseek/deepseek-v4-pro"},
                {"id": "deepseek-v4-flash",        "name": "DeepSeek V4 Flash",  "provider": "deepseek",  "openrouter_id": "deepseek/deepseek-v4-flash"},
                {"id": "glm-5.2",                  "name": "GLM 5.2",            "provider": "z-ai",      "openrouter_id": "z-ai/glm-5.2"},
                {"id": "kimi-k2.7-code",           "name": "Kimi K2.7 Code",     "provider": "moonshot",  "openrouter_id": "moonshotai/kimi-k2.7-code"},
                {"id": "kimi-k2.6",                "name": "Kimi K2.6",          "provider": "moonshot",  "openrouter_id": "moonshotai/kimi-k2.6"},
                # NVIDIA NIM (build.nvidia.com) — tek nvapi- key ile ÜCRETSİZ havuz
                # (kredi kartsız, ~40 RPM; ID'ler NIM kataloğundan, 2026-07-13)
                {"id": "nvidia/nemotron-3-super-120b-a12b",            "name": "Nemotron 3 Super 120B",  "provider": "nvidia"},
                {"id": "nvidia/llama-3.3-nemotron-super-49b-v1.5",     "name": "Nemotron Super 49B",     "provider": "nvidia"},
                {"id": "qwen/qwen3.5-397b-a17b",                       "name": "Qwen 3.5 397B",          "provider": "nvidia"},
                {"id": "qwen/qwen3-coder-480b-a35b-instruct",          "name": "Qwen3 Coder 480B",       "provider": "nvidia"},
                {"id": "mistralai/mistral-large-3-675b-instruct-2512", "name": "Mistral Large 3 675B",   "provider": "nvidia"},
                {"id": "deepseek-ai/deepseek-v4-pro",                  "name": "DeepSeek V4 Pro (NIM)",  "provider": "nvidia"},
                {"id": "moonshotai/kimi-k2.6",                         "name": "Kimi K2.6 (NIM)",        "provider": "nvidia"},
            ],
            "subscription": [
                {"id": "claude-sonnet-5",      "name": "Claude Sonnet 5 (CLI)",         "provider": "subscription"},
                {"id": "claude-fable-5",       "name": "Claude Fable 5 (CLI)",          "provider": "subscription"},
                {"id": "claude-opus-4-8",      "name": "Claude 4.8 Opus (CLI)",         "provider": "subscription"},
                {"id": "claude-sonnet-4-6",    "name": "Claude 4.6 Sonnet (CLI)",       "provider": "subscription"},
                {"id": "claude-haiku-4-5",     "name": "Claude 4.5 Haiku (CLI)",        "provider": "subscription"},
                {"id": "gpt-5.6-sol",         "name": "Codex (GPT-5.6 Sol)",           "provider": "subscription"},
                {"id": "gpt-5.6-terra",       "name": "Codex (GPT-5.6 Terra)",         "provider": "subscription"},
                {"id": "gpt-5.6-luna",        "name": "Codex (GPT-5.6 Luna)",          "provider": "subscription"},
                {"id": "gpt-5.5",              "name": "Codex (GPT-5.5)",               "provider": "subscription"},
                {"id": "gpt-5.4",              "name": "Codex (GPT-5.4)",               "provider": "subscription"},
                {"id": "gpt-5.4-mini",         "name": "Codex (GPT-5.4 Mini)",          "provider": "subscription"},
                {"id": "gemini-3.5-flash",             "name": "Gemini 3.5 Flash (Önerilen)", "provider": "subscription"},
                {"id": "gemini-3.5-flash-medium",      "name": "Gemini 3.5 Flash (Medium)",   "provider": "subscription"},
                {"id": "gemini-3.1-pro-preview",       "name": "Gemini 3.1 Pro (High)",       "provider": "subscription"},
                {"id": "gemini-3.1-pro-low",           "name": "Gemini 3.1 Pro (Low)",        "provider": "subscription"},
                {"id": "gemini-3-flash-preview",       "name": "Gemini 3 Flash",              "provider": "subscription"},
                {"id": "gemini-3.1-flash-lite-preview","name": "Gemini 3.1 Flash Lite",       "provider": "subscription"},
                {"id": "agy-claude-sonnet-4-6",        "name": "Claude Sonnet 4.6 (Thinking)", "provider": "subscription"},
                {"id": "agy-gpt-oss-120b",             "name": "GPT-OSS 120B (Medium)",       "provider": "subscription"},
                # GitHub Copilot CLI (statik — copilot'un programatik model listesi yok;
                # ID'ler CLI'ın kendi model seçicisinden alındı, 2026-07-13)
                {"id": "copilot-auto",                 "name": "Copilot Auto (Önerilen)",     "provider": "subscription"},
                {"id": "copilot-claude-sonnet-5",      "name": "Claude Sonnet 5",             "provider": "subscription"},
                {"id": "copilot-claude-fable-5",       "name": "Claude Fable 5",              "provider": "subscription"},
                {"id": "copilot-claude-opus-4.8",      "name": "Claude Opus 4.8",             "provider": "subscription"},
                {"id": "copilot-claude-haiku-4.5",     "name": "Claude Haiku 4.5",            "provider": "subscription"},
                {"id": "copilot-gpt-5.6-sol",          "name": "GPT-5.6 Sol",                 "provider": "subscription"},
                {"id": "copilot-gpt-5.6-luna",         "name": "GPT-5.6 Luna",                "provider": "subscription"},
                {"id": "copilot-gpt-5.5",              "name": "GPT-5.5",                     "provider": "subscription"},
                {"id": "copilot-gpt-5.4-mini",         "name": "GPT-5.4 Mini",                "provider": "subscription"},
                {"id": "copilot-gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro",            "provider": "subscription"},
                # Cursor ve OpenCode modelleri DİNAMİK: /cli-models/{cli} endpoint'i
                # kullanıcının hesabına/kurulumuna göre canlı liste döner.
            ]
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

    @router.get("/cli-availability")
    async def cli_availability(x_session_token: str = Header(alias="X-Session-Token", default="")):
        """CLI sağlayıcılarının kullanıcı PC'sinde kurulu olup olmadığını döner.
        Bunlar gömülü DEĞİL — kullanıcının kurmuş olması gerekir.
        Frontend, kurulu olmayan bir CLI modeli seçilince uyarı gösterir."""
        import shutil
        from providers.agy_provider import AgyProvider
        from providers.oneshot_cli import cli_installed

        # _agy_binary() yaygın kurulum yollarına da bakar; "agy" dönerse sadece PATH'e kalmış demektir.
        agy_ok = AgyProvider._agy_binary() != "agy" or bool(shutil.which("agy"))
        return {
            "claude": bool(shutil.which("claude")),
            "codex": bool(shutil.which("codex")),
            "agy": agy_ok,
            "cursor": cli_installed("cursor"),
            "copilot": cli_installed("copilot"),
            "opencode": cli_installed("opencode"),
        }

    # ── Dinamik CLI model listeleri (cursor: hesaba göre; opencode: kuruluma göre) ──
    _cli_models_cache: dict = {}   # cli → (timestamp, models)
    _CLI_MODELS_TTL = 300          # 5 dk — CLI listeleri nadiren değişir

    async def _run_cli_capture(cmd: list, timeout: float = 20.0) -> str:
        """CLI komutunu çalıştırıp stdout'u döner (Windows'ta pencere açmadan)."""
        import subprocess as sp
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=getattr(sp, "CREATE_NO_WINDOW", 0),
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return ""
        return out.decode("utf-8", errors="ignore")

    def _parse_cursor_models(raw: str) -> list:
        """`agent models` çıktısı: 'id - Display Name' satırları.
        '-fast' hız varyantları listeyi 2x şişiriyor → elenir (id'yi bilen
        kullanıcı yine seçebilir; UI listesi derli toplu kalsın)."""
        models = []
        for line in raw.splitlines():
            line = line.strip()
            if " - " not in line or line.lower().startswith("available"):
                continue
            mid, _, name = line.partition(" - ")
            mid = mid.strip()
            name = name.strip()
            if not mid or mid.endswith("-fast"):
                continue
            # "Auto (current, default)" → "Auto"
            name = name.split(" (current")[0].split(" (default")[0].strip()
            models.append({"id": f"cursor-{mid}", "name": name, "provider": "subscription"})
        return models

    def _parse_opencode_models(raw: str) -> list:
        """`opencode models` çıktısı: 'provider/model' satırları. Liste models.dev
        kataloğunun tamamı olabilir (yüzlerce) → yalnızca opencode/* (ücretsiz,
        auth'suz çalışır — canlı doğrulandı) gösterilir; diğer sağlayıcılar için
        kullanıcı zaten bizim API-key provider'larımızı kullanabilir."""
        models = []
        for line in raw.splitlines():
            line = line.strip()
            if "/" not in line or " " in line:
                continue
            if not line.startswith("opencode/"):
                continue
            short = line.split("/", 1)[1]
            pretty = short.replace("-", " ").title()
            if short.endswith("-free"):
                pretty = pretty[:-5].strip() + " (Ücretsiz)"
            models.append({"id": f"opencode:{line}", "name": pretty, "provider": "subscription"})
        return models

    @router.get("/cli-models/{cli}")
    async def cli_models(cli: str, x_session_token: str = Header(alias="X-Session-Token", default="")):
        """Cursor/OpenCode için canlı model listesi (kullanıcının hesabına/kurulumuna
        göre). 5 dk cache'lenir. CLI kurulu değilse boş liste döner."""
        import time
        from providers.oneshot_cli import resolve_cli_cmd

        if cli not in ("cursor", "opencode"):
            raise HTTPException(404, "Desteklenen: cursor, opencode")

        cached = _cli_models_cache.get(cli)
        if cached and time.time() - cached[0] < _CLI_MODELS_TTL:
            return {"models": cached[1]}

        base = resolve_cli_cmd(cli)
        if not base:
            return {"models": [], "installed": False}

        try:
            raw = await _run_cli_capture([*base, "models"])
            models = _parse_cursor_models(raw) if cli == "cursor" else _parse_opencode_models(raw)
        except Exception as exc:
            logger.warning(f"cli-models({cli}) alınamadı: {exc}")
            models = []

        if models:
            _cli_models_cache[cli] = (time.time(), models)
        return {"models": models, "installed": True}

    return router
