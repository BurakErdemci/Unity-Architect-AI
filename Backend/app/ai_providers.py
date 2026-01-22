import re
import ollama
import openai
import google.generativeai as genai
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class AIProvider(ABC):
    @abstractmethod
    def analyze_code(self, prompt: str) -> str:
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
        raw_name = model_name.lower()
        if "1.5-flash" in raw_name:
            self.model_id = "gemini-1.5-flash"
        elif "2.0-flash" in raw_name:
            self.model_id = "gemini-2.0-flash"
        elif "3-flash" in raw_name:
            self.model_id = "gemini-3-flash-preview"
        else:
            self.model_id = model_name if model_name else "gemini-1.5-flash"

        self.model = genai.GenerativeModel(self.model_id)

    def analyze_code(self, prompt: str) -> str:
        try:
            # v1beta yerine v1 zorlaması gerekirse kütüphane bunu halleder
            response = self.model.generate_content(prompt)
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
    def analyze_code(self, prompt: str) -> str:
        try:
            response = ollama.chat(model=self.model_name, messages=[{'role': 'user', 'content': prompt}])
            return self._clean_response(response['message']['content'])
        except Exception as e:
            raise Exception(f"Ollama Hatası: {str(e)}")

class OpenAICompatibleProvider(AIProvider):
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
    def analyze_code(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], temperature=0.3)
            return self._clean_response(response.choices[0].message.content)
        except Exception as e:
            raise Exception(f"API Hatası: {str(e)}")

class AIProviderManager:
    @staticmethod
    def get_provider(config: Dict[str, Any]) -> AIProvider:
        p_type = config.get("provider_type", "ollama")
        m_name = config.get("model_name")
        api_key = config.get("api_key", "")
        if p_type == "google":
            return GeminiProvider(api_key=api_key, model_name=m_name)
        elif p_type == "openai":
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.openai.com/v1", model_name=m_name)
        elif p_type == "deepseek":
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.deepseek.com", model_name=m_name)
        return OllamaProvider(model_name=m_name)