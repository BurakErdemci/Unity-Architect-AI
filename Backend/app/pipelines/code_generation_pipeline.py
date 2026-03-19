import logging
import re
import asyncio
from typing import Any

from pipelines.base import BasePipeline, PipelineResult, StepResult
from pipelines.agents.architect_generation import ArchitectGenerationAgent
from pipelines.agents.coder_generation import CoderGenerationAgent
from pipelines.agents.game_feel_agent import GameFeelAgent
from prompts import get_language_instr, get_relevant_rules
from validator import ResponseValidator

logger = logging.getLogger(__name__)

class CodeGenerationPipeline(BasePipeline):
    """
    Sıfırdan kod üretmek için kullanılan Multi-Agent sistemi.
    1. Architect (Mimar): Kodu planlar
    2. Coder (Yazılımcı): Plana göre kodu üretir
    3. Game Feel Agent (Sessiz): Kodu değerlendirir, düşük skorsa Coder'a geri gönderir
    """
    
    GAME_FEEL_THRESHOLD = 7.0  # Bu skorun altındaysa Coder tekrar yazar
    
    def __init__(
        self,
        prompt: str,
        provider: Any,
        language: str = "tr",
        context: str = "",
        user_message: str = "",
        provider_type: str = "unknown"
    ):
        super().__init__("", provider, language, context, "", user_message, provider_type)
        self.prompt = prompt
        
        # Ajanları başlat
        self.architect = ArchitectGenerationAgent(self.provider)
        self.coder = CoderGenerationAgent(self.provider)
        self.game_feel = GameFeelAgent(self.provider)
        
    async def run(self) -> PipelineResult:
        logger.info("✨ CodeGenerationPipeline başlatılıyor...")
        
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
        
        # --- ADIM 2: CODER + GAME FEEL SILENT LOOP ---
        MAX_ATTEMPTS = 2
        final_response = ""
        gf_score = 10.0  # Varsayılan: yeterli
        gf_result = {}
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if attempt == 1:
                logger.info("  Step 2: Coder Kodu üretiyor...")
                current_plan = plan
            else:
                logger.info(f"  Step 2 (Retry): 🎮 Game Feel düşük ({gf_score:.1f}), Coder tekrar yazıyor...")
                # Game Feel feedback'ini plana ekle
                suggestions = "\n".join(f"- {s}" for s in gf_result.get("suggestions", []))
                movement = gf_result.get("movement", {})
                combat = gf_result.get("combat", {})
                physics = gf_result.get("physics", {})
                
                game_feel_feedback = f"""

[🎮 OYUN HİSSİYATI GERİ BİLDİRİMİ — BU SORUNLARI DÜZELT]
Önceki kodun oyun hissiyatı puanı: {gf_score:.1f}/10 (Yetersiz!)

Hareket: {movement.get('verdict', '?')} — {movement.get('detail', '')}
Combat: {combat.get('verdict', '?')} — {combat.get('detail', '')}
Fizik: {physics.get('verdict', '?')} — {physics.get('detail', '')}

Somut düzeltme talimatları:
{suggestions}

ÖNEMLİ: Bu sefer OYUN HİSSİYATINI (Game Feel) ön plana koy!
- Hareket: rb.velocity veya CharacterController kullan, AddForce KULLANMA
- Düşüş: Gravity multiplier ekle (havada asılı kalmasın)
- Combat: Input anında tepki versin, gecikme olmasın
- Oyuncu kontrolü keskin ve tatmin edici (snappy) olmalı
"""
                current_plan = plan + game_feel_feedback

            final_response = await asyncio.to_thread(
                self.coder.generate_code,
                self.prompt,
                current_plan,
                lang_instr,
                rules_str,
                max_tokens=8192 # Üretim için yüksek limit
            )
            
            # Game Feel değerlendirmesi (sessiz — kullanıcıya gösterilmez)
            code_block = self._extract_csharp(final_response)
            if code_block and len(code_block.strip()) > 20 and attempt < MAX_ATTEMPTS:
                logger.info(f"  [Game Feel Check] Deneme {attempt}: Sessiz değerlendirme...")
                gf_result = await asyncio.to_thread(
                    self.game_feel.evaluate,
                    code=code_block,
                    context=self.prompt
                )
                gf_score = gf_result.get("game_feel_score", 10.0)
                logger.info(f"  [Game Feel Check] Skor: {gf_score:.1f}/10 (Eşik: {self.GAME_FEEL_THRESHOLD})")
                
                if gf_score >= self.GAME_FEEL_THRESHOLD:
                    logger.info(f"  ✅ Game Feel yeterli, loop sonlandırıldı (deneme {attempt})")
                    break
                # else: döngü devam eder, Coder tekrar yazar
            else:
                break
        
        self._result.step3_code_fix = StepResult("Kod Üretimi", True, 0, final_response)
        
        # Finalize — kullanıcıya sadece temiz kod gösterilir
        self._result.analysis_text = final_response
        self._result.combined_response = final_response
        
        return self._result

    def _extract_csharp(self, text: str) -> str:
        """Markdown'daki C# kod bloğunu çıkarır."""
        if not text:
            return ""
        match = re.search(r'```(?:csharp|cs)\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""
