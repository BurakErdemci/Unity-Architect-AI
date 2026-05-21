import re
import time

# ANSI/VT100 escape code temizleyici — bubbletea TUI çıktısını temizler
_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*\x07)')

def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)
import subprocess
import os
import logging
import ollama
import openai
from google import genai
from google.genai import types as gtypes
from abc import ABC, abstractmethod
import asyncio
from typing import Dict, Any, Optional, Tuple, List, AsyncGenerator

logger = logging.getLogger(__name__)

# (response_text, thinking_text, thinking_duration_ms)
ThinkingResult = Tuple[str, Optional[str], Optional[int]]


class AIProvider(ABC):
    @abstractmethod
    def analyze_code(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None, cwd: Optional[str] = None) -> str:
        pass

    def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None, thinking_level: str = "medium", cwd: Optional[str] = None) -> ThinkingResult:
        """Thinking desteklemeyen provider'lar için fallback — thinking None döner."""
        return self.analyze_code(prompt, max_tokens, images, cwd=cwd), None, None

    def _clean_response(self, text: str):
        if not text: return ""
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return text.strip()


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)

        raw_name = model_name.lower() if model_name else ""
        # Google AI Studio / google-genai SDK - Mayıs 2026 (Minimum desteklenen: v2.0)
        if "3.1-pro" in raw_name:
            self.model_id = "gemini-3.1-pro"
        elif "3.1-flash-lite" in raw_name:
            self.model_id = "gemini-3.1-flash-lite"
        elif "3-flash" in raw_name or "3.0-flash" in raw_name:
            self.model_id = "gemini-3-flash"
        elif "2.5-pro" in raw_name:
            self.model_id = "gemini-2.5-pro"
        elif "2.0-flash" in raw_name:
            self.model_id = "gemini-2.0-flash"
        elif "pro" in raw_name:
            self.model_id = "gemini-3.1-pro"
        else:
            self.model_id = model_name if model_name else "gemini-3.1-pro"

    _THINKING_MODELS = ("gemini-3.1", "gemini-3.0", "gemini-2.5")

    def _supports_thinking(self) -> bool:
        return any(self.model_id.startswith(m) for m in self._THINKING_MODELS)

    def analyze_code(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None) -> str:
        try:
            contents = [prompt]
            if images:
                parts = [gtypes.Part(text=prompt)]
                for img_data in images:
                    if "," in img_data:
                        header, base64_str = img_data.split(",", 1)
                        mime_type = header.split(":")[1].split(";")[0]
                        parts.append(gtypes.Part(inline_data=gtypes.Blob(mime_type=mime_type, data=base64_str)))
                contents = [gtypes.Content(role="user", parts=parts)]

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=gtypes.GenerateContentConfig(max_output_tokens=max_tokens),
            )
            if response and response.text:
                return response.text
            return "AI yanıt üretti ancak içerik boş döndü."
        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                return "SİSTEM MESAJI: Google API ücretsiz kota sınırına ulaşıldı. Lütfen 60 saniye bekleyip tekrar deneyin veya Ollama (Yerel) moduna geçin."
            if "404" in err_str:
                return f"SİSTEM MESAJI: '{self.model_id}' modeli bulunamadı. Ayarlar'dan farklı bir Gemini modeli seçin."
            raise Exception(f"Gemini API Hatası: {err_str}")

    def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None, thinking_level: str = "medium") -> ThinkingResult:
        if not self._supports_thinking():
            return self.analyze_code(prompt, max_tokens, images), None, None

        try:
            start = time.time()
            contents = [prompt]
            if images:
                parts = [gtypes.Part(text=prompt)]
                for img_data in images:
                    if "," in img_data:
                        header, base64_str = img_data.split(",", 1)
                        mime_type = header.split(":")[1].split(";")[0]
                        parts.append(gtypes.Part(inline_data=gtypes.Blob(mime_type=mime_type, data=base64_str)))
                contents = [gtypes.Content(role="user", parts=parts)]

            # Düşünme seviyesine göre bütçe belirle
            budget_map = {"low": 4096, "medium": 16384, "high": 65536}
            budget = budget_map.get(thinking_level, 16384)

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=gtypes.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    thinking_config=gtypes.ThinkingConfig(thinking_budget=budget),
                ),
            )
            duration_ms = int((time.time() - start) * 1000)

            thinking_text = None
            response_text = ""
            for part in response.candidates[0].content.parts:
                if getattr(part, "thought", False):
                    thinking_text = (thinking_text or "") + (part.text or "")
                else:
                    response_text += part.text or ""

            return response_text.strip() or "", thinking_text, duration_ms
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Gemini thinking] Fallback: {e}")
            return self.analyze_code(prompt, max_tokens), None, None


