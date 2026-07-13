import asyncio
import json
import logging
import os
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
        # 'CLI_SESSION' abonelik modunun placeholder'ıdır, GERÇEK key değildir.
        # Frontend state'inde bayat kalıp bulut modele geçişte buraya sızıyor ve
        # kullanıcının gerçek API key'inin ÜZERİNE yazıyordu (nvidia 401 bug'ı,
        # 2026-07-13 canlı yakalandı) → asla key olarak kaydetme.
        if req.api_key and req.api_key != "CLI_SESSION" and req.provider_type not in ("ollama", "subscription"):
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
                # (kredi kartsız, ~40 RPM; ID'ler /v1/models'ten CANLI doğrulandı 2026-07-13)
                {"id": "nvidia/nemotron-3-ultra-550b-a55b",            "name": "Nemotron 3 Ultra 550B",  "provider": "nvidia"},
                {"id": "nvidia/nemotron-3-super-120b-a12b",            "name": "Nemotron 3 Super 120B",  "provider": "nvidia"},
                {"id": "qwen/qwen3.5-397b-a17b",                       "name": "Qwen 3.5 397B",          "provider": "nvidia"},
                {"id": "mistralai/mistral-large-3-675b-instruct-2512", "name": "Mistral Large 3 675B",   "provider": "nvidia"},
                {"id": "minimaxai/minimax-m3",                         "name": "MiniMax M3",             "provider": "nvidia"},
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

    # Copilot'un programatik model listeleme komutu yok → statik liste (dinamik
    # endpoint'ten servis edilir ki plan-caps disabled bayrakları eklenebilsin).
    _COPILOT_MODELS = [
        {"id": "copilot-auto",                   "name": "Copilot Auto (Önerilen)", "provider": "subscription"},
        {"id": "copilot-claude-sonnet-5",        "name": "Claude Sonnet 5",         "provider": "subscription"},
        {"id": "copilot-claude-fable-5",         "name": "Claude Fable 5",          "provider": "subscription"},
        {"id": "copilot-claude-opus-4.8",        "name": "Claude Opus 4.8",         "provider": "subscription"},
        {"id": "copilot-claude-haiku-4.5",       "name": "Claude Haiku 4.5",        "provider": "subscription"},
        {"id": "copilot-gpt-5.6-sol",            "name": "GPT-5.6 Sol",             "provider": "subscription"},
        {"id": "copilot-gpt-5.6-luna",           "name": "GPT-5.6 Luna",            "provider": "subscription"},
        {"id": "copilot-gpt-5.5",                "name": "GPT-5.5",                 "provider": "subscription"},
        {"id": "copilot-gpt-5.4-mini",           "name": "GPT-5.4 Mini",            "provider": "subscription"},
        {"id": "copilot-gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro",          "provider": "subscription"},
    ]

    # Codex modelleri: statik liste (plan-bazlı blocklist bayrakları eklenerek servis edilir)
    _CODEX_MODELS = [
        {"id": "gpt-5.6-terra", "name": "GPT-5.6 Terra",  "provider": "subscription"},
        {"id": "gpt-5.6-sol",   "name": "GPT-5.6 Sol",    "provider": "subscription"},
        {"id": "gpt-5.6-luna",  "name": "GPT-5.6 Luna",   "provider": "subscription"},
        {"id": "gpt-5.5",       "name": "GPT-5.5",        "provider": "subscription"},
        {"id": "gpt-5.4",       "name": "GPT-5.4",        "provider": "subscription"},
        {"id": "gpt-5.4-mini",  "name": "GPT-5.4 Mini",   "provider": "subscription"},
    ]

    def _apply_plan_caps(cli: str, models: list) -> list:
        """Plan kısıtlarını işaretle: (a) adlı-modeller-kapalı (cursor/copilot),
        (b) model-bazlı blocklist (codex: 'not supported with ChatGPT account')."""
        from providers.oneshot_cli import get_named_models_cap, get_blocked_models
        if get_named_models_cap(cli) is False:
            for m in models:
                if m["id"] not in (f"{cli}-auto",):
                    m["disabled"] = True
                    m["disabled_reason"] = "plan"
        blocked = get_blocked_models(cli)
        if blocked:
            for m in models:
                if m["id"] in blocked:
                    m["disabled"] = True
                    m["disabled_reason"] = "plan"
        return models

    @router.get("/cli-models/{cli}")
    async def cli_models(cli: str, x_session_token: str = Header(alias="X-Session-Token", default="")):
        """Cursor/OpenCode: canlı model listesi; Copilot/Codex: statik liste.
        Plan desteklemeyen modeller disabled=true bayrağıyla döner. 5 dk cache."""
        import time
        from providers.oneshot_cli import resolve_cli_cmd, get_named_models_cap, probe_named_models

        if cli not in ("cursor", "opencode", "copilot", "codex"):
            raise HTTPException(404, "Desteklenen: cursor, opencode, copilot, codex")

        import copy as _copy
        cached = _cli_models_cache.get(cli)
        if cached and time.time() - cached[0] < _CLI_MODELS_TTL:
            # Bayraklar cache'e YAZILMAZ — plan bilgisi turda değişebilir (canlı
            # öğrenme) → her istekte taze uygulanır.
            return {"models": _apply_plan_caps(cli, _copy.deepcopy(cached[1])), "installed": True}

        import shutil as _shutil
        base = resolve_cli_cmd(cli) if cli != "codex" else (["codex"] if _shutil.which("codex") else None)
        if not base:
            return {"models": [], "installed": False}

        if cli == "copilot":
            import copy
            models = copy.deepcopy(_COPILOT_MODELS)
        elif cli == "codex":
            import copy
            models = copy.deepcopy(_CODEX_MODELS)
        else:
            try:
                raw = await _run_cli_capture([*base, "models"])
                models = _parse_cursor_models(raw) if cli == "cursor" else _parse_opencode_models(raw)
            except Exception as exc:
                logger.warning(f"cli-models({cli}) alınamadı: {exc}")
                models = []

        # Plan yeteneği bilinmiyorsa TEK SEFERLİK ucuz probe (sonuç haftalık cache'li
        # dosyada). İlk açılışta grup birkaç sn "yükleniyor" gösterir, sonrası anlık.
        if cli in ("cursor", "copilot") and get_named_models_cap(cli) is None:
            await probe_named_models(cli)

        if models:
            _cli_models_cache[cli] = (time.time(), _copy.deepcopy(models))
        return {"models": _apply_plan_caps(cli, models), "installed": True}

    # ── CLI doktoru: kurulu mu + giriş yapılmış mı ──────────────────
    _doctor_cache: dict = {}

    @router.get("/cli-doctor")
    async def cli_doctor(refresh: bool = False, x_session_token: str = Header(alias="X-Session-Token", default="")):
        import time
        import shutil
        from providers.oneshot_cli import cli_installed, resolve_cli_cmd
        from providers.agy_provider import AgyProvider

        if not refresh and _doctor_cache.get("t", 0) > time.time() - 60:
            return _doctor_cache["data"]
        if refresh:
            # Kullanıcı yenilemesi = "durumu baştan öğren": plan kısıtları da
            # sıfırlanır (plan yükseltince kilitli modeller anında açılabilsin;
            # kısıt sürüyorsa probe/ilk hata yeniden öğrenir).
            from providers.oneshot_cli import clear_plan_caps
            clear_plan_caps()
            _cli_models_cache.clear()

        async def cursor_login() -> bool | None:
            base = resolve_cli_cmd("cursor")
            if not base:
                return None
            out = await _run_cli_capture([*base, "status"], timeout=10)
            if "logged in" in out.lower():
                return True
            return False if out.strip() else None

        def copilot_login() -> bool | None:
            # Login durumu config dosyasında — spawn'sız, anlık.
            import json as _json
            try:
                p = os.path.expanduser(os.path.join("~", ".copilot", "config.json"))
                with open(p, "r", encoding="utf-8") as f:
                    txt = "\n".join(l for l in f.read().splitlines() if not l.strip().startswith("//"))
                return bool((_json.loads(txt) or {}).get("lastLoggedInUser"))
            except Exception:
                return None

        agy_ok = AgyProvider._agy_binary() != "agy" or bool(shutil.which("agy"))
        data = {
            "claude":   {"installed": bool(shutil.which("claude")),  "loggedIn": None},
            "codex":    {"installed": bool(shutil.which("codex")),   "loggedIn": None},
            "agy":      {"installed": agy_ok,                        "loggedIn": None},
            "cursor":   {"installed": cli_installed("cursor"),       "loggedIn": None},
            "copilot":  {"installed": cli_installed("copilot"),      "loggedIn": None},
            "opencode": {"installed": cli_installed("opencode"),     "loggedIn": True},  # auth opsiyonel (ücretsiz modeller)
        }
        if data["cursor"]["installed"]:
            try:
                data["cursor"]["loggedIn"] = await cursor_login()
            except Exception:
                pass
        if data["copilot"]["installed"]:
            data["copilot"]["loggedIn"] = copilot_login()
        if not data["opencode"]["installed"]:
            data["opencode"]["loggedIn"] = None

        _doctor_cache["t"] = time.time()
        _doctor_cache["data"] = data
        return data

    # ── Tek tık kurulum / giriş: kullanıcının GÖREBİLECEĞİ bir terminal
    #    penceresi açar (kurulum çıktısı + tarayıcı login akışı orada yaşar). ──
    _INSTALL_CMDS = {
        "cursor":   ("irm 'https://cursor.com/install?win32=true' | iex", False),
        "copilot":  ("npm install -g @github/copilot", True),
        "opencode": ("npm install -g opencode-ai", True),
        "claude":   ("npm install -g @anthropic-ai/claude-code", True),
        "codex":    ("npm install -g @openai/codex", True),
        # DİKKAT: npm'deki 'agy'/'antigravity-cli' paketleri Google'ın DEĞİL
        # (squatter) — agy yalnız resmi installer'la kurulur (LOCALAPPDATA\agy\bin).
        "agy":      ("irm 'https://antigravity.google/cli/install.ps1' | iex", False),
    }
    _LOGIN_CMDS = {
        "cursor":   "agent login",
        "copilot":  "copilot login",
        "codex":    "codex login",
        "opencode": "opencode auth login",
        "claude":   "claude",   # claude login akışı interaktif oturum içinde (/login)
        "agy":      "agy",      # login subcommand'ı yok — ilk interaktif açılış Google girişini başlatır
    }

    def _open_visible_terminal(ps_command: str) -> None:
        import subprocess as sp
        import sys as _sys
        if _sys.platform != "win32":
            raise HTTPException(501, "Şimdilik yalnız Windows'ta destekleniyor.")
        CREATE_NEW_CONSOLE = 0x00000010
        sp.Popen(["powershell", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", ps_command],
                 creationflags=CREATE_NEW_CONSOLE)

    @router.post("/cli-install/{cli}")
    async def cli_install(cli: str, x_session_token: str = Header(alias="X-Session-Token", default="")):
        import shutil
        entry = _INSTALL_CMDS.get(cli)
        if not entry:
            raise HTTPException(404, f"'{cli}' için otomatik kurulum desteklenmiyor.")
        cmd, needs_npm = entry
        if needs_npm and not shutil.which("npm"):
            raise HTTPException(412, "Bu CLI'ın kurulumu için Node.js gerekiyor. Önce nodejs.org'dan Node.js kurun (npm ile birlikte gelir).")
        _open_visible_terminal(
            f"Write-Host '=== {cli} kurulumu basliyor ===' -ForegroundColor Cyan; {cmd}; "
            f"Write-Host ''; Write-Host '=== Bitti. Bu pencereyi kapatip uygulamada Yenile''ye basabilirsiniz. ===' -ForegroundColor Green")
        _doctor_cache.clear()
        return {"status": "started", "message": "Kurulum penceresi açıldı."}

    @router.post("/cli-login/{cli}")
    async def cli_login(cli: str, x_session_token: str = Header(alias="X-Session-Token", default="")):
        cmd = _LOGIN_CMDS.get(cli)
        if not cmd:
            raise HTTPException(404, f"'{cli}' için giriş akışı desteklenmiyor.")
        _open_visible_terminal(
            f"Write-Host '=== {cli} girisi: acilan tarayicida hesabinizla giris yapin ===' -ForegroundColor Cyan; {cmd}")
        _doctor_cache.clear()
        return {"status": "started", "message": "Giriş penceresi açıldı."}

    return router
