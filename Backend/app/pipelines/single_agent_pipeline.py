"""
Single Agent Pipeline (Partner Mode) — Yalın 2 aşamalı analiz.

Aşamalar:
  1. Statik Analiz (Python, anında)
  2. AI Analiz + Düzeltme (tek çağrıda hem sorunu anlat hem kodu düzelt)

Eski 4-step pipeline (analiz → fix → critique → retry) kaldırıldı.
Kullanıcı puan/skor istemiyor, partner gibi konuş ve düzelt.
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
    SYSTEM_PROMPT,
    get_language_instr, get_relevant_rules
)
from .base import BasePipeline, StepResult

logger = logging.getLogger(__name__)


class SingleAgentPipeline(BasePipeline):
    """
    Partner-mode 2 aşamalı pipeline: Statik → AI (analiz + fix tek çağrıda).
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._smells: List[Dict] = []
        self._report: Dict[str, Any] = {}

    async def run(self):
        pipeline_start = time.time()
        logger.info("🔗 SingleAgent Partner Pipeline başlatılıyor...")

        # ─── STEP 1: Statik Analiz ───
        self._result.step1_static = self._step1_static_analysis()

        # ─── STEP 2: AI Analiz + Fix (Tek Çağrı) ───
        self._result.step2_analysis = await self._step2_analyze_and_fix()

        # ─── Sonuçları birleştir ───
        self._finalize(pipeline_start)

        logger.info(
            f"✅ SingleAgent Partner tamamlandı — Toplam: {self._result.total_duration_ms}ms"
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
    # STEP 2: AI Analiz + Fix (TEK ÇAĞRI)
    # ═══════════════════════════════════════════════════════════
    async def _step2_analyze_and_fix(self) -> StepResult:
        if self.progress_callback: self.progress_callback("step2", "in-progress")
        start = time.time()
        try:
            lang_instr = get_language_instr(self.language)
            rules_str = get_relevant_rules(self.code)
            smells_str = json.dumps(self._smells, ensure_ascii=False) if self._smells else "Statik analizde sorun bulunamadı."
            learned = self._format_learned_rules()

            prompt = f"""{SYSTEM_PROMPT}

{lang_instr}

[GÖREV]
Kullanıcının gönderdiği Unity C# kodunu incele ve düzelt.
Tek yanıtta hem sorunları kısaca açıkla hem düzeltilmiş kodu ver.

[ÖNCEKİ SOHBET]
{self.context or "Yeni sohbet."}

[KULLANICI MESAJI]
{self.user_message}

[STATİK ANALİZ BULGULARI]
{smells_str}

[KONTROL EDİLECEK KURALLAR]
{rules_str}

{learned}

[FORMAT]
1. Kodda bulduğun en kritik 1-3 sorunu kısaca listele (her biri 1 cümle).
2. Ardından düzeltilmiş tam kodu ver:

```csharp
// düzeltilmiş kod
```

Puan verme, essay yazma, emoji bombardımanı yapma. Kısa ve öz ol."""

            response = await self._call_ai(prompt)
            self._result.analysis_text = response

            # Kodun içinden düzeltilmiş kısmı ayıkla
            fixed = self._extract_code(response)
            if fixed:
                self._result.fixed_code = fixed

            duration = int((time.time() - start) * 1000)
            logger.info(f"  Step 2 ✅ Analiz + Fix — {duration}ms")
            if self.progress_callback: self.progress_callback("step2", "completed", duration)
            return StepResult(step_name="analyze_and_fix", success=True, duration_ms=duration, output=response)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 2 ❌ Hata: {e}")
            if self.progress_callback: self.progress_callback("step2", "failed", duration)
            return StepResult(step_name="analyze_and_fix", success=False, duration_ms=duration, error=str(e))

    # ═══════════════════════════════════════════════════════════
    # YARDIMCI METODLAR
    # ═══════════════════════════════════════════════════════════
    _TOKEN_LIMITS = {
        "groq": 32000,
        "openai": 16384,
        "openrouter": 16384,
        "deepseek": 16384,
        "anthropic": 16384,
        "google": 65536,
    }

    async def _call_ai(self, prompt: str, max_tokens: int = None) -> str:
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

    def _extract_code(self, text: str) -> str:
        """Markdown içerisinden sadece C# kodunu çıkarır."""
        if not text:
            return ""

        # Normal kapalı blok
        match = re.search(r'```(?:csharp|cs)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Truncated blok
        match_open = re.search(r'```(?:csharp|cs)?\s*(.*)', text, re.DOTALL | re.IGNORECASE)
        if match_open:
            code = match_open.group(1).strip()
            code = re.sub(r'```\s*$', '', code).strip()
            if code:
                return code

        return ""

    def _format_learned_rules(self) -> str:
        if not self.learned_rules:
            return ""
        return f"\n[KULLANICIDAN ÖĞRENİLEN KURALLAR]\n{self.learned_rules}\n"

    def _finalize(self, pipeline_start: float):
        total = int((time.time() - pipeline_start) * 1000)
        self._result.total_duration_ms = total

        # AI yanıtı zaten hem analiz hem kodu içeriyor
        if self._result.analysis_text:
            self._result.combined_response = self._result.analysis_text
        else:
            self._result.combined_response = "❌ Analiz yapılamadı."