class OllamaProvider(AIProvider):
    def __init__(self, model_name: str = "qwen2.5-coder:7b"):
        self.model_name = model_name if model_name else "qwen2.5-coder:7b"

    def analyze_code(self, prompt: str, max_tokens: int = 4096) -> str:
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{'role': 'user', 'content': prompt}],
                options={'num_predict': max_tokens}
            )
            return self._clean_response(response['message']['content'])
        except Exception as e:
            raise Exception(f"Ollama Hatası: {str(e)}")


class OpenAICompatibleProvider(AIProvider):
    # OpenAI reasoning modelleri (Mayıs 2026 güncel)
    _REASONING_MODELS = ("gpt-5.5", "gpt-5.4", "o3", "o4", "o5")
    # Kimi thinking modelleri
    _KIMI_THINKING_MODELS = ("kimi-k3", "kimi-k2")
    # Kimi model name normalization
    _KIMI_ALIASES = {"kimi-k2.6": "kimi-k2.6", "kimi-k2.5": "kimi-k2.5"}

    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.base_url = base_url

    def _is_openai_reasoning(self) -> bool:
        lower_name = self.model_name.lower()
        return any(m in lower_name for m in self._REASONING_MODELS)

    def _is_kimi(self) -> bool:
        lower_name = self.model_name.lower()
        return "moonshot" in self.base_url or "moonshotai" in lower_name or "kimi-k2" in lower_name

    def analyze_code(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None) -> str:
        try:
            user_content = [{"type": "text", "text": prompt}]
            if images:
                for img_data in images:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": img_data}
                    })

            kwargs = dict(
                model=self.model_name,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=max_tokens,
            )
            # Reasoning ve Kimi modelleri temperature parametresini desteklemiyor
            if not self._is_openai_reasoning() and not self._is_kimi():
                kwargs["temperature"] = 0.3
            response = self.client.chat.completions.create(**kwargs)
            return self._clean_response(response.choices[0].message.content)
        except Exception as e:
            raise Exception(f"API Hatası: {str(e)}")

    def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096) -> ThinkingResult:
        # OpenAI GPT-5.x reasoning
        if self._is_openai_reasoning():
            try:
                start = time.time()
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    reasoning={"effort": "medium"},
                )
                duration_ms = int((time.time() - start) * 1000)
                thinking = getattr(response.choices[0].message, "reasoning_content", None)
                text = self._clean_response(response.choices[0].message.content)
                return text, thinking or None, duration_ms
            except Exception:
                # reasoning parametresi desteklenmiyorsa (örn. bazı OpenRouter proxy'leri) standart call
                try:
                    start = time.time()
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                    )
                    duration_ms = int((time.time() - start) * 1000)
                    text = self._clean_response(response.choices[0].message.content)
                    return text, None, duration_ms
                except Exception:
                    return self.analyze_code(prompt, max_tokens), None, None

        # Kimi K2.x thinking
        if self._is_kimi():
            try:
                start = time.time()
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    extra_body={"thinking": {"enabled": True}},
                )
                duration_ms = int((time.time() - start) * 1000)
                thinking = getattr(response.choices[0].message, "reasoning_content", None)
                text = self._clean_response(response.choices[0].message.content)
                return text, thinking or None, duration_ms
            except Exception:
                # thinking desteklenmiyorsa (K2.6 gibi yeni versiyonlar) standart call
                try:
                    start = time.time()
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                    )
                    duration_ms = int((time.time() - start) * 1000)
                    text = self._clean_response(response.choices[0].message.content)
                    return text, None, duration_ms
                except Exception:
                    return self.analyze_code(prompt, max_tokens), None, None

        return self.analyze_code(prompt, max_tokens), None, None


