"""
Game Feel Agent — Oyun Hissiyatı Kontrolcüsü.

Bu ajan, üretilen veya düzeltilen kodun oyunda nasıl "hissettireceğini" değerlendirir.
Sadece kod kalitesi değil, OYUNCU DENEYİMİ odaklı puanlama yapar.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class GameFeelAgent:
    """
    Oyun hissiyatını puanlayan ajan.
    Critic'ten farklı olarak, kod kalitesine değil, oyuncunun kodu çalıştırdığında
    ne hissedeceğine odaklanır.
    """

    # ─── MAX TOKEN LİMİTİ ───
    MAX_RESPONSE_TOKENS = 1500

    GAME_FEEL_PROMPT = """# GÖREV: UNITY OYUN HİSSİYATI ANALİZİ (GAME FEEL SCORING)

Sen Unity oyun geliştirme konusunda 15+ yıl deneyimli bir Gameplay Programmer'sın.
Görevin, aşağıdaki Unity C# kodunu analiz ederek kodun oyun içinde nasıl "hissettireceğini" puanlamaktır.

[ÖNEMLİ] Bu bir "kod kalitesi" incelemesi DEĞİLDİR.
Temiz yazılmış ama oyunda berbat hissettiren bir kod 2/10 alabilir.

[NEGATİF KISITLAMALAR — İHLAL EDİLEMEZ]:
1. ASLA KOD YAZMA. Kod bloğu (```csharp```) üretme.
2. ASLA GİRİŞ/ÇIKIŞ CÜMLESİ YAZMA.
3. "suggestions" ve "summary" içinde KOD BLOKLARI KULLANMA.
4. "detail" alanları MAX 1 CÜMLE olsun.

# ANALİZ KRİTERLERİ

## 🕹️ HAREKET HİSSİYATI — 30 puan
- Snappy mi floaty mi? rb.velocity vs rb.AddForce?
- Lerp/SmoothDamp var mı? Ground check var mı?

## ⚔️ COMBAT — 25 puan
- Input → Aksiyon gecikmesi? Feedback (shake, partikül)?

## 🎯 FİZİK — 20 puan
- FixedUpdate doğru mu? Fall multiplier var mı?

## 📷 KAMERA — 15 puan
- Smooth follow? LateUpdate içinde mi?

## ✨ JUICE — 10 puan
- Screen shake, squash & stretch, hit-stop var mı?

# KOD
```csharp
{code}
```

# BAĞLAM
{context}

# ÇIKTI FORMATI (STRICT JSON)
JSON dışında HİÇBİR metin yazma. Sadece aşağıdaki yapıyı döndür:

{{
    "game_feel_score": 7.5,
    "movement": {{"score": 8, "verdict": "snappy", "detail": "Kısa açıklama"}},
    "combat": {{"score": 6, "verdict": "responsive", "detail": "Kısa açıklama"}},
    "physics": {{"score": 7, "verdict": "consistent", "detail": "Kısa açıklama"}},
    "camera": {{"score": 5, "verdict": "smooth", "detail": "Kısa açıklama"}},
    "juice": {{"score": 3, "verdict": "basic", "detail": "Kısa açıklama"}},
    "suggestions": ["Öneri 1", "Öneri 2"],
    "summary": "Tek cümle genel değerlendirme"
}}"""

    def __init__(self, provider: Any):
        self.provider = provider

    def evaluate(self, code: str, context: str = "Kod analiz ediliyor.") -> Dict[str, Any]:
        """Verilen kodu oyun hissiyatı açısından değerlendirir."""
        logger.info("  [Game Feel Agent] 🎮 Oyun hissiyatı analiz ediliyor...")

        prompt = self.GAME_FEEL_PROMPT.format(code=code, context=context)

        try:
            response = self.provider.analyze_code(prompt, max_tokens=self.MAX_RESPONSE_TOKENS)
            result = self._parse_response(response)
            logger.info(
                f"  [Game Feel Agent] ✅ Skor: {result.get('game_feel_score', '?')}/10 "
                f"| Movement: {result.get('movement', {}).get('verdict', '?')} "
                f"| Combat: {result.get('combat', {}).get('verdict', '?')}"
            )
            return result
        except Exception as e:
            logger.error(f"  [Game Feel Agent] ❌ Hata: {e}")
            return self._fallback_result(str(e))

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """LLM yanıtından JSON'ı çıkar ve doğrula."""
        from validator import ResponseValidator

        is_valid, parsed = ResponseValidator.validate_json_response(
            response,
            required_keys=["game_feel_score", "summary"]
        )

        if is_valid and parsed:
            # Toplam skoru normaliz et (0-10 aralığı)
            score = float(parsed.get("game_feel_score", 5.0))
            parsed["game_feel_score"] = max(0.0, min(10.0, score))
            return parsed

        return self._fallback_result(f"JSON parse edilemedi: {response[:100] if response else 'Boş'}...")

    def _fallback_result(self, error: str) -> Dict[str, Any]:
        """Hata durumunda güvenli varsayılan sonuç."""
        return {
            "game_feel_score": -1.0,
            "movement": {"score": 0, "verdict": "unknown", "detail": "Analiz yapılamadı"},
            "combat": {"score": 0, "verdict": "unknown", "detail": "Analiz yapılamadı"},
            "physics": {"score": 0, "verdict": "unknown", "detail": "Analiz yapılamadı"},
            "camera": {"score": 0, "verdict": "unknown", "detail": "Analiz yapılamadı"},
            "juice": {"score": 0, "verdict": "unknown", "detail": "Analiz yapılamadı"},
            "suggestions": [],
            "summary": f"Game Feel analizi sırasında hata oluştu: {error}"
        }

    def format_for_ui(self, result: Dict[str, Any]) -> str:
        """Game Feel sonuçlarını alt-başlık olarak (bağımsız skor OLMADAN) formatlar."""
        if result.get("game_feel_score", -1) < 0:
            return ""

        lines = []

        # Kategori detayları (skor başlığı YOK — birleşik skor zaten pipeline'dan geliyor)
        categories = [
            ("🕹️ Hareket", "movement"),
            ("⚔️ Combat", "combat"),
            ("🎯 Fizik", "physics"),
            ("📷 Kamera", "camera"),
            ("✨ Polish", "juice"),
        ]
        for label, key in categories:
            cat = result.get(key, {})
            if cat.get("verdict") != "none" and cat.get("verdict") != "unknown" and cat.get("score", 0) > 0:
                lines.append(f"- {label}: **{cat.get('verdict', '?')}** — {cat.get('detail', '')}")

        # Öneriler (max 3)
        suggestions = result.get("suggestions", [])
        if suggestions:
            lines.append("\n**💡 İyileştirme Önerileri:**")
            for s in suggestions[:3]:
                lines.append(f"- {s}")

        return "\n".join(lines)
