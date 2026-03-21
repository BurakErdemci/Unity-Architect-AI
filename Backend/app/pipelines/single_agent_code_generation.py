"""
SingleAgentCodeGenerationPipeline — Tek istek ile sıfırdan kod üretir.
Multi-Agent versiyonundan farklı olarak Architect + Coder + GameFeel ayrı ayrı çalışmaz.
Tek bir prompt'ta hem planlama hem kod üretimi hem de game feel kuralları birleştirilir.
"""
import logging
import re
import time
import asyncio
from typing import Any

from pipelines.base import BasePipeline, PipelineResult, StepResult
from prompts import get_language_instr, get_relevant_rules

logger = logging.getLogger(__name__)


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

    async def run(self) -> PipelineResult:
        logger.info("🔗 SingleAgent CodeGeneration Pipeline başlatılıyor...")

        rules_str = get_relevant_rules(self.prompt)
        lang_instr = get_language_instr(self.language)

        # --- TEK ADIM: KOD ÜRETİMİ ---
        if self.progress_callback:
            self.progress_callback("step1", "in-progress")

        start = time.time()

        combined_prompt = f"""Sen bir Unity C# kod üretici uzmanısın. Görevin SADECE sıfırdan kod yazmaktır.
ASLA analiz yapma, ASLA "Bulgular" veya "Performans" başlığı kullanma.
Sen bir KOD YAZARI'sın, bir analizci DEĞİLSİN.

{lang_instr}

[ÖNCEKİ SOHBET]
{self.context}

[KULLANICI İSTEĞİ]
{self.prompt}

[UYULMASI GEREKEN KURALLAR]
{rules_str}

[OYUN HİSSİYATI (GAME FEEL) — ÇOK ÖNEMLİ]
- Karakter hareketi: rb.velocity veya CharacterController kullan, AddForce KULLANMA
- Zıplama: Düşüş anında gravity multiplier artır (havada asılı kalmasın)
- Combat: Input anında tepki versin, gecikme olmasın
- Genel: Oyuncu kontrolü keskin ve tatmin edici (snappy) olmalı

[ÇIKTI FORMATI — SADECE BU ŞEKİLDE YAZ]
1. Tek bir cümle ile yaklaşımını özetle (Örn: "İşte rb.velocity tabanlı 2D hareket sisteminiz:")
2. HEMEN ```csharp bloğu ile TAM ve ÇALIŞAN kodu ver — yarım bırakma!
3. Kodun altına sadece "🎮 Editor Ayarları" başlığıyla 1-2 madde yaz

[YASAKLAR]
- ASLA "Bulgular", "Performans", "Puan" gibi analiz başlıkları KULLANMA
- ASLA kodu yarım bırakma veya "..." ile kısaltma
- ASLA uzun açıklama yapma — kısa ve öz ol"""

        try:
            response = await asyncio.to_thread(
                self.provider.analyze_code,
                combined_prompt
            )
        except Exception as e:
            logger.error(f"SingleAgent CodeGen hatası: {e}")
            response = f"❌ Kod üretimi başarısız: {str(e)}"

        duration = int((time.time() - start) * 1000)

        if self.progress_callback:
            self.progress_callback("step1", "completed", duration)

        logger.info(f"  Step 1 ✅ Kod Üretimi — {duration}ms")

        # Sonuçları ayarla
        self._result.step2_analysis = StepResult("Kod Üretimi", True, duration, response)
        self._result.analysis_text = response
        self._result.combined_response = response

        return self._result
