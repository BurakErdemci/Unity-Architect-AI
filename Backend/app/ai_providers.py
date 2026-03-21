import re
import ollama
import openai
import google.generativeai as genai
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class AIProvider(ABC):
    @abstractmethod
    def analyze_code(self, prompt: str, max_tokens: int = 4096) -> str:
        pass

    def _clean_response(self, text: str):
        if not text: return ""
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return text.strip()

class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        genai.configure(api_key=api_key)
        
        # --- AKILLI İSİM DÜZELTİCİ ---
        # 404 hatalarını önlemek için alternatif isimleri deniyoruz
        raw_name = model_name.lower() if model_name else ""
        if "2.5-flash" in raw_name:
            self.model_id = "gemini-2.5-flash"
        elif "1.5-flash" in raw_name:
            self.model_id = "gemini-1.5-flash"
        elif "2.0-flash" in raw_name or "2-flash" in raw_name:
            self.model_id = "gemini-2.5-flash"  # 2.0-flash kotası 0, 2.5'e yönlendir
        elif "3-flash" in raw_name:
            self.model_id = "gemini-3-flash-preview"
        else:
            self.model_id = model_name if model_name else "gemini-2.5-flash"

        self.model = genai.GenerativeModel(self.model_id)

    def analyze_code(self, prompt: str, max_tokens: int = 4096) -> str:
        try:
            gen_config = genai.types.GenerationConfig(max_output_tokens=max_tokens)
            response = self.model.generate_content(prompt, generation_config=gen_config)
            if response and response.text:
                return response.text
            return "AI yanıt üretti ancak içerik boş döndü."
        except Exception as e:
            err_str = str(e)
            # Kota hatası (429) için kullanıcı dostu mesaj
            if "429" in err_str:
                return "SİSTEM MESAJI: Google API ücretsiz kota sınırına ulaşıldı. Lütfen 60 saniye bekleyip tekrar deneyin veya Ollama (Yerel) moduna geçin."
            # Model bulunamadı hatası (404)
            if "404" in err_str:
                return f"SİSTEM MESAJI: '{self.model_id}' modeli bulunamadı. Ayarlar'dan 'gemini-1.5-flash' yazarak tekrar deneyin."
            raise Exception(f"Gemini API Hatası: {err_str}")

# Ollama ve OpenAI kısımları aynı kalabilir...
class OllamaProvider(AIProvider):
    def __init__(self, model_name: str = "qwen2.5-coder:7b"):
        self.model_name = model_name if model_name else "qwen2.5-coder:7b"
    def analyze_code(self, prompt: str, max_tokens: int = 4096) -> str:
        try:
            response = ollama.chat(model=self.model_name, messages=[{'role': 'user', 'content': prompt}], options={'num_predict': max_tokens})
            return self._clean_response(response['message']['content'])
        except Exception as e:
            raise Exception(f"Ollama Hatası: {str(e)}")

class OpenAICompatibleProvider(AIProvider):
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
    def analyze_code(self, prompt: str, max_tokens: int = 4096) -> str:
        try:
            response = self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=max_tokens)
            return self._clean_response(response.choices[0].message.content)
        except Exception as e:
            raise Exception(f"API Hatası: {str(e)}")

import anthropic

# --- DEFAULT GROQ MODEL ---
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        
        # --- MODEL ISIM DUZELTICI ---
        raw_name = model_name.lower() if model_name else ""
        if "sonnet-4-6" in raw_name or "sonnet" in raw_name:
            self.model_name = "claude-sonnet-4-6"
        elif "opus-4-6" in raw_name or "opus" in raw_name:
            self.model_name = "claude-opus-4-6"
        elif "haiku" in raw_name:
            self.model_name = "claude-haiku-4-6"
        else:
            self.model_name = "claude-sonnet-4-6"

    def analyze_code(self, prompt: str, max_tokens: int = 4096) -> str:
        try:
            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=max_tokens,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract text from ContentBlock
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text
            
            return self._clean_response(text)
        except Exception as e:
            return f"❌ Anthropic API Hatası: Sistemsel bir ret veya model hatası oluştu. Mesaj: {str(e)}"

class AIProviderManager:
    @staticmethod
    def get_provider(config: Dict[str, Any]) -> AIProvider:
        p_type = config.get("provider_type", "")
        m_name = config.get("model_name")
        api_key = config.get("api_key", "")

        # Kullanıcı bir provider seçtiyse onu kullan
        if p_type == "anthropic" and api_key:
            return AnthropicProvider(api_key=api_key, model_name=m_name)
        elif p_type == "google" and api_key:
            return GeminiProvider(api_key=api_key, model_name=m_name)
        elif p_type == "openai" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.openai.com/v1", model_name=m_name or "gpt-4o-mini")
        elif p_type == "deepseek" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.deepseek.com", model_name=m_name or "deepseek-chat")
        elif p_type == "groq" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.groq.com/openai/v1", model_name=m_name or DEFAULT_GROQ_MODEL)
        elif p_type == "ollama":
            return OllamaProvider(model_name=m_name)
        
        # Kullanıcı hiçbir şey seçmediyse veya API key yoksa → Ollama'ya düş
        return OllamaProvider(model_name=m_name)