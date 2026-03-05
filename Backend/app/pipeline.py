"""
Analysis Pipeline — 3 aşamalı kademeli analiz motoru.

Step 1: Statik Analiz (Python, anında) → Smells + Severity + Skor
Step 2: AI Derin Analiz (AI çağrısı)  → Açıklama + Bulgular (kod yazmaz)
Step 3: AI Kod Düzeltme (AI çağrısı)  → Sadece düzeltilmiş tam C# kodu
"""

import asyncio
import json
import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

from analyzer import UnityAnalyzer
from report_engine import ReportEngine
from prompts import (
    SYSTEM_PROMPT, PROMPT_DEEP_ANALYSIS, PROMPT_CODE_FIX,
    get_language_instr, get_relevant_rules
)

logger = logging.getLogger(__name__)


# ─── VERİ MODELLERİ ───
@dataclass
class StepResult:
    """Tek bir pipeline adımının sonucunu tutar."""
    step_name: str
    success: bool
    duration_ms: int
    output: Any = None
    error: Optional[str] = None


@dataclass
class PipelineResult:
    """Pipeline'ın tam sonucunu tutar."""
    # Adım sonuçları
    step1_static: Optional[StepResult] = None
    step2_analysis: Optional[StepResult] = None
    step3_code_fix: Optional[StepResult] = None

    # Birleşik rapor
    score: float = 10.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    severity_counts: Dict[str, int] = field(default_factory=dict)
    total_smells: int = 0
    summary: str = ""
    total_duration_ms: int = 0

    # Final çıktılara
    analysis_text: str = ""   # Step 2 çıktısı (açıklama)
    fixed_code: str = ""      # Step 3 çıktısı (düzeltilmiş kod)
    combined_response: str = ""  # Frontend'e gösterilecek birleşik metin

    def to_dict(self) -> Dict[str, Any]:
        """Frontend'e gönderilecek pipeline bilgisini döndürür."""
        return {
            "score": self.score,
            "score_breakdown": self.score_breakdown,
            "severity_counts": self.severity_counts,
            "total_smells": self.total_smells,
            "summary": self.summary,
            "total_duration_ms": self.total_duration_ms,
            "steps": {
                "step1": {
                    "name": "Statik Analiz",
                    "duration_ms": self.step1_static.duration_ms if self.step1_static else 0,
                    "success": self.step1_static.success if self.step1_static else False,
                },
                "step2": {
                    "name": "Derin AI Analizi",
                    "duration_ms": self.step2_analysis.duration_ms if self.step2_analysis else 0,
                    "success": self.step2_analysis.success if self.step2_analysis else False,
                },
                "step3": {
                    "name": "Kod Düzeltme",
                    "duration_ms": self.step3_code_fix.duration_ms if self.step3_code_fix else 0,
                    "success": self.step3_code_fix.success if self.step3_code_fix else False,
                },
            },
        }


