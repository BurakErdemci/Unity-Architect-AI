from typing import Dict, Any
from .api_providers import GeminiProvider, OllamaProvider, OpenAICompatibleProvider, AnthropicProvider, DEFAULT_GROQ_MODEL
from .claude_provider import ClaudeCodeProvider
from .codex_provider import CodexProvider
from .agy_provider import AgyProvider
from .cursor_provider import CursorProvider
from .copilot_provider import CopilotProvider
from .opencode_provider import OpenCodeProvider
from .cli_base import BaseCLIProvider as CLIProvider
from .base import AIProvider


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
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.moonshot.cn/v1", model_name=m_name or "kimi-k2.7-code")
        elif p_type == "z-ai" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.z.ai/api/paas/v4", model_name=m_name or "glm-5.2")
        elif p_type == "subscription":
            # m_name burada binary adıdır (claude, codex, agy, cursor-*, copilot-*, opencode:*)
            name = m_name or "claude"
            if name.startswith("cursor-"):
                return CursorProvider(binary_name=name)
            elif name.startswith("copilot-"):
                return CopilotProvider(binary_name=name)
            elif name.startswith("opencode:"):
                return OpenCodeProvider(binary_name=name)
            elif name.startswith("gpt-"):
                return CodexProvider(binary_name=name)
            elif name.startswith(("gemini", "agy-")):
                return AgyProvider(binary_name=name)
            else:  # claude-* ve diğerleri
                return ClaudeCodeProvider(binary_name=name)
        elif p_type == "ollama":
            return OllamaProvider(model_name=m_name)

        cloud_providers = ("anthropic", "google", "openai", "deepseek", "groq", "openrouter", "moonshot", "z-ai")
        if p_type in cloud_providers and not api_key:
            raise ValueError(
                f"⚠️ {p_type.capitalize()} için API key girilmedi. "
                f"Lütfen Ayarlar'dan API key'inizi girin."
            )

        return OllamaProvider(model_name=m_name)
