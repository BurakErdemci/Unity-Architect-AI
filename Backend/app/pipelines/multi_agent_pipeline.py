import asyncio
import json
import time
import logging
import re
from typing import Dict, List

from analyzer import UnityAnalyzer
from report_engine import ReportEngine
from prompts import get_language_instr, get_relevant_rules

from .base import BasePipeline, StepResult
from .agents import OrchestratorAgent, UnityExpertAgent, CriticAgent, GameFeelAgent

logger = logging.getLogger(__name__)

class MultiAgentPipeline(BasePipeline):
    """
    Multi-Agent Pipeline — Toggle ON modu.
    Architect planlar → Expert yazar → Critic + GameFeel paralel denetler.
    """
    def __init__(self, *args, coding_provider=None, coding_provider_type: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._smells: List[Dict] = []

        _expert_provider = coding_provider if coding_provider else self.provider
        _coder_type = coding_provider_type or self.provider_type

        self.orchestrator = OrchestratorAgent(self.provider)
        self.expert = UnityExpertAgent(_expert_provider)
        self.critic = CriticAgent(_expert_provider)
        self.game_feel = GameFeelAgent(self.provider)

        if coding_provider:
            logger.info(f"[MultiAgent] Hybrid: Architect+GameFeel={self.provider_type}, Expert+Critic={_coder_type}")

    async def run(self):
        pipeline_start = time.time()
        logger.info("🔗 Multi-Agent Pipeline başlatılıyor...")

        self._result.step1_static = self._step1_static_analysis()
        await self._run_agent_team()
        self._finalize(pipeline_start)

        logger.info(f"✅ Multi-Agent Pipeline tamamlandı — {self._result.total_duration_ms}ms")
        return self._result

    def _step1_static_analysis(self) -> StepResult:
        start = time.time()
        try:
            analyzer = UnityAnalyzer(self.code)
            raw_result = analyzer.analyze()
            self._smells = raw_result.get("smells", [])

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

        # 1. Architect planlar
        if self.progress_callback:
            self.progress_callback("step1", "in-progress")

        plan = await asyncio.to_thread(
            self.orchestrator.plan_task,
            code=self.code,
            smells=smells_str,
            user_message=self.user_message
        )
        self._result.step2_analysis = StepResult("architect_plan", True, int((time.time() - start) * 1000), plan)

        if self.progress_callback:
            self.progress_callback("step1", "completed")
            self.progress_callback("step2", "in-progress")

        # 2. Expert kodu yazar
        fixed_code_raw = await asyncio.to_thread(
            self.expert.fix_code,
            code=self.code,
            plan=plan,
            lang_instr=lang_instr,
            rules=rules_str,
            learned_rules=learned_rules_str,
            max_tokens=8192
        )
        fixed_code = self._extract_code(fixed_code_raw)
        self._result.fixed_code = fixed_code

        if self.progress_callback:
            self.progress_callback("step2", "completed")
            self.progress_callback("step3", "in-progress")

        # 3. Critic + GameFeel paralel denetler
        critic_task = asyncio.to_thread(
            self.critic.evaluate,
            original_code=self.code,
            fixed_code=fixed_code,
            plan=plan,
            lang_instr=lang_instr
        )
        game_feel_task = asyncio.to_thread(
            self.game_feel.evaluate,
            code=fixed_code,
            context=self.user_message
        )

        critic_result, game_feel_result = await asyncio.gather(critic_task, game_feel_task)

        if self.progress_callback:
            self.progress_callback("step3", "completed")

        self._result.summary = critic_result.get("review_message", "")
        self._game_feel_result = game_feel_result
        self._result.step3_code_fix = StepResult(
            "critic_and_gamefeel", True,
            int((time.time() - start) * 1000),
            critic_result
        )

    def _extract_code(self, text: str) -> str:
        if not text:
            return ""
        match = re.search(r'```(?:csharp|cs)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _format_learned_rules(self) -> str:
        if not self.learned_rules:
            return ""
        return f"\n[KULLANICIDAN ÖĞRENILEN KURALLAR]\n{self.learned_rules}\n"

    def _finalize(self, pipeline_start: float):
        total = int((time.time() - pipeline_start) * 1000)
        self._result.total_duration_ms = total

        parts = []

        if self._result.summary:
            parts.append(self._result.summary)

        if self._result.fixed_code:
            parts.append(f"```csharp\n{self._result.fixed_code}\n```")

        game_feel_text = ""
        if hasattr(self, "_game_feel_result") and self._game_feel_result:
            game_feel_text = self.game_feel.format_for_ui(self._game_feel_result)
            if game_feel_text.strip():
                parts.append(f"**🎮 Oyun Hissiyatı:**\n{game_feel_text}")

        self._result.combined_response = "\n\n".join(parts)
