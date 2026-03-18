"""
Single Agent Pipeline — Mevcut 3 aşamalı kademeli analiz motoru.
(Ollama, Groq, Gemini, OpenAI gibi tekil/basit API çağrıları için kullanılır)
"""

import asyncio
import json
import time
import logging
from typing import Dict, Any, List

from analyzer import UnityAnalyzer
from report_engine import ReportEngine
from prompts import (
    SYSTEM_PROMPT, PROMPT_DEEP_ANALYSIS, PROMPT_CODE_FIX,
    get_language_instr, get_relevant_rules
)
from .base import BasePipeline, StepResult

logger = logging.getLogger(__name__)

class SingleAgentPipeline(BasePipeline):
    """
    3 aşamalı kademeli analiz pipeline'ı (Mevcut sistem).
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._smells: List[Dict] = []
        self._report: Dict[str, Any] = {}
        self._analysis_text: str = ""

    async def run(self):
        """Pipeline'ın 3 adımını sırayla çalıştırır."""
        pipeline_start = time.time()
        logger.info("🔗 SingleAgent Pipeline başlatılıyor...")

        # ─── STEP 1: Statik Analiz (Python, anında) ───
        self._result.step1_static = self._step1_static_analysis()

        # ─── STEP 2: AI Derin Analiz ───
        self._result.step2_analysis = await self._step2_deep_analysis()

        # ─── STEP 3: AI Kod Düzeltme ───
        self._result.step3_code_fix = await self._step3_code_fix()

        # ─── Sonuçları birleştir ───
        self._finalize(pipeline_start)

        logger.info(
            f"✅ SingleAgent Pipeline tamamlandı — Skor: {self._result.score}/10, "
            f"Toplam: {self._result.total_duration_ms}ms"
        )
        return self._result

    def _step1_static_analysis(self) -> StepResult:
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

            return StepResult(step_name="static_analysis", success=True, duration_ms=duration, output=raw_result)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 1 ❌ Hata: {e}")
            return StepResult(step_name="static_analysis", success=False, duration_ms=duration, error=str(e))

    async def _step2_deep_analysis(self) -> StepResult:
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

            if self.provider_type == "ollama":
                self._analysis_text = await self._call_ollama(prompt)
            else:
                self._analysis_text = await asyncio.to_thread(self.provider.analyze_code, prompt)

            self._result.analysis_text = self._analysis_text
            duration = int((time.time() - start) * 1000)
            logger.info(f"  Step 2 ✅ Derin Analiz — {duration}ms")
            return StepResult(step_name="deep_analysis", success=True, duration_ms=duration, output=self._analysis_text)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 2 ❌ Hata: {e}")
            self._analysis_text = f"❌ AI Analiz Hatası: {str(e)}"
            self._result.analysis_text = self._analysis_text
            return StepResult(step_name="deep_analysis", success=False, duration_ms=duration, error=str(e))

    async def _step3_code_fix(self) -> StepResult:
        start = time.time()
        try:
            lang_instr = get_language_instr(self.language)
            rules_str = get_relevant_rules(self.code)
            analysis_summary = self._analysis_text[:1500] if self._analysis_text else "Analiz yapılamadı."

            prompt = PROMPT_CODE_FIX.format(
                lang_instr=lang_instr,
                original_code=self.code,
                analysis_summary=analysis_summary,
                rules=rules_str,
                learned_rules=self._format_learned_rules(),
            )

            if self.provider_type == "ollama":
                fixed_code = await self._call_ollama(prompt)
            else:
                fixed_code = await asyncio.to_thread(self.provider.analyze_code, prompt)

            self._result.fixed_code = fixed_code
            duration = int((time.time() - start) * 1000)
            logger.info(f"  Step 3 ✅ Kod Düzeltme — {duration}ms")
            return StepResult(step_name="code_fix", success=True, duration_ms=duration, output=fixed_code)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 3 ❌ Hata: {e}")
            self._result.fixed_code = ""
            return StepResult(step_name="code_fix", success=False, duration_ms=duration, error=str(e))

    async def _call_ollama(self, prompt: str) -> str:
        import ollama
        model_name = getattr(self.provider, "model_name", "qwen2.5-coder:7b")
        def _sync_call():
            response = ollama.chat(
                model=model_name,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
            )
            return response["message"]["content"]
        return await asyncio.wait_for(asyncio.to_thread(_sync_call), timeout=120)

    def _format_learned_rules(self) -> str:
        if not self.learned_rules: return ""
        return f"\n[KULLANICIDAN ÖĞRENILEN KURALLAR]\n{self.learned_rules}\n"

    def _finalize(self, pipeline_start: float):
        total = int((time.time() - pipeline_start) * 1000)
        self._result.total_duration_ms = total

        parts = []
        if self._result.analysis_text: parts.append(self._result.analysis_text)
        if self._result.fixed_code: parts.append(self._result.fixed_code)
        self._result.combined_response = "\n\n".join(parts)
