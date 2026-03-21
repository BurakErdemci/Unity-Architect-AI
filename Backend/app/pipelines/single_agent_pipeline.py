"""
Single Agent Pipeline (Enhanced) — 4 aşamalı kademeli analiz motoru.
(Ollama, Groq, Gemini, OpenAI gibi tekil/basit API çağrıları için kullanılır)

Aşamalar:
  1. Statik Analiz (Python, anında)
  2. AI Derin Analiz (açıklama)
  3. AI Kod Düzeltme (fix)
  4. Self-Critique & Game Feel (tek çağrıda teknik + hissiyat skoru)
     → Skor < 6.0 ise 1 kez retry (Step 3 + Step 4 tekrar)
"""

import asyncio
import json
import re
import time
import logging
from typing import Dict, Any, List, Optional

from analyzer import UnityAnalyzer
from report_engine import ReportEngine
from prompts import (
    SYSTEM_PROMPT, PROMPT_DEEP_ANALYSIS, PROMPT_CODE_FIX,
    PROMPT_SELF_CRITIQUE,
    get_language_instr, get_relevant_rules
)
from .base import BasePipeline, StepResult

logger = logging.getLogger(__name__)

# ─── Skor Ağırlıkları ───
W_STATIC = 0.3
W_TECH   = 0.4
W_FEEL   = 0.3
RETRY_THRESHOLD = 6.0
MAX_RETRIES = 1  # Skor düşükse 1 ek deneme


