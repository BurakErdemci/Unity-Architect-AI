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
from .agents import OrchestratorAgent, UnityExpertAgent, CriticAgent, GameFeelAgent

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
        self.game_feel = GameFeelAgent(self.provider)

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
        
        # Adım 2 süresini kaydet
        self._result.step2_analysis = StepResult("orchestrator_plan", True, int((time.time() - start) * 1000), plan)

        # ─── ITERATIVE FIX LOOP (Max 2 döngü) ───
        MAX_RETRIES = 2
        fixed_code = ""
        critic_result = {}
        
        for attempt in range(1, MAX_RETRIES + 1):
            expert_start = time.time()
            
            if attempt == 1:
                # İlk deneme: Normal Expert çalışması
                logger.info(f"  [Loop {attempt}/{MAX_RETRIES}] Expert kodu yazıyor...")
                expert_task = asyncio.to_thread(
                    self.expert.fix_code,
                    code=self.code,
                    plan=plan,
                    lang_instr=lang_instr,
                    rules=rules_str,
                    learned_rules=learned_rules_str
                )
            else:
                # 2. deneme: Critic feedback'i ile birlikte tekrar yaz
                logger.info(f"  [Loop {attempt}/{MAX_RETRIES}] Critic beğenmedi (skor: {critic_result.get('score', '?')}), Expert tekrar yazıyor...")
                critic_feedback = critic_result.get("review_message", "Kod kalitesi yetersiz.")
                retry_prompt_extra = f"""
[ÖNCEKİ DENEME ELEŞTİRİSİ — BU HATALARI DÜZELT]
Critic puanı: {critic_result.get('score', '?')}/10
Eleştiri: {critic_feedback}

Lütfen yukarıdaki eleştirileri dikkate alarak kodu TAMAMEN yeniden yaz. 
Önceki hataları tekrarlama!"""
                
                expert_task = asyncio.to_thread(
                    self.expert.fix_code,
                    code=self.code,
                    plan=plan + retry_prompt_extra,
                    lang_instr=lang_instr,
                    rules=rules_str,
                    learned_rules=learned_rules_str
                )
            
            fixed_code_raw = await expert_task
            fixed_code = self._extract_code(fixed_code_raw)
            self._result.fixed_code = fixed_code

            # Critic puanlar
            critic_task = asyncio.to_thread(
                self.critic.evaluate,
                original_code=self.code,
                fixed_code=fixed_code,
                plan=plan,
                lang_instr=lang_instr
            )
            critic_result = await critic_task
            
            score = critic_result.get("score", 0)
            logger.info(f"  [Loop {attempt}/{MAX_RETRIES}] Critic puanı: {score}/10")
            
            # Skor yeterli (>= 8.0) ise döngüyü kır
            if score >= 8.0:
                logger.info(f"  ✅ Kod kalitesi yeterli, loop sonlandırıldı (deneme {attempt})")
                break
            elif attempt < MAX_RETRIES:
                logger.info(f"  🔄 Skor düşük ({score}), tekrar deneniyor...")
        
        # Critic'in sonuçlarını pipeline'a yansıt
        self._result.score = critic_result.get("score", self._result.score)
        self._result.summary = critic_result.get("review_message", "Eleştiri yok.")
        
        # Loop bilgisini rapora ekle
        loop_info = f"(🔄 {attempt} deneme)" if attempt > 1 else ""
        self._result.analysis_text = f"**⚖️ KOD DENETİM RAPORU {loop_info}:**\n\n{self._result.summary}\n\n**Puan:** {self._result.score}/10.0"
        
        # Step 3 sonucunu kaydet
        self._result.step3_code_fix = StepResult("expert_and_critic", True, int((time.time() - expert_start) * 1000), critic_result)

        # ─── STEP 4: GAME FEEL ANALİZİ ───
        if fixed_code and len(fixed_code.strip()) > 20:
            logger.info("  [Multi-Agent] 🎮 Game Feel analizi başlatılıyor...")
            game_feel_task = asyncio.to_thread(
                self.game_feel.evaluate,
                code=fixed_code,
                context=self.user_message
            )
            self._game_feel_result = await game_feel_task
            
            # Game Feel skorunu da iterative loop'a dahil et
            gf_score = self._game_feel_result.get("game_feel_score", -1)
            if gf_score >= 0:
                game_feel_text = self.game_feel.format_for_ui(self._game_feel_result)
                self._result.analysis_text += game_feel_text
        else:
            self._game_feel_result = None

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
