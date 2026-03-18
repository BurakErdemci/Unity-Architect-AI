import logging
import asyncio
from typing import Any

from pipelines.base import BasePipeline, PipelineResult, StepResult
from pipelines.agents.architect_generation import ArchitectGenerationAgent
from pipelines.agents.coder_generation import CoderGenerationAgent
from prompts import get_language_instr, get_relevant_rules
from validator import ResponseValidator

logger = logging.getLogger(__name__)

class CodeGenerationPipeline(BasePipeline):
    """
    Sıfırdan kod üretmek için kullanılan Multi-Agent sistemi.
    1. Architect (Mimar): Kodu planlar
    2. Coder (Yazılımcı): Plana göre kodu üretir ve direkt olarak kullanıcıya sunar (puanlama veya şefik denetim olmadan)
    """
    
    def __init__(
        self,
        prompt: str,
        provider: Any,
        language: str = "tr",
        context: str = "",
        user_message: str = "",
        provider_type: str = "unknown"
    ):
        # Base constructor expects code, which is empty here
        super().__init__("", provider, language, context, "", user_message, provider_type)
        self.prompt = prompt # kullanıcının "Bana x yap" isteği
        
        # Ajanları başlat
        self.architect = ArchitectGenerationAgent(self.provider)
        self.coder = CoderGenerationAgent(self.provider)
        
    async def run(self) -> PipelineResult:
        logger.info("✨ CodeGenerationPipeline başlatılıyor...")
        
        # 1. Ortak Kuralları Topla (Statik analiz yapmıyoruz, ama kuralları bilelim)
        rules_str = get_relevant_rules(self.prompt)
        lang_instr = get_language_instr(self.language)
        
        # --- ADIM 1: ARCHITECT PLANLAMASI ---
        logger.info("  Step 1: Architect Planı oluşturuluyor...")
        plan = await asyncio.to_thread(
            self.architect.plan_architecture,
            self.prompt,
            lang_instr,
            rules_str
        )
        self._result.step2_analysis = StepResult("Mimari Plan", True, 0, plan)
        
        # --- ADIM 2: CODER KOD ÜRETİMİ (VE KULLANICIYA YANIT) ---
        logger.info("  Step 2: Coder Kodu üretiyor...")
        final_response = await asyncio.to_thread(
            self.coder.generate_code,
            self.prompt,
            plan,
            lang_instr,
            rules_str
        )
        
        # Regex vs ile C# kodu ayrıştırılabilir, Coder direkt metin + kod bastığı için
        # final_response zaten kullanıcıya gösterilecek nihai cevaptır.
        
        self._result.step3_code_fix = StepResult("Kod Üretimi", True, 0, final_response)
        
        # 3. Finalize
        self._result.analysis_text = final_response
        self._result.combined_response = final_response
        
        return self._result