class AnalysisPipeline:
    """
    3 aşamalı kademeli analiz pipeline'ı.
    Her adım bir öncekinin çıktısını girdi olarak kullanır (zincir etkisi).
    """

    def __init__(
        self,
        code: str,
        provider: Any,
        language: str = "tr",
        context: str = "",
        learned_rules: str = "",
        user_message: str = "",
        provider_type: str = "groq",
    ):
        self.code = code
        self.provider = provider
        self.language = language
        self.context = context
        self.learned_rules = learned_rules
        self.user_message = user_message or code
        self.provider_type = provider_type

        # Pipeline dahili state
        self._smells: List[Dict] = []
        self._report: Dict[str, Any] = {}
        self._analysis_text: str = ""
        self._result = PipelineResult()

    async def run(self) -> PipelineResult:
        """Pipeline'ın 3 adımını sırayla çalıştırır."""
        pipeline_start = time.time()

        logger.info("🔗 Pipeline başlatılıyor...")

        # ─── STEP 1: Statik Analiz (Python, anında) ───
        self._result.step1_static = self._step1_static_analysis()

        # ─── STEP 2: AI Derin Analiz ───
        self._result.step2_analysis = await self._step2_deep_analysis()

        # ─── STEP 3: AI Kod Düzeltme ───
        self._result.step3_code_fix = await self._step3_code_fix()

        # ─── Sonuçları birleştir ───
        self._finalize(pipeline_start)

        logger.info(
            f"✅ Pipeline tamamlandı — Skor: {self._result.score}/10, "
            f"Toplam: {self._result.total_duration_ms}ms "
            f"(S1: {self._result.step1_static.duration_ms}ms, "
            f"S2: {self._result.step2_analysis.duration_ms}ms, "
            f"S3: {self._result.step3_code_fix.duration_ms}ms)"
        )

        return self._result

    # ═══════════════════════════════════════════════════════════
    # STEP 1: Statik Analiz (Python, AI'dan bağımsız, anında)
    # ═══════════════════════════════════════════════════════════
    def _step1_static_analysis(self) -> StepResult:
        """Python kural motoruyla statik analiz + rapor üretimi."""
        start = time.time()
        try:
            # Statik analiz çalıştır
            analyzer = UnityAnalyzer(self.code)
            raw_result = analyzer.analyze()
            self._smells = raw_result.get("smells", [])

            # Rapor motoru ile puanlama
            self._report = ReportEngine.build_report(
                self._smells,
                duration_ms=int((time.time() - start) * 1000)
            )

            # PipelineResult'a aktar
            self._result.score = self._report["score"]
            self._result.score_breakdown = self._report["score_breakdown"]
            self._result.severity_counts = self._report["severity_counts"]
            self._result.total_smells = self._report["total_smells"]
            self._result.summary = self._report["summary"]

            duration = int((time.time() - start) * 1000)
            logger.info(f"  Step 1 ✅ Statik Analiz — {len(self._smells)} bulgu, {duration}ms")

            return StepResult(
                step_name="static_analysis",
                success=True,
                duration_ms=duration,
                output=raw_result,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 1 ❌ Hata: {e}")
            return StepResult(
                step_name="static_analysis",
                success=False,
                duration_ms=duration,
                error=str(e),
            )

    # ═══════════════════════════════════════════════════════════
    # STEP 2: AI Derin Analiz (sadece açıklama, kod yazmaz)
    # ═══════════════════════════════════════════════════════════
    async def _step2_deep_analysis(self) -> StepResult:
        """AI'ya sadece açıklama ve öğretmenlik yaptırır."""
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

            # AI çağrısı (Ollama veya Cloud)
            if self.provider_type == "ollama":
                self._analysis_text = await self._call_ollama(prompt)
            else:
                self._analysis_text = await asyncio.to_thread(
                    self.provider.analyze_code, prompt
                )

            self._result.analysis_text = self._analysis_text

            duration = int((time.time() - start) * 1000)
            logger.info(f"  Step 2 ✅ Derin Analiz — {len(self._analysis_text)} karakter, {duration}ms")

            return StepResult(
                step_name="deep_analysis",
                success=True,
                duration_ms=duration,
                output=self._analysis_text,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 2 ❌ Hata: {e}")
            self._analysis_text = f"❌ AI Analiz Hatası: {str(e)}"
            self._result.analysis_text = self._analysis_text
            return StepResult(
                step_name="deep_analysis",
                success=False,
                duration_ms=duration,
                error=str(e),
            )

    # ═══════════════════════════════════════════════════════════
    # STEP 3: AI Kod Düzeltme (sadece kod, açıklama yapmaz)
    # ═══════════════════════════════════════════════════════════
    async def _step3_code_fix(self) -> StepResult:
        """AI'ya sadece düzeltilmiş tam C# kodu ürettiriri."""
        start = time.time()
        try:
            lang_instr = get_language_instr(self.language)
            rules_str = get_relevant_rules(self.code)

            # Step 2'nin analizini özetle
            analysis_summary = self._analysis_text[:1500] if self._analysis_text else "Analiz yapılamadı."

            prompt = PROMPT_CODE_FIX.format(
                lang_instr=lang_instr,
                original_code=self.code,
                analysis_summary=analysis_summary,
                rules=rules_str,
                learned_rules=self._format_learned_rules(),
            )

            # AI çağrısı
            if self.provider_type == "ollama":
                fixed_code = await self._call_ollama(prompt)
            else:
                fixed_code = await asyncio.to_thread(
                    self.provider.analyze_code, prompt
                )

            self._result.fixed_code = fixed_code

            duration = int((time.time() - start) * 1000)
            logger.info(f"  Step 3 ✅ Kod Düzeltme — {len(fixed_code)} karakter, {duration}ms")

            return StepResult(
                step_name="code_fix",
                success=True,
                duration_ms=duration,
                output=fixed_code,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 3 ❌ Hata: {e}")
            self._result.fixed_code = ""
            return StepResult(
                step_name="code_fix",
                success=False,
                duration_ms=duration,
                error=str(e),
            )

    # ═══════════════════════════════════════════════════════════
    # YARDIMCI METODLAR
    # ═══════════════════════════════════════════════════════════
    async def _call_ollama(self, prompt: str) -> str:
        """Ollama'ya senkron çağrıyı async wrapper ile yapar."""
        import ollama

        model_name = getattr(self.provider, "model_name", "qwen2.5-coder:7b")

        def _sync_call():
            response = ollama.chat(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            return response["message"]["content"]

        return await asyncio.wait_for(
            asyncio.to_thread(_sync_call), timeout=120
        )

    def _format_learned_rules(self) -> str:
        """Öğrenilmiş kuralları prompt'a enjekte edilecek formata çevirir."""
        if not self.learned_rules:
            return ""
        return f"\n[KULLANICIDAN ÖĞRENILEN KURALLAR]\n{self.learned_rules}\n"

    def _finalize(self, pipeline_start: float):
        """Pipeline sonuçlarını birleştirir ve final çıktı üretir."""
        total = int((time.time() - pipeline_start) * 1000)
        self._result.total_duration_ms = total

        # Step 2 + Step 3 çıktılarını birleştir
        parts = []
        if self._result.analysis_text:
            parts.append(self._result.analysis_text)
        if self._result.fixed_code:
            parts.append(self._result.fixed_code)

        self._result.combined_response = "\n\n".join(parts)
