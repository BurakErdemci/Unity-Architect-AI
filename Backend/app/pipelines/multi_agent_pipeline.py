import asyncio
import json
import time
import logging
import re
from typing import Dict, Any, List

from analyzer import UnityAnalyzer
from report_engine import ReportEngine
from prompts import get_language_instr, get_relevant_rules

from .base import BasePipeline, StepResult
from .agents import OrchestratorAgent, UnityExpertAgent, CriticAgent

logger = logging.getLogger(__name__)

class MultiAgentPipeline(BasePipeline):
    """
    Tier 2: Multi-Agent Mimarisi. (Sadece Claude API için)
    Orchestrator planlar -> Expert yazar -> Critic denetler.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._smells: List[Dict] = []
        
        # Ajanları başlat (Hepsi aynı Claude provider'ını kullanır)
        self.orchestrator = OrchestratorAgent(self.provider)
        self.expert = UnityExpertAgent(self.provider)
        self.critic = CriticAgent(self.provider)

    async def run(self):
        pipeline_start = time.time()
        logger.info("🔗 Multi-Agent Pipeline başlatılıyor (Tier 2)...")

        # ─── STEP 1: Statik Analiz (Python) ───
        self._result.step1_static = self._step1_static_analysis()

        # ─── STEP 2: Multi-Agent İş Akışı ───
        logger.info("  [Multi-Agent] Ajan takımı devreye giriyor...")
        await self._run_agent_team()

        # ─── Sonuçları birleştir ───
        self._finalize(pipeline_start)

        logger.info(
            f"✅ Multi-Agent Pipeline tamamlandı — Skor: {self._result.score}/10, "
            f"Toplam: {self._result.total_duration_ms}ms"
        )
        return self._result

    def _step1_static_analysis(self) -> StepResult:
        start = time.time()
        try:
            analyzer = UnityAnalyzer(self.code)
            raw_result = analyzer.analyze()
            self._smells = raw_result.get("smells", [])

            # Statik rapordan sadece severity vs almak için ReportEngine kullanıyoruz.
            # Normalde Critic'in verdiği skoru ezeceğiz.
            report = ReportEngine.build_report(self._smells, duration_ms=int((time.time() - start) * 1000))

            self._result.severity_counts = report["severity_counts"]
            self._result.total_smells = report["total_smells"]
            
            duration = int((time.time() - start) * 1000)
            logger.info(f"  Step 1 ✅ Statik Analiz — {len(self._smells)} bulgu, {duration}ms")

            return StepResult(step_name="static_analysis", success=True, duration_ms=duration, output=raw_result)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.error(f"  Step 1 ❌ Hata: {e}")
            return StepResult(step_name="static_analysis", success=False, duration_ms=duration, error=str(e))

    async def _run_agent_team(self):
        start = time.time()
        lang_instr = get_language_instr(self.language)
        rules_str = get_relevant_rules(self.code)
        learned_rules_str = self._format_learned_rules()
        smells_str = json.dumps(self._smells, ensure_ascii=False) if self._smells else "Sorun yok."

        # 1. Orchestrator Plan yapar
        plan_task = asyncio.to_thread(
            self.orchestrator.plan_task, 
            code=self.code, 
            smells=smells_str, 
            user_message=self.user_message
        )
        plan = await plan_task
        
        # Adım 2 süresini kaydet (Frontend'e planı göndermiyoruz, sadece log ve data olarak tutuyoruz)
        self._result.step2_analysis = StepResult("orchestrator_plan", True, int((time.time() - start) * 1000), plan)

        # 2. Expert kodu yazar
        expert_start = time.time()
        expert_task = asyncio.to_thread(
            self.expert.fix_code,
            code=self.code,
            plan=plan,
            lang_instr=lang_instr,
            rules=rules_str,
            learned_rules=learned_rules_str
        )
        fixed_code_raw = await expert_task
        
        # Kodu temizle
        fixed_code = self._extract_code(fixed_code_raw)
        self._result.fixed_code = fixed_code

        # 3. Critic puanlar
        critic_task = asyncio.to_thread(
            self.critic.evaluate,
            original_code=self.code,
            fixed_code=fixed_code,
            plan=plan,
            lang_instr=lang_instr
        )
        critic_result = await critic_task
        
        # Critic'in sonuçlarını pipeline'a yansıt
        self._result.score = critic_result.get("score", self._result.score)
        self._result.summary = critic_result.get("review_message", "Eleştiri yok.")
        
        # Critic mesajını ana analiz metni olarak ekle (Orchestrator planı gizli kalır)
        self._result.analysis_text = f"**⚖️ KOD DENETİM RAPORU:**\n\n{self._result.summary}\n\n**Puan:** {self._result.score}/10.0"
        
        # Step 3 sonucunu kaydet
        self._result.step3_code_fix = StepResult("expert_and_critic", True, int((time.time() - expert_start) * 1000), critic_result)

    def _extract_code(self, text: str) -> str:
        """Markdown içerisinden sadece C# kodunu çıkarır"""
        if not text: return ""
        match = re.search(r'```(?:csharp|cs)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _format_learned_rules(self) -> str:
        if not self.learned_rules: return ""
        return f"\n[KULLANICIDAN ÖĞRENILEN KURALLAR]\n{self.learned_rules}\n"

    def _finalize(self, pipeline_start: float):
        total = int((time.time() - pipeline_start) * 1000)
        self._result.total_duration_ms = total

        parts = []
        if self._result.analysis_text: parts.append(self._result.analysis_text)
        if self._result.fixed_code: 
            # Düzeltilmiş kodu UI'ın kod bloğunda (Kopyala butonuyla) gösterebilmesi için Markdown ile sarıyoruz
            parts.append(f"```csharp\n{self._result.fixed_code}\n```")
        self._result.combined_response = "\n\n".join(parts)