import anthropic

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)

        raw_name = model_name.lower() if model_name else ""
        if "sonnet-4-6" in raw_name or "sonnet" in raw_name:
            self.model_name = "claude-4-6-sonnet"
        elif "opus-4-7" in raw_name or "opus" in raw_name:
            self.model_name = "claude-4-7-opus"
        elif "haiku-4-5" in raw_name or "haiku" in raw_name:
            self.model_name = "claude-4-5-haiku"
        else:
            self.model_name = "claude-4-6-sonnet"

    def analyze_code(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None) -> str:
        try:
            if max_tokens > 16384:
                return self._stream_response(prompt, max_tokens) # Stream mode doesn't support images yet in our simple implementation

            user_content = [{"type": "text", "text": prompt}]
            if images:
                for img_data in images:
                    if "," in img_data:
                        header, base64_str = img_data.split(",", 1)
                        media_type = header.split(":")[1].split(";")[0]
                        user_content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_str
                            }
                        })

            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": user_content}]
            )
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text
            return self._clean_response(text)
        except Exception as e:
            return f"❌ Anthropic API Hatası: Sistemsel bir ret veya model hatası oluştu. Mesaj: {str(e)}"

    def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None) -> ThinkingResult:
        try:
            start = time.time()
            user_content = [{"type": "text", "text": prompt}]
            if images:
                for img_data in images:
                    if "," in img_data:
                        header, base64_str = img_data.split(",", 1)
                        media_type = header.split(":")[1].split(";")[0]
                        user_content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_str
                            }
                        })

            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=max_tokens + 8000,
                thinking={"type": "enabled", "budget_tokens": 8000},
                messages=[{"role": "user", "content": user_content}]
            )
            duration_ms = int((time.time() - start) * 1000)

            thinking_text = None
            response_text = ""
            for block in response.content:
                if block.type == "thinking":
                    thinking_text = block.thinking
                elif block.type == "text":
                    response_text += block.text

            return self._clean_response(response_text), thinking_text, duration_ms
        except Exception:
            return self.analyze_code(prompt, max_tokens), None, None

    def _stream_response(self, prompt: str, max_tokens: int) -> str:
        try:
            text = ""
            with self.client.messages.stream(
                model=self.model_name,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                for chunk in stream.text_stream:
                    text += chunk
            return self._clean_response(text)
        except Exception as e:
            return f"❌ Anthropic API Hatası: {str(e)}"


class CLIProvider(AIProvider):
    """
    Claude Code ve Codex CLI'larını Antigravity MCP Server üzerinden çalıştırır.

    Tüm onay mantığı MCP server'da — bu sınıf sadece CLI'ı başlatır ve
    stdout'u SSE event'lerine dönüştürür.
    """

    def __init__(self, binary_name: str = "claude"):
        self.binary_name = binary_name

    def _write_mcp_config(self, workspace: str) -> str:
        """
        Claude Code için workspace'e .mcp.json yazar.
        Codex için ~/.codex/config.toml içindeki antigravity MCP kaydını günceller.
        Gemini CLI için MCP kaydını günceller.
        Döndürür: Claude config dosyasının tam yolu.
        """
        import json
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        launcher = os.path.join(backend_dir, "run_mcp_server.sh")
        antigravity_url = os.environ.get("ANTIGRAVITY_URL", "http://localhost:8000")

        # Claude Code: workspace/.mcp.json
        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
        config = {
            "mcpServers": {
                "antigravity": {
                    "command": launcher,
                    "args": ["--workspace", workspace],
                    "env": {"ANTIGRAVITY_URL": antigravity_url}
                }
            }
        }
        # Unity MCP: sadece aktifse ekle, kapalıysa kesinlikle ekleme
        # (Codex/Claude CLI başlarken bağlanamadığı MCP'de crash yapar)
        if unity_mcp_manager.is_running():
            config["mcpServers"]["unityMCP"] = {
                "url": f"http://localhost:{unity_mcp_manager.mcp_port}/mcp"
            }
            logger.info("[CLIProvider] Unity MCP aktif, .mcp.json'a eklendi.")

        config_path = os.path.join(workspace, ".mcp.json")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        if self.binary_name.startswith("gpt-"):
            # Codex: ~/.codex/config.toml içine MCP server ekle/güncelle
            self._register_codex_mcp(launcher, workspace, antigravity_url)
        elif self.binary_name.startswith("gemini"):
            # Gemini CLI: MCP kaydını güncelle
            self._register_gemini_mcp(launcher, workspace, antigravity_url)
        elif self.binary_name.startswith("claude"):
            # Claude Code: user-scope config'e ekle ki -p (headless) mode'da
            # project-level approval prompt'una takılmasın
            self._register_claude_mcp(launcher, workspace, antigravity_url)

        return config_path

    def _register_claude_mcp(self, launcher: str, workspace: str, antigravity_url: str):
        """
        Claude Code'un user-scope config'ine antigravity ve unityMCP server'larını yazar.
        Project-scope .mcp.json -p (headless) modda approval gerektirdiği için kullanılamaz.
        """
        import subprocess as sp

        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager

        # antigravity (stdio)
        try:
            sp.run(["claude", "mcp", "remove", "antigravity", "--scope", "user"],
                   capture_output=True, timeout=5)
            sp.run(
                [
                    "claude", "mcp", "add", "antigravity",
                    "--scope", "user",
                    "-e", f"ANTIGRAVITY_URL={antigravity_url}",
                    "-e", f"WORKSPACE={workspace}",
                    "--", launcher, "--workspace", workspace,
                ],
                capture_output=True, timeout=5, check=True,
            )
            logger.info("[CLIProvider] Claude antigravity MCP kaydedildi (user scope).")
        except Exception as e:
            logger.warning(f"[CLIProvider] Claude antigravity MCP kaydı yapılamadı: {e}")

        # unityMCP (http) — sadece Unity MCP server çalışıyorsa
        try:
            sp.run(["claude", "mcp", "remove", "unityMCP", "--scope", "user"],
                   capture_output=True, timeout=5)
            if unity_mcp_manager.is_running():
                sp.run(
                    [
                        "claude", "mcp", "add", "unityMCP",
                        "--scope", "user",
                        "--transport", "http",
                        f"http://localhost:{unity_mcp_manager.mcp_port}/mcp",
                    ],
                    capture_output=True, timeout=5, check=True,
                )
                logger.info("[CLIProvider] Claude unityMCP kaydedildi (user scope).")
        except Exception as e:
            logger.warning(f"[CLIProvider] Claude unityMCP kaydı yapılamadı: {e}")

    def _register_codex_mcp(self, launcher: str, workspace: str, antigravity_url: str):
        """
        Codex'in ~/.codex/config.toml dosyasına antigravity MCP server'ını yazar.
        Her çağrıda URL güncellenir (backend dinamik port kullanır).
        """
        import subprocess as sp
        try:
            # Önce var olan kaydı sil (URL güncel olmayabilir)
            sp.run(
                ["codex", "mcp", "remove", "antigravity"],
                capture_output=True, timeout=5,
            )
            # Yeni kaydı ekle
            sp.run(
                [
                    "codex", "mcp", "add", "antigravity",
                    "--env", f"ANTIGRAVITY_URL={antigravity_url}",
                    "--env", f"WORKSPACE={workspace}",
                    "--", launcher, "--workspace", workspace,
                ],
                capture_output=True, timeout=5, check=True,
            )
        except Exception as e:
            logger.warning(f"[CLIProvider] Codex MCP kaydı yapılamadı: {e}")

    def _register_gemini_mcp(self, launcher: str, workspace: str, antigravity_url: str):
        """
        Gemini CLI için ~/.gemini/settings.json içine MCP server yazar (global user scope).
        Project-level .gemini/settings.json headless modda okunmadığından global tercih edilir.
        Her çağrıda workspace ve URL güncellenir.
        """
        import json
        home = os.path.expanduser("~")
        gemini_dir = os.path.join(home, ".gemini")
        os.makedirs(gemini_dir, exist_ok=True)
        settings_path = os.path.join(gemini_dir, "settings.json")

        try:
            with open(settings_path) as f:
                settings = json.load(f)
        except Exception:
            settings = {}

        settings.setdefault("mcpServers", {})["antigravity"] = {
            "command": launcher,
            "args": ["--workspace", workspace],
            "env": {
                "ANTIGRAVITY_URL": antigravity_url,
                "WORKSPACE": workspace,
            },
            "trust": True,
        }

        # ⚠️ ÖNEMLI: unityMCP kaydına KESİNLİKLE DOKUNMUYORUZ.
        # ~/.gemini/settings.json'daki unityMCP, Antigravity IDE'nin CoplayDev/unity-mcp
        # reposundan bağımsız olarak kurduğu kendi konfigürasyonudur.
        # Bizim uygulamamız sadece 'antigravity' sunucusunu yönetir, başka hiçbir şeye dokunmaz.

        try:
            with open(settings_path, "w") as f:
                json.dump(settings, f, indent=2)
            logger.info(f"[CLIProvider] Gemini MCP güncellendi: {antigravity_url} → {workspace}")
        except Exception as e:
            logger.warning(f"[CLIProvider] Gemini ~/.gemini/settings.json yazılamadı: {e}")

    def _write_gemini_policy(self, workspace: str) -> str:
        """
        Gemini CLI'ın built-in araçlarını deny eden policy dosyasını TOML formatında yazar.
        --policy flag'i JSON değil TOML bekler; JSON olunca sessizce ignore edilir.
        """
        deny_tools = [
            "run_shell_command",  # Native terminal → MCP run_terminal_command kullanmak zorunda kalır
            "replace",            # Native text replace → MCP write_file kullanmak zorunda kalır
        ]
        # Her araç için ayrı [[rule]] bloğu gerekiyor (TOML array of tables)
        lines = []
        for i, tool in enumerate(deny_tools, start=1):
            lines.append("[[rule]]")
            lines.append(f'toolName = "{tool}"')
            lines.append('decision = "deny"')
            lines.append(f'priority = {i}')
            lines.append("")
        toml_content = "\n".join(lines)

        policy_path = os.path.join(workspace, ".gemini_antigravity_policy.toml")
        try:
            with open(policy_path, "w") as f:
                f.write(toml_content)
        except Exception as e:
            logger.error(f"[CLIProvider] Gemini policy yazılamadı: {e}")
        return policy_path

    def _build_cmd(self, prompt: str, thinking_level: str = "medium", workspace: str = None) -> list:
        full_id = self.binary_name
        if full_id.startswith("claude-"):
            # Built-in tehlikeli araçları blokla → Claude MCP'lerimizi kullanmak ZORUNDA kalır
            # bypassPermissions modu --allowedTools'u pasifleştirdiği için sadece deny-list işe yarar
            disallowed = ",".join([
                "Bash",          # → mcp__antigravity__bash
                "Write",         # → mcp__antigravity__write_file
                "Edit",          # → mcp__antigravity__write_file
                "MultiEdit",     # → mcp__antigravity__write_file
                "NotebookEdit",
            ])
            from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
            unity_running = unity_mcp_manager.is_running()
            unity_section = ""
            if unity_running:
                unity_section = (
                    "\nUNITY EDITOR — unityMCP tools (use these for ALL Unity scene/UI operations):\n"
                    "- Scene hierarchy:               mcp__unityMCP__manage_scene action=get_hierarchy\n"
                    "- Create/modify GameObjects:     mcp__unityMCP__manage_gameobject\n"
                    "- Add/remove/edit components:    mcp__unityMCP__manage_components\n"
                    "- UI elements (Canvas/Button):   mcp__unityMCP__manage_ui\n"
                    "- Scripts (create/attach):       mcp__unityMCP__manage_script\n"
                    "- Materials/shaders:             mcp__unityMCP__manage_material\n"
                    "- Console logs:                  mcp__unityMCP__read_console\n"
                    "RULE: Never write Editor scripts to create scene objects — use unityMCP tools directly.\n"
                    "Only use mcp__antigravity__save_file for runtime C# scripts (.cs), NOT for scene setup.\n"
                )
            subagent_prefix = (
                "SUBAGENT EXECUTION MODE: You are a subagent dispatched to execute a specific task. "
                "Do NOT invoke any skills, do NOT brainstorm, do NOT offer visual companions or mockups, "
                "do NOT ask clarifying questions. Execute the task IMMEDIATELY using available MCP tools. "
                "Respond in Turkish (Türkçe).\n"
                + unity_section + "\n"
            )
            return [
                "claude", "--model", full_id,
                "--permission-mode", "bypassPermissions",
                "--disallowedTools", disallowed,
                "--output-format", "stream-json",
                "--include-partial-messages",
                "--verbose",
                "-p", subagent_prefix + prompt,
            ]
        elif full_id.startswith("gpt-"):
            from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
            unity_running = unity_mcp_manager.is_running()

            unity_section = ""
            if unity_running:
                unity_section = (
                    "\n\nUNITY EDITOR CONTROL (unityMCP tools — use these for ALL Unity operations):\n"
                    "RULE: NEVER read .unity, .prefab or .asset files to answer Unity questions.\n"
                    "      ALWAYS call the live Unity Editor via unityMCP tools instead.\n"
                    "- Scene hierarchy & GameObjects: unityMCP/manage_scene (action='get_hierarchy')\n"
                    "- Find objects:                  unityMCP/find_gameobjects\n"
                    "- Create/modify/delete objects:  unityMCP/manage_gameobject\n"
                    "- Components (add/remove/edit):  unityMCP/manage_components\n"
                    "- UI elements (Button/Text/etc): unityMCP/manage_ui\n"
                    "- Scripts (create/read/update):  unityMCP/manage_script\n"
                    "- Console errors/warnings:       unityMCP/read_console\n"
                    "- Play/Pause/Save scene:         unityMCP/manage_editor\n"
                    "- Materials/shaders:             unityMCP/manage_material\n"
                    "- Physics settings:              unityMCP/manage_physics\n"
                    "Only use antigravity file tools for C# source files (.cs), NOT for Unity scene data.\n"
                )

            mcp_hint = (
                "\n\nIMPORTANT — Tool priority order (follow exactly, no exceptions):\n"
                + unity_section +
                "\nFILE & TERMINAL operations (antigravity tools):\n"
                "- Shell commands (git, npm, mkdir, etc.): mcp__antigravity__run_terminal_command\n"
                "- Create/edit .cs files:                  mcp__antigravity__save_file\n"
                "- Delete files:                           mcp__antigravity__delete_file\n"
                "- Read .cs source files:                  mcp__antigravity__read_file\n"
                "- List directories:                       mcp__antigravity__list_directory\n"
                "\nRESPOND IN TURKISH. Be concise. Never say you cannot do something — use the tools.\n"
            )

            cmd = [
                "codex", "exec",
                "-m", full_id,
                "-s", "read-only",
                "--skip-git-repo-check",
                "--disable", "shell_tool",
                "--disable", "unified_exec",
                "--json",
                "-c", 'mcp_servers.antigravity.default_tools_approval_mode="approve"',
            ]
            if unity_running:
                cmd.extend(["-c", 'mcp_servers.unityMCP.default_tools_approval_mode="approve"'])
            if thinking_level != "off":
                cmd.extend(["-c", f"reasoning.effort={thinking_level}"])
            cmd.append(mcp_hint + "\n" + prompt)
            return cmd
        elif full_id.startswith("gemini"):
            policy_path = self._write_gemini_policy(workspace or os.getcwd())
            mcp_hint = (
                "IMPORTANT: You MUST respond in Turkish (Türkçe) at all times. Never respond in English.\n\n"
                "CRITICAL RULES — follow exactly:\n"
                "1. To CREATE or EDIT any file: use mcp__antigravity__save_file — NO exceptions.\n"
                "   WARNING: There is NO tool called 'write_file' or 'mcp_antigravity_write_file'. Do NOT attempt these — they do not exist. Only 'mcp__antigravity__save_file' works.\n"
                "   FORBIDDEN for file writing: python3 -c, printf, echo, cat, tee, heredoc, perl, ruby, node, bash -c, or ANY shell redirection (>, >>).\n"
                "2. To DELETE a file: use mcp__antigravity__delete_file\n"
                "3. To READ a file: use mcp__antigravity__read_file\n"
                "4. To LIST a directory: use mcp__antigravity__list_directory\n"
                "5. For shell commands ONLY (git, npm, mkdir, mv, rm, etc.): use mcp__antigravity__run_terminal_command\n\n"
                "Never say you cannot perform an action — always call the appropriate MCP tool.\n"
                "SCOPE: Only perform the exact task the user asked. Do NOT create test files (test.txt etc.), analyze unrelated files, or modify anything beyond what was explicitly requested. Never create empty files to test write access.\n\n"
            )
            actual_model = full_id.replace("gemini-cli-", "")
            if actual_model == "gemini":
                actual_model = "gemini-2.0-flash"
            return [
                "gemini",
                "--model", actual_model,
                "--output-format", "stream-json",
                "--policy", policy_path,
                "--skip-trust",
                "-p", mcp_hint + prompt,
            ]
            
        return [full_id, prompt]

    def _get_file_tree(self, workspace: str, max_files: int = 80) -> str:
        """Workspace dosya ağacını string olarak döner (Codex context'i için)."""
        lines = []
        count = 0
        skip_dirs = {".git", "node_modules", "__pycache__", ".next", "venv", "obj", "Library", "Temp"}
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            rel = os.path.relpath(root, workspace)
            prefix = "" if rel == "." else rel + "/"
            for f in files:
                if count >= max_files:
                    lines.append("... (daha fazla dosya var)")
                    return "\n".join(lines)
                lines.append(prefix + f)
                count += 1
        return "\n".join(lines) if lines else "(boş workspace)"

    async def analyze_code(self, prompt: str, max_tokens: int = 4096,
                           images: Optional[List[str]] = None,
                           thinking_level: str = "medium", cwd: Optional[str] = None,
                           interactive: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            workspace = cwd or os.getcwd()
            self._write_mcp_config(workspace)

            # Codex için prompt'a gerçek dosya ağacını ekle (hallucination'ı önler)
            enriched_prompt = prompt
            if self.binary_name.startswith("gpt-"):
                file_tree = self._get_file_tree(workspace)
                enriched_prompt = (
                    f"WORKSPACE: {workspace}\n"
                    f"CURRENT FILES:\n{file_tree}\n\n"
                    f"{prompt}"
                )

            cmd = self._build_cmd(enriched_prompt, thinking_level, workspace)
            _env = {**os.environ, "NO_COLOR": "1", "TERM": "xterm-256color",
                    "COLUMNS": "220", "LINES": "50"}

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_env,
                cwd=workspace,
            )
            logger.info(f"[CLIProvider:{self.binary_name}] PID={process.pid} başlatıldı")

            stderr_buffer = []

            async def _drain_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="ignore").rstrip()
                    stderr_buffer.append(decoded)
                    logger.warning(f"[CLIProvider:{self.binary_name}][STDERR] {decoded}")

            stderr_task = asyncio.create_task(_drain_stderr())

            full_text = ""
            line_count = 0
            _start = asyncio.get_event_loop().time()

            while True:
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=15.0)
                except asyncio.TimeoutError:
                    _now = asyncio.get_event_loop().time()
                    logger.warning(
                        f"[CLIProvider:{self.binary_name}][TIMEOUT] "
                        f"15s'de stdout yok | toplam={_now-_start:.0f}s | "
                        f"pid={process.pid} | rc={process.returncode} | stderr={len(stderr_buffer)}"
                    )
                    # lsof: process'in hangi dosyaları/soketleri açtığını göster
                    try:
                        import subprocess as _sp
                        lsof = _sp.run(
                            ["lsof", "-p", str(process.pid), "-F", "n"],
                            capture_output=True, text=True, timeout=3
                        )
                        open_files = [
                            l[1:] for l in lsof.stdout.splitlines()
                            if l.startswith("n") and l[1:] not in ("/dev/null", "")
                        ]
                        logger.warning(f"[DIAG][LSOF pid={process.pid}] {open_files[:20]}")
                    except Exception as _le:
                        logger.warning(f"[DIAG][LSOF] çalıştırılamadı: {_le}")
                    # Claude CLI kendi log dosyasını ~/.claude/logs/'a yazar — son satırları oku
                    if self.binary_name.startswith("claude"):
                        try:
                            import glob as _glob
                            claude_logs = sorted(
                                _glob.glob(os.path.expanduser("~/.claude/logs/*.log")),
                                key=os.path.getmtime, reverse=True
                            )
                            if claude_logs:
                                with open(claude_logs[0], "r", errors="ignore") as _lf:
                                    tail = _lf.readlines()[-30:]
                                logger.warning(f"[DIAG][CLAUDE_LOG] {claude_logs[0]}:\n{''.join(tail)}")
                        except Exception as _cle:
                            logger.warning(f"[DIAG][CLAUDE_LOG] okunamadı: {_cle}")
                    if process.returncode is not None:
                        logger.error(f"[CLIProvider:{self.binary_name}] Process bitti rc={process.returncode}")
                        break
                    if _now - _start > 120:
                        logger.error(f"[CLIProvider:{self.binary_name}] 120s timeout — kill")
                        process.kill()
                        break
                    continue

                if not line:
                    logger.info(f"[CLIProvider:{self.binary_name}] stdout EOF (toplam {line_count} satır)")
                    break

                raw = _strip_ansi(line.decode("utf-8", errors="ignore")).strip()
                if not raw:
                    continue
                line_count += 1

                import json as _json
                _is_json_provider = (
                    self.binary_name.startswith("claude") or
                    self.binary_name.startswith("gemini") or
                    self.binary_name.startswith("gpt-")
                )
                if _is_json_provider:
                    try:
                        ev = _json.loads(raw)
                        ev_type = ev.get("type", "")

                        # ── Claude stream-json ──────────────────────────────
                        if ev_type == "assistant":
                            for block in ev.get("message", {}).get("content", []):
                                btype = block.get("type", "")
                                if btype == "thinking":
                                    t = block.get("thinking", "").strip()
                                    if t:
                                        yield {"type": "thinking", "text": t}
                                elif btype == "tool_use":
                                    name = block.get("name", "")
                                    inp = block.get("input", {})
                                    hint = f"🔧 `{name}`"
                                    if "path" in inp:
                                        hint += f" → `{inp['path']}`"
                                    elif "action" in inp:
                                        hint += f" → `{inp['action']}`"
                                    yield {"type": "thinking", "text": hint}
                                elif btype == "text":
                                    t = block.get("text", "")
                                    if t:
                                        full_text += t
                                        yield {"type": "delta", "text": t}
                        elif ev_type == "tool":
                            content = ev.get("content", "")
                            result_text = content[:200] if isinstance(content, str) else ""
                            if result_text:
                                yield {"type": "thinking", "text": f"↩ {result_text}"}
                        elif ev_type == "result":
                            result = ev.get("result", "")
                            if result and not full_text:
                                full_text = result

                        # ── Gemini CLI stream-json ──────────────────────────
                        elif ev_type == "content":
                            t = ev.get("content", ev.get("text", ""))
                            if t:
                                full_text += t
                                yield {"type": "delta", "text": t}
                        elif ev_type == "tool_call":
                            name = ev.get("tool", ev.get("name", ""))
                            inp = ev.get("input", ev.get("args", {}))
                            hint = f"🔧 `{name}`"
                            if isinstance(inp, dict):
                                if "path" in inp:
                                    hint += f" → `{inp['path']}`"
                                elif "action" in inp:
                                    hint += f" → `{inp['action']}`"
                            yield {"type": "thinking", "text": hint}
                        elif ev_type == "tool_result":
                            res = str(ev.get("result", ev.get("content", "")))[:200]
                            if res:
                                yield {"type": "thinking", "text": f"↩ {res}"}

                        # ── Codex --json ────────────────────────────────────
                        elif ev_type == "function_call":
                            name = ev.get("name", "")
                            args = ev.get("arguments", {})
                            hint = f"🔧 `{name}`"
                            if isinstance(args, dict):
                                if "path" in args:
                                    hint += f" → `{args['path']}`"
                                elif "action" in args:
                                    hint += f" → `{args['action']}`"
                            yield {"type": "thinking", "text": hint}
                        elif ev_type == "function_call_output":
                            out = str(ev.get("output", ""))[:200]
                            if out:
                                yield {"type": "thinking", "text": f"↩ {out}"}
                        elif ev_type == "reasoning":
                            t = ev.get("content", ev.get("text", "")).strip()
                            if t:
                                yield {"type": "thinking", "text": t}
                        elif ev_type == "message":
                            # Codex final message veya Gemini user/assistant message
                            role = ev.get("role", "")
                            if role == "assistant":
                                content = ev.get("content", "")
                                if isinstance(content, str) and content:
                                    full_text += content
                                    yield {"type": "delta", "text": content}
                                elif isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict) and block.get("type") == "text":
                                            t = block.get("text", "")
                                            if t:
                                                full_text += t
                                                yield {"type": "delta", "text": t}

                        continue
                    except _json.JSONDecodeError:
                        pass  # JSON değilse plain text olarak işle

                # Plain text fallback
                full_text += raw + "\n"
                yield {"type": "delta", "text": raw + "\n"}

            await process.wait()
            await stderr_task

            logger.info(
                f"[CLIProvider:{self.binary_name}][DONE] "
                f"rc={process.returncode} | lines={line_count} | chars={len(full_text)} | "
                f"stderr={len(stderr_buffer)} | süre={asyncio.get_event_loop().time()-_start:.1f}s"
            )

            if process.returncode not in (0, 1, None):
                stderr_full = "\n".join(stderr_buffer)
                logger.error(f"[CLIProvider:{self.binary_name}][FAILED] rc={process.returncode}\nSTDERR:\n{stderr_full}")
                yield {"type": "error", "content": f"❌ CLI hata (rc={process.returncode}): {stderr_full[:500] or '(boş)'}"}
            elif line_count == 0:
                stderr_full = "\n".join(stderr_buffer)
                logger.error(f"[CLIProvider:{self.binary_name}][NO_OUTPUT] Stdout boş!\nSTDERR:\n{stderr_full}")
                yield {"type": "error", "content": f"⚠️ Çıktı yok. Hata: {stderr_full[:500]}"}

            yield {"type": "final", "text": self._clean_response(full_text)}

        except Exception as e:
            logger.exception(f"[CLIProvider:{self.binary_name}] Exception in analyze_code")
            yield {"type": "error", "content": f"❌ CLI Bridge Hatası: {str(e)}"}

    async def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096,
                                         images: Optional[List[str]] = None,
                                         thinking_level: str = "medium", cwd: Optional[str] = None,
                                         interactive: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        async for ev in self.analyze_code(prompt, max_tokens, images, thinking_level, cwd, interactive):
            yield ev


