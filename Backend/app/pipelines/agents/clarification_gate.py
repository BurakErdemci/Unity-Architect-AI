"""
ClarificationGateAgent — Multi-Agent pipeline'ının önüne konulan hafif bir ön-kontrol ajanı.

Görev:
  - Kullanıcının isteğini analiz eder.
  - Yeterli detay varsa → PROCEED (pipeline devam eder).
  - Eksik kritik bilgi varsa → NEEDS_CLARIFICATION (pipeline durur, sorular kullanıcıya döner).

Tasarım kararları:
  - max_tokens=400: Sadece JSON çıktısı üretir, fazlasına gerek yok.
  - Önceki sohbet context'i de verilir: Kullanıcı zaten cevap verdiyse tekrar soru sorulmaz.
  - Sadece generation mode'da çalışır (kod analizi için gerek yok).
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Tek bir kod üretim isteği için yeterli sayılan minimum bilgiler:
#   - Ne yapılacak (zorunlu — kullanıcı zaten yazdı)
#   - Platform (2D/3D) — hareket/fizik/kamera sistemi gerektiren isteklerde kritik
#   - Veri saklama — inventory/save/quest gibi sistemlerde kritik
# Basit isteklerde (ör: "timer yaz", "singleton yaz") bunlar gerekmez.

_GATE_PROMPT = """Sen bir Unity C# proje asistanısın. Görevin kullanıcının kod üretim isteğini analiz edip yeterli mi yetersiz mi olduğuna karar vermektir.

[ÖNCEKİ SOHBET]
{context}

[KULLANICI İSTEĞİ]
{user_prompt}

[KARAR KURALLARI]

PROCEED ver (kod üretilebilir) eğer:
- İstek basit ve tek parça bir sistemse (ör: timer, singleton, coroutine, basit movement)
- Platform (2D/3D) zaten belirtilmişse
- Önceki sohbette bu bilgiler zaten verilmişse
- Kullanıcı "devam et", "evet", "yap" gibi bir onay verdiyse

NEEDS_CLARIFICATION ver (soru sor) eğer:
- İstek büyük/karmaşık bir sistem ama kritik bilgiler eksikse (ör: "RPG sistemi", "inventory", "quest sistemi", "diyalog sistemi", "save/load", "karakter kontrolcüsü")
- Platform belirsizse VE fizik/hareket/kamera gerektiren bir sistem isteniyorsa
- Veri saklama yöntemi belirsizse VE sistem veri gerektiriyorsa (inventory, save/load)
- Birden fazla farklı yoruma açık bir istek varsa

[KRİTİK KURAL — ASLA İHLAL ETME]
Kullanıcı bir bilgiyi zaten belirttiyse o konuda ASLA soru sorma. Örnekler:
- "gerçek zamanlı" / "real-time" / "action" → savaş tipi sorma
- "2D" veya "3D" geçiyorsa → platform sorma
- "PlayerPrefs" / "JSON" / "binary" geçiyorsa → veri saklama sorma
- "UI dahil" / "sadece backend" geçiyorsa → UI sorama
Prompta bak, orada ne var ne yok listele, SADECE gerçekten eksik olanları sor.

[ÖNEMLİ]
- Basit isteklerde (tek script, tek davranış) ASLA soru sorma — direkt PROCEED ver.
- Soru sayısı maksimum 3 olsun, hepsini tek seferde sor.
- Sadece GERÇEKTEN eksik olan bilgileri sor, prompt'ta geçen detayları tekrarlama.

[ÇIKTI FORMATI — SADECE JSON, BAŞKA HİÇBİR ŞEY YAZMA]

PROCEED durumu:
{{"status": "PROCEED"}}

NEEDS_CLARIFICATION durumu:
{{"status": "NEEDS_CLARIFICATION", "questions": ["Soru 1?", "Soru 2?", "Soru 3?"]}}
"""

_CLARIFICATION_HEADER = """📋 **Sistemi en iyi şekilde tasarlayabilmem için birkaç hızlı sorum var:**

"""

_CLARIFICATION_FOOTER = """
> Cevapladıktan sonra hemen kodu üretmeye başlayacağım! 🚀"""


class ClarificationGateAgent:
    """
    Multi-Agent CodeGenerationPipeline'ının önünde çalışan hafif ön-kontrol ajanı.
    Kullanıcıdan yeterli detay alınmadan pipeline'ı başlatmaz.
    """

    def __init__(self, provider: Any):
        self.provider = provider

    def check(self, user_prompt: str, context: str = "") -> dict:
        """
        İsteği analiz eder.
        Döndürür:
          {"status": "PROCEED"}
          veya
          {"status": "NEEDS_CLARIFICATION", "questions": [...]}
        """
        prompt = _GATE_PROMPT.format(
            user_prompt=user_prompt,
            context=context or "Yeni sohbet — önceki bağlam yok.",
        )

        try:
            raw = self.provider.analyze_code(prompt, max_tokens=400)
            result = self._parse(raw)
            logger.info(f"[ClarificationGate] Karar: {result.get('status')} | Prompt: {user_prompt[:60]}...")
            return result
        except Exception as exc:
            # Gate hata verirse pipeline'ı durdurma — PROCEED ile devam et
            logger.warning(f"[ClarificationGate] Hata (PROCEED ile devam): {exc}")
            return {"status": "PROCEED"}

    def format_questions(self, questions: list) -> str:
        """Soruları kullanıcıya gösterilecek formata dönüştürür."""
        lines = [_CLARIFICATION_HEADER]
        for i, q in enumerate(questions, 1):
            lines.append(f"**{i}.** {q}")
        lines.append(_CLARIFICATION_FOOTER)
        return "\n".join(lines)

    def _parse(self, raw: str) -> dict:
        """LLM çıktısından JSON'u güvenli şekilde çıkarır."""
        # Markdown code block varsa soy
        clean = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

        # { ile başlayan kısmı bul
        brace = clean.find("{")
        if brace >= 0:
            clean = clean[brace:]

        try:
            parsed = json.loads(clean)
            if parsed.get("status") in ("PROCEED", "NEEDS_CLARIFICATION"):
                return parsed
        except (json.JSONDecodeError, AttributeError):
            pass

        # Fallback: metin içinde PROCEED geçiyorsa güvenli geç
        if "PROCEED" in raw:
            return {"status": "PROCEED"}

        logger.warning(f"[ClarificationGate] JSON parse başarısız, PROCEED ile devam: {raw[:150]}")
        return {"status": "PROCEED"}