class SingleAgentPipeline(BasePipeline):
    """
    Enhanced 4-aşamalı pipeline: Statik → Analiz → Fix → Self-Critique.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._smells: List[Dict] = []
        self._report: Dict[str, Any] = {}
        self._analysis_text: str = ""

    async def run(self):
        pipeline_start = time.time()
        logger.info("🔗 SingleAgent Enhanced Pipeline başlatılıyor...")

        # ─── STEP 1: Statik Analiz ───
        self._result.step1_static = self._step1_static_analysis()
        static_score = self._result.score  # Statik skordan gelen ilk değer

        # ─── STEP 2: AI Derin Analiz ───
        self._result.step2_analysis = await self._step2_deep_analysis()

        # ─── STEP 3 + 4: Fix → Critique Loop ───
        attempt = 0
        critique_result = None
        critique_feedback = ""

        while attempt <= MAX_RETRIES:
            attempt += 1

            # Step 3: Kod Düzeltme
            self._result.step3_code_fix = await self._step3_code_fix(
                extra_feedback=critique_feedback if attempt > 1 else ""
            )

            # Step 4: Self-Critique
            if self._result.fixed_code:
                step4, critique_result = await self._step4_self_critique(static_score)
                self._result.step4_critique = step4
            else:
                break  # Fix başarısız, critique yapma

            if critique_result is None:
                break  # Critique parse edilemedi

            # Skor hesapla
            final_score = self._calculate_final_score(static_score, critique_result)

            logger.info(
                f"  [Attempt {attempt}] Statik: {static_score}, "
                f"Teknik: {critique_result.get('tech_score', '?')}, "
                f"GameFeel: {critique_result.get('game_feel_score', '?')} "
                f"→ BİRLEŞİK: {final_score:.1f}/10"
            )

            # Yeterli skor veya son deneme → çık
            if final_score >= RETRY_THRESHOLD or attempt > MAX_RETRIES:
                break

            # Retry: feedback oluştur
            logger.info(f"  🔄 Skor düşük ({final_score:.1f}), tekrar deneniyor...")
            critique_feedback = self._build_retry_feedback(critique_result)
            
            if self.progress_callback:
                self.progress_callback("step4", "pending")
                self.progress_callback("step3", "in-progress")

        # ─── Sonuçları birleştir ───
        self._result.retry_count = attempt - 1
        if critique_result:
            self._apply_critique_results(static_score, critique_result)

        self._finalize(pipeline_start)

        logger.info(
            f"✅ SingleAgent Enhanced tamamlandı — Skor: {self._result.score}/10, "
            f"Deneme: {attempt}, Toplam: {self._result.total_duration_ms}ms"
        )
        return self._result

    # ═══════════════════════════════════════════════════════════
    # STEP 1: Statik Analiz
    # ═══════════════════════════════════════════════════════════
    def _step1_static_analysis(self) -> StepResult:
        if self.progress_callback: self.progress_callback("step1", "in-progress")
        start = time.time()
        try:
            analyzer = UnityAnalyzer(self.code)
            raw_result = analyzer.analyze()
            self._smells = raw_result.get("smells", [])

            self._report = ReportEngine.build_report(
                self._smells,
                duration_ms=int((time.time() - start) * 1000)
            )

            self._result.score = self._report["score"]
            self._result.score_breakdown = self._report["score_breakdown"]
            self._result.severity_counts = self._report["severity_counts"]
            self._result.total_smells = self._report["total_smells"]
            self._result.summary = self._report["summary"]

            duration = int((time.time() - start) * 1000)
            logger.info(f"  Step 1 ✅ Statik Analiz — {len(self._smells)} bulgu, {duration}ms")
            if self.progress_callback: self.progress_callback("step1", "completed", duration)
            return StepResult(step_name="static_analysis", success=True, duration_ms=duration, output=raw_result)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 1 ❌ Hata: {e}")
            if self.progress_callback: self.progress_callback("step1", "failed", duration)
            return StepResult(step_name="static_analysis", success=False, duration_ms=duration, error=str(e))

    # ═══════════════════════════════════════════════════════════
    # STEP 2: AI Derin Analiz
    # ═══════════════════════════════════════════════════════════
    async def _step2_deep_analysis(self) -> StepResult:
        if self.progress_callback: self.progress_callback("step2", "in-progress")
        start = time.time()
        try:
            lang_instr = get_language_instr(self.language)
            rules_str = get_relevant_rules(self.code)
            smells_str = json.dumps(self._smells, ensure_ascii=False) if self._smells else "Statik analizde sorun bulunamadı."
            severity = self._result.severity_counts

            prompt = PROMPT_DEEP_ANALYSIS.format(
                system_prompt=SYSTEM_PROMPT,
                lang_instr=lang_instr,
                context=self.context or "Yeni sohbet.",
                user_message=self.user_message,
                score=self._result.score,
                summary=self._result.summary,
                critical=severity.get("critical", 0),
                warnings=severity.get("warning", 0),
                infos=severity.get("info", 0),
                smells=smells_str,
                rules=rules_str,
                learned_rules=self._format_learned_rules(),
            )

            self._analysis_text = await self._call_ai(prompt)
            self._result.analysis_text = self._analysis_text

            duration = int((time.time() - start) * 1000)
            logger.info(f"  Step 2 ✅ Derin Analiz — {duration}ms")
            if self.progress_callback: self.progress_callback("step2", "completed", duration)
            return StepResult(step_name="deep_analysis", success=True, duration_ms=duration, output=self._analysis_text)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 2 ❌ Hata: {e}")
            self._analysis_text = f"❌ AI Analiz Hatası: {str(e)}"
            self._result.analysis_text = self._analysis_text
            if self.progress_callback: self.progress_callback("step2", "failed", duration)
            return StepResult(step_name="deep_analysis", success=False, duration_ms=duration, error=str(e))

    # ═══════════════════════════════════════════════════════════
    # STEP 3: AI Kod Düzeltme
    # ═══════════════════════════════════════════════════════════
    async def _step3_code_fix(self, extra_feedback: str = "") -> StepResult:
        if self.progress_callback: self.progress_callback("step3", "in-progress")
        start = time.time()
        try:
            lang_instr = get_language_instr(self.language)
            rules_str = get_relevant_rules(self.code)
            analysis_summary = self._analysis_text[:2000] if self._analysis_text else "Analiz yapılamadı."

            # Retry feedback varsa analiz özetine ekle
            if extra_feedback:
                analysis_summary += f"\n\n{extra_feedback}"

            prompt = PROMPT_CODE_FIX.format(
                lang_instr=lang_instr,
                original_code=self.code,
                analysis_summary=analysis_summary,
                rules=rules_str,
                learned_rules=self._format_learned_rules(),
            )

            fixed_code_raw = await self._call_ai(prompt)
            self._result.fixed_code = self._extract_code(fixed_code_raw)

            duration = int((time.time() - start) * 1000)
            logger.info(f"  Step 3 ✅ Kod Düzeltme — {duration}ms")
            if self.progress_callback: self.progress_callback("step3", "completed", duration)
            return StepResult(step_name="code_fix", success=True, duration_ms=duration, output=self._result.fixed_code)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 3 ❌ Hata: {e}")
            self._result.fixed_code = ""
            if self.progress_callback: self.progress_callback("step3", "failed", duration)
            return StepResult(step_name="code_fix", success=False, duration_ms=duration, error=str(e))

    # ═══════════════════════════════════════════════════════════
    # STEP 4: Self-Critique (TEKNİK + GAME FEEL tek çağrıda)
    # ═══════════════════════════════════════════════════════════
    async def _step4_self_critique(self, static_score: float):
        if self.progress_callback: self.progress_callback("step4", "in-progress")
        start = time.time()
        try:
            lang_instr = get_language_instr(self.language)

            prompt = PROMPT_SELF_CRITIQUE.format(
                lang_instr=lang_instr,
                original_code=self.code,
                fixed_code=self._result.fixed_code,
                total_smells=self._result.total_smells,
                static_score=static_score,
            )

            response = await self._call_ai(prompt)
            critique_result = self._parse_critique_json(response)

            duration = int((time.time() - start) * 1000)

            if critique_result:
                logger.info(
                    f"  Step 4 ✅ Self-Critique — tech: {critique_result.get('tech_score', '?')}, "
                    f"feel: {critique_result.get('game_feel_score', '?')}, {duration}ms"
                )
                if self.progress_callback: self.progress_callback("step4", "completed", duration)
                return StepResult(step_name="self_critique", success=True, duration_ms=duration, output=critique_result), critique_result
            else:
                logger.warning(f"  Step 4 ⚠️ JSON parse edilemedi, {duration}ms")
                if self.progress_callback: self.progress_callback("step4", "failed", duration)
                return StepResult(step_name="self_critique", success=False, duration_ms=duration, error="JSON parse hatası"), None

        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 4 ❌ Hata: {e}")
            if self.progress_callback: self.progress_callback("step4", "failed", duration)
            return StepResult(step_name="self_critique", success=False, duration_ms=duration, error=str(e)), None

    # ═══════════════════════════════════════════════════════════
    # SKOR HESAPLAMA
    # ═══════════════════════════════════════════════════════════
    def _calculate_final_score(self, static_score: float, critique: Dict) -> float:
        tech = float(critique.get("tech_score", static_score))
        feel = float(critique.get("game_feel_score", -1))

        if feel < 0:
            # Game feel değerlendirilemedi → sadece statik + teknik
            return (static_score * 0.4) + (tech * 0.6)
        else:
            return (static_score * W_STATIC) + (tech * W_TECH) + (feel * W_FEEL)

    def _apply_critique_results(self, static_score: float, critique: Dict):
        """Critique sonuçlarını pipeline result'a yansıt."""
        final_score = self._calculate_final_score(static_score, critique)
        self._result.score = round(final_score, 1)
        self._result.summary = critique.get("review_message", self._result.summary)

        # Game Feel verilerini sakla
        gf_data = {}
        for key in ["movement", "combat", "physics", "camera", "juice"]:
            if key in critique and isinstance(critique[key], dict):
                gf_data[key] = critique[key]
        gf_data["game_feel_score"] = critique.get("game_feel_score", -1)
        gf_data["suggestions"] = critique.get("suggestions", [])
        gf_data["summary"] = critique.get("summary", "")
        self._result.game_feel_data = gf_data

    # ═══════════════════════════════════════════════════════════
    # RETRY FEEDBACK
    # ═══════════════════════════════════════════════════════════
    def _build_retry_feedback(self, critique: Dict) -> str:
        parts = []
        parts.append("[ÖNCEKİ DENEME ELEŞTİRİSİ — BU HATALARI DÜZELT]")
        parts.append(f"Teknik Puan: {critique.get('tech_score', '?')}/10")
        parts.append(f"Eleştiri: {critique.get('review_message', 'Kalite yetersiz.')}")

        gf_summary = critique.get("summary", "")
        if gf_summary:
            parts.append(f"Oyun Hissiyatı: {gf_summary}")

        suggestions = critique.get("suggestions", [])
        if suggestions:
            parts.append("Öneriler: " + "; ".join(suggestions[:3]))

        parts.append("Lütfen yukarıdaki eleştirileri dikkate alarak kodu TAMAMEN yeniden yaz!")
        return "\n".join(parts)

    # ═══════════════════════════════════════════════════════════
    # YARDIMCI METODLAR
    # ═══════════════════════════════════════════════════════════
    # Provider başına max_tokens limitleri
    _TOKEN_LIMITS = {
        "groq": 32000,
        "openai": 16384,
        "openrouter": 16384,
        "deepseek": 16384,
        "anthropic": 16384,
        "google": 65536,
    }

    async def _call_ai(self, prompt: str, max_tokens: int = None) -> str:
        """Provider türüne göre AI çağrısı yapar. max_tokens=None → provider limitine kadar."""
        if self.provider_type == "ollama":
            return await self._call_ollama(prompt, max_tokens or -1)

        limit = self._TOKEN_LIMITS.get(self.provider_type, 16384)
        effective_tokens = min(max_tokens, limit) if max_tokens else limit
        return await asyncio.to_thread(self.provider.analyze_code, prompt, effective_tokens)

    async def _call_ollama(self, prompt: str, max_tokens: int = -1) -> str:
        import ollama
        model_name = getattr(self.provider, "model_name", "qwen2.5-coder:7b")
        def _sync_call():
            opts = {"num_predict": max_tokens} if max_tokens > 0 else {}
            response = ollama.chat(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                options=opts
            )
            return response["message"]["content"]
        return await asyncio.wait_for(asyncio.to_thread(_sync_call), timeout=120)

    def _parse_critique_json(self, response: str) -> Optional[Dict]:
        """Self-Critique JSON yanıtını parse eder. Markdown ve truncated JSON kurtarma içerir."""
        from validator import ResponseValidator

        # 1. Validator ile dene
        is_valid, parsed = ResponseValidator.validate_json_response(
            response,
            required_keys=["tech_score", "review_message"]
        )

        if is_valid and parsed:
            for key in ["tech_score", "game_feel_score"]:
                if key in parsed and isinstance(parsed[key], (int, float)):
                    parsed[key] = max(0.0, min(10.0, float(parsed[key])))
            return parsed

        # 2. Fallback: Markdown bloğunu manuel soy ve truncated JSON'u kurtarmayı dene
        text = response.strip()
        # ```json ... ``` soy
        md_match = re.search(r'```(?:json)?\s*([\s\S]*)', text)
        if md_match:
            text = md_match.group(1).strip()
            # Sondaki ``` varsa kaldır
            if text.endswith("```"):
                text = text[:-3].strip()

        # { ile başlayan kısmı bul
        brace_start = text.find("{")
        if brace_start >= 0:
            text = text[brace_start:]

            # Truncated JSON kurtarma: açık parantezleri kapat
            open_count = text.count("{") - text.count("}")
            if open_count > 0:
                # Sonundaki yarım key/value'yu kes
                last_comma = text.rfind(",")
                last_brace = text.rfind("}")
                if last_comma > last_brace:
                    text = text[:last_comma]
                text += "}" * open_count

            try:
                parsed = json.loads(text, strict=False)
                if isinstance(parsed, dict) and "tech_score" in parsed:
                    for key in ["tech_score", "game_feel_score"]:
                        if key in parsed and isinstance(parsed[key], (int, float)):
                            parsed[key] = max(0.0, min(10.0, float(parsed[key])))
                    logger.info("[Self-Critique] JSON fallback kurtarma başarılı")
                    return parsed
            except json.JSONDecodeError:
                pass

        logger.warning(f"[Self-Critique] JSON parse başarısız: {response[:200]}...")
        return None

    def _extract_code(self, text: str) -> str:
        """Markdown içerisinden sadece C# kodunu çıkarır. Truncated blokları da kurtarır."""
        if not text:
            return ""

        # 1. Normal kapalı blok: ```csharp ... ```
        match = re.search(r'```(?:csharp|cs)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # 2. Truncated blok: ```csharp ... (kapanış yok — token bitti)
        match_open = re.search(r'```(?:csharp|cs)?\s*(.*)', text, re.DOTALL | re.IGNORECASE)
        if match_open:
            code = match_open.group(1).strip()
            # Sondaki markdown artıklarını temizle
            code = re.sub(r'```\s*$', '', code).strip()
            if code:
                return code

        # 3. Header/açıklama metni varsa at, sadece kod kısmını döndür
        lines = text.strip().split("\n")
        code_lines = [l for l in lines if not l.startswith("#") and not l.startswith("**")]
        return "\n".join(code_lines).strip()

    def _format_learned_rules(self) -> str:
        if not self.learned_rules:
            return ""
        return f"\n[KULLANICIDAN ÖĞRENILEN KURALLAR]\n{self.learned_rules}\n"

    def _finalize(self, pipeline_start: float):
        total = int((time.time() - pipeline_start) * 1000)
        self._result.total_duration_ms = total

        parts = []

        # Retry bilgisi
        retry_info = f" (🔄 {self._result.retry_count + 1} deneme)" if self._result.retry_count > 0 else ""

        # Skor başlığı
        status_emoji = "🚀" if self._result.score >= 8 else "⚠️" if self._result.score >= 5 else "❌"

        # Analiz metni (Step 2'den gelen)
        if self._result.analysis_text:
            parts.append(self._result.analysis_text)

        # Self-Critique özeti (Step 4 başarılıysa)
        if self._result.game_feel_data and self._result.game_feel_data.get("game_feel_score", -1) >= 0:
            critique_section = self._format_game_feel_section()
            if critique_section:
                parts.append(critique_section)

        # Skor kartını komple kaldırdık, artık UI render ediyor.

        # Düzeltilmiş kod (AI zaten header ekleyebilir, tekrar ekleme)
        if self._result.fixed_code:
            code = self._result.fixed_code
            # Eğer kod zaten "### ✅" ile başlıyorsa tekrar sarma
            if code.strip().startswith("### ✅") or code.strip().startswith("```"):
                parts.append(code)
            else:
                parts.append(f"### ✅ Düzeltilmiş Kod\n```csharp\n{code}\n```")

        self._result.combined_response = "\n\n".join(parts)

    def _format_game_feel_section(self) -> str:
        """Game Feel verilerini UI-ready formata çevirir."""
        gf = self._result.game_feel_data
        if not gf:
            return ""

        lines = ["**🎮 Oyun Hissiyatı Detayları:**"]

        categories = [
            ("🕹️ Hareket", "movement"),
            ("⚔️ Combat", "combat"),
            ("🎯 Fizik", "physics"),
            ("📷 Kamera", "camera"),
            ("✨ Polish", "juice"),
        ]
        for label, key in categories:
            cat = gf.get(key, {})
            if isinstance(cat, dict) and cat.get("verdict") not in ("none", "unknown", None) and cat.get("score", 0) > 0:
                lines.append(f"- {label}: **{cat.get('verdict', '?')}** — {cat.get('detail', '')}")

        suggestions = gf.get("suggestions", [])
        if suggestions:
            lines.append("\n**💡 İyileştirme Önerileri:**")
            for s in suggestions[:3]:
                lines.append(f"- {s}")

        return "\n".join(lines) if len(lines) > 1 else ""