class AIProviderManager:
    @staticmethod
    def get_provider(config: Dict[str, Any]) -> AIProvider:
        p_type = config.get("provider_type", "")
        m_name = config.get("model_name")
        api_key = config.get("api_key", "")

        if p_type == "anthropic" and api_key:
            return AnthropicProvider(api_key=api_key, model_name=m_name)
        elif p_type == "google" and api_key:
            return GeminiProvider(api_key=api_key, model_name=m_name)
        elif p_type == "openai" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.openai.com/v1", model_name=m_name or "gpt-5.5")
        elif p_type == "deepseek" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.deepseek.com", model_name=m_name or "deepseek-v4-pro")
        elif p_type == "groq" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.groq.com/openai/v1", model_name=m_name or "llama-3.3-70b-versatile")
        elif p_type == "openrouter" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://openrouter.ai/api/v1", model_name=m_name or "openai/gpt-5.5")
        elif p_type == "moonshot" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.moonshot.cn/v1", model_name=m_name or "kimi-k3")
        elif p_type == "subscription":
            # m_name burada binary adıdır (claude, copilot vb.)
            return CLIProvider(binary_name=m_name or "claude")
        elif p_type == "ollama":
            return OllamaProvider(model_name=m_name)

        cloud_providers = ("anthropic", "google", "openai", "deepseek", "groq", "openrouter", "moonshot")
        if p_type in cloud_providers and not api_key:
            raise ValueError(
                f"⚠️ {p_type.capitalize()} için API key girilmedi. "
                f"Lütfen Ayarlar'dan API key'inizi girin."
            )

        return OllamaProvider(model_name=m_name)
