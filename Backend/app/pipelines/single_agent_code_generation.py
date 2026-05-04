"""
SingleAgentCodeGenerationPipeline — Tek istek ile sıfırdan kod üretir.

Claude hariç TÜM provider'lar bu pipeline'ı kullanır.
Partner modunda çalışır — gereksiz kurallar azaltıldı, context aktif kullanılıyor.
"""
import logging
import re
import time
import asyncio
from typing import Any

from pipelines.base import BasePipeline, PipelineResult, StepResult
from prompts import SYSTEM_PROMPT, get_language_instr, get_relevant_rules

logger = logging.getLogger(__name__)

# Provider başına max_tokens limitleri
_TOKEN_LIMITS = {
    "groq": 32000,
    "openai": 16384,
    "openrouter": 16384,
    "deepseek": 16384,
    "anthropic": 16384,
    "google": 65536,
    "ollama": -1,
}


class SingleAgentCodeGenerationPipeline(BasePipeline):
    """
    Sıfırdan kod üretmek için kullanılan Single-Agent sistemi.
    TEK bir LLM çağrısı ile hem mimari kararı hem kodu üretir.
    """

    def __init__(
        self,
        prompt: str,
        provider: Any,
        language: str = "tr",
        context: str = "",
        user_message: str = "",
        provider_type: str = "unknown",
        progress_callback=None,
        use_thinking: bool = False
    ):
        super().__init__("", "", provider, language, context, "", user_message, provider_type, progress_callback, use_thinking)
        self.prompt = prompt

    def _get_max_tokens(self) -> int:
        return _TOKEN_LIMITS.get(self.provider_type, 16384)

    async def _call_ai(self, prompt: str) -> str:
        if self.provider_type == "ollama":
            return await self._call_ollama(prompt)
        max_tokens = self._get_max_tokens()
        if self.use_thinking and hasattr(self.provider, 'analyze_code_with_thinking'):
            response_text, thinking_text, thinking_ms = await asyncio.to_thread(
                self.provider.analyze_code_with_thinking, prompt, max_tokens
            )
            self._result.thinking_text = thinking_text
            self._result.thinking_duration_ms = thinking_ms
            return response_text
        return await asyncio.to_thread(self.provider.analyze_code, prompt, max_tokens)

    async def _call_ollama(self, prompt: str) -> str:
        import ollama
        model_name = getattr(self.provider, "model_name", "qwen2.5-coder:7b")
        def _sync():
            resp = ollama.chat(model=model_name, messages=[{"role": "user", "content": prompt}])
            return resp.get("message", {}).get("content", "")
        return await asyncio.to_thread(_sync)

    async def run(self) -> PipelineResult:
        logger.info("🔗 SingleAgent CodeGeneration Pipeline başlatılıyor...")
        logger.info(f"  Provider: {self.provider_type}, Max tokens: {self._get_max_tokens()}")

        rules_str = get_relevant_rules(self.prompt)
        lang_instr = get_language_instr(self.language)

        if self.progress_callback:
            self.progress_callback("step1", "in-progress")

        start = time.time()

        combined_prompt = f"""{SYSTEM_PROMPT}

{lang_instr}

[GÖREV]
Kullanıcının isteğine göre Unity C# kodu üret.

[ÖNCEKİ SOHBET BAĞLAMI]
{self.context or "Yeni sohbet."}

[KULLANICI İSTEĞİ]
{self.prompt}

[UNITY KURALLARI]
{rules_str}

[OYUN HİSSİYATI]
- Karakter hareketi: rb.velocity veya CharacterController kullan. AddForce ile hareket yapma.
- Zıplama: Düşüşte gravity multiplier uygula.
- Combat: Input'a anında yanıt ver.
- Kamera: Smooth follow, LateUpdate içinde.

[SAVE/LOAD]
- Save gerekiyorsa: JSON dosya (Application.persistentDataPath + "/save.json") kullan.
- PlayerPrefs kullanma (kullanıcı açıkça istemedikçe).

[AÇIKLAMA İHTİYACI]
Eğer istek belirsizse veya kritik detaylar eksikse, kod yazma — tek mesajda max 4 soru sor.
Eğer önceki sohbet bağlamında cevaplar varsa, direkt kodu yaz.

[TOKEN LİMİTİ]
Tüm kodu tek yanıta sığdıramazsan:
1. En önemli kısmı ÇALIŞIR halde yaz.
2. Sonuna ekle: ⏳ **Devam:** [kalan dosyalar] — Devam edeyim mi? ✋
3. Yarım metod, açık parantez bırakma.

[FORMAT]
1. Kısa bir giriş cümlesi (1 satır).
2. Her dosya için ayrı blok:

   **📄 DosyaAdi.cs**
   ```csharp
   // tam kod
   ```

3. Sonunda max 3 madde ile "🎮 Editor Kurulumu" yaz.

[YASAK]
- Birden fazla dosyayı tek ```csharp bloğuna koyma
- Kod kısaltma ("...") yapma
- Uzun açıklama yazma"""

        try:
            response = await self._call_ai(combined_prompt)
        except Exception as e:
            error_str = str(e)
            logger.error(f"SingleAgent CodeGen hatası: {e}")
            if "413" in error_str or "Request too large" in error_str or "tokens per minute" in error_str.lower():
                response = (
                    "⚠️ **Token Limiti Aşıldı**\n\n"
                    "Bu istek için yeterli token limiti yok.\n"
                    "Daha kısa bir istek yapın veya farklı bir model seçin."
                )
            else:
                response = f"❌ Kod üretimi başarısız: {error_str}"

        response = self._fix_truncated_response(response)
        duration = int((time.time() - start) * 1000)

        if self.progress_callback:
            self.progress_callback("step1", "completed", duration)

        logger.info(f"  Step 1 ✅ Kod Üretimi — {duration}ms")

        self._result.step2_analysis = StepResult("Kod Üretimi", True, duration, response)
        self._result.analysis_text = response
        self._result.combined_response = response

        return self._result

    def _is_truncated(self, text: str) -> bool:
        if not text:
            return False
        blocks = re.findall(r'```', text)
        return len(blocks) % 2 == 1

    def _fix_truncated_response(self, text: str) -> str:
        if not self._is_truncated(text):
            return text
        logger.warning("  [Truncation] Yanıt kesildi — devam mesajı ekleniyor.")
        fixed = text.rstrip() + "\n// ... (yanıt kesildi)\n```"
        fixed += (
            "\n\n---\n"
            "⏳ **Token limitine ulaşıldı — yanıt kesildi.**\n\n"
            "Kalan dosyaları yazmamı ister misin? **Devam et** yazman yeterli. ✋"
        )
        return fixed
