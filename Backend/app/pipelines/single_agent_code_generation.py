"""
SingleAgentCodeGenerationPipeline — Tek istek ile sıfırdan kod üretir.
Multi-Agent versiyonundan farklı olarak Architect + Coder + GameFeel ayrı ayrı çalışmaz.
Tek bir prompt'ta hem planlama hem kod üretimi hem de game feel kuralları birleştirilir.

Claude hariç TÜM provider'lar bu pipeline'ı kullanır.
"""
import logging
import re
import time
import asyncio
from typing import Any

from pipelines.base import BasePipeline, PipelineResult, StepResult
from prompts import get_language_instr, get_relevant_rules

logger = logging.getLogger(__name__)

# Provider başına max_tokens limitleri
_TOKEN_LIMITS = {
    "groq": 32000,
    "openai": 16384,
    "openrouter": 16384,
    "deepseek": 16384,
    "anthropic": 16384,
    "google": 65536,
    "ollama": -1,  # sınırsız
}


class SingleAgentCodeGenerationPipeline(BasePipeline):
    """
    Sıfırdan kod üretmek için kullanılan Single-Agent sistemi.
    TEK bir LLM çağrısı ile hem mimari kararı hem kodu üretir.
    Avantaj: Hızlı, az token, ucuz modellerde çalışır.
    """

    def __init__(
        self,
        prompt: str,
        provider: Any,
        language: str = "tr",
        context: str = "",
        user_message: str = "",
        provider_type: str = "unknown",
        progress_callback=None
    ):
        super().__init__("", "", provider, language, context, "", user_message, provider_type, progress_callback)
        self.prompt = prompt

    def _get_max_tokens(self) -> int:
        """Provider türüne göre güvenli max_tokens döndürür."""
        return _TOKEN_LIMITS.get(self.provider_type, 16384)

    async def _call_ai(self, prompt: str) -> str:
        """Provider'a göre AI çağrısı yapar."""
        if self.provider_type == "ollama":
            return await self._call_ollama(prompt)

        max_tokens = self._get_max_tokens()
        return await asyncio.to_thread(self.provider.analyze_code, prompt, max_tokens)

    async def _call_ollama(self, prompt: str) -> str:
        """Ollama için özel çağrı."""
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

        # --- TEK ADIM: KOD ÜRETİMİ ---
        if self.progress_callback:
            self.progress_callback("step1", "in-progress")

        start = time.time()

        combined_prompt = f"""You are an expert Unity C# code generator. Your ONLY job is to write complete, production-ready code from scratch.

CRITICAL RULES:
- You are a CODE WRITER, NOT an analyst. NEVER write "Findings", "Performance", "Score" headers.
- Write the FULL code — never truncate with "..." or leave methods empty.
- Output MUST follow the exact format below.

{lang_instr}

[PREVIOUS CONVERSATION CONTEXT]
{self.context}

[USER REQUEST]
{self.prompt}

[UNITY BEST PRACTICES TO FOLLOW]
{rules_str}

[GAME FEEL — CRITICAL]
- Character movement: Use rb.velocity or CharacterController. NEVER use AddForce for player movement.
- Jumping: Apply gravity multiplier during fall (prevent floating).
- Combat: Respond instantly to input — zero delay.
- General: Player controls must feel sharp and satisfying (snappy).
- Camera: Smooth follow with slight lag, never rigid lock.
- Effects: Use Time.timeScale for hit-stop, screen shake for impacts.

[CLARIFICATION — BEFORE WRITING CODE]
If the user's request is vague or missing critical details (e.g., "RPG sistemi yap", "inventory yap", "bir oyun yap"), DO NOT write code yet.
Instead, ask ALL missing questions in a SINGLE message (max 4 questions). Examples:
- 2D mi 3D mü?
- Veri nerede saklanacak (ScriptableObject / JSON / PlayerPrefs)?
- UI gerekiyor mu?
- Mevcut sistemle entegrasyon var mı?

If the request is already specific enough (e.g., "2D platformer Rigidbody tabanlı karakter kontrolcüsü"), skip questions and generate directly.
If the previous conversation context shows the user already answered clarification questions, use those answers and generate code — do NOT ask again.

[TOKEN LIMIT — GRACEFUL ENDING]
If you cannot fit the ENTIRE system in a single response:
1. Write the most important, FULLY WORKING part (e.g., core class + main methods — no half-finished code).
2. At the very end, add this section:
   ⏳ **Devam:** [Yazılmayan dosya/sistem adlarını listele]
   Devam edeyim mi? ✋
3. NEVER leave a half-open method, unclosed brace, or syntax error — everything you write must compile.

[OUTPUT FORMAT — FOLLOW EXACTLY — NO EXCEPTIONS]
1. ONE short sentence summarizing your approach (e.g., "Here is your rb.velocity-based 2D movement system:")
2. For EACH FILE output a separate section — NEVER merge multiple files into one block:

   **📄 FileName.cs**
   ```csharp
   // full, working code for this file only
   ```

   **📄 AnotherFile.cs**
   ```csharp
   // full, working code for this file only
   ```

3. Single-file systems: still use ONE ```csharp block with the **📄 FileName.cs** header above it.
4. Below ALL code blocks, write ONLY a "🎮 Editor Setup" section with 1-3 bullet points.

[BANNED]
- NO merging multiple classes/files into a single ```csharp block — EVERY file gets its own block
- NO truncated code or "..." placeholders
- NO lengthy explanations — be concise
- NO greetings or farewells"""

        try:
            response = await self._call_ai(combined_prompt)
        except Exception as e:
            logger.error(f"SingleAgent CodeGen hatası: {e}")
            response = f"❌ Kod üretimi başarısız: {str(e)}"

        response = self._fix_truncated_response(response)
        duration = int((time.time() - start) * 1000)

        if self.progress_callback:
            self.progress_callback("step1", "completed", duration)

        logger.info(f"  Step 1 ✅ Kod Üretimi — {duration}ms")

        # Sonuçları ayarla
        self._result.step2_analysis = StepResult("Kod Üretimi", True, duration, response)
        self._result.analysis_text = response
        self._result.combined_response = response

        return self._result

    def _is_truncated(self, text: str) -> bool:
        """Yanıtın token limitinde kesilip kesilmediğini kontrol eder (açık ``` bloğu var mı)."""
        if not text:
            return False
        blocks = re.findall(r'```', text)
        return len(blocks) % 2 == 1

    def _fix_truncated_response(self, text: str) -> str:
        """Kesilmiş yanıtı kapatır ve kullanıcıya devam mesajı ekler."""
        if not self._is_truncated(text):
            return text
        logger.warning("  [Truncation] Yanıt token limitinde kesildi — devam mesajı ekleniyor.")
        fixed = text.rstrip() + "\n// ... (yanıt kesildi)\n```"
        fixed += (
            "\n\n---\n"
            "⏳ **Token limitine ulaşıldı — yanıt kesildi.**\n\n"
            "Kalan dosyaları yazmamı ister misin? **Devam et** yazman yeterli. ✋"
        )
        return fixed
