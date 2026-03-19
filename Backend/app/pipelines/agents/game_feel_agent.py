"""
Game Feel Agent — Oyun Hissiyatı Kontrolcüsü.

Bu ajan, üretilen veya düzeltilen kodun oyunda nasıl "hissettireceğini" değerlendirir.
Sadece kod kalitesi değil, OYUNCU DENEYİMİ odaklı puanlama yapar.

Kontrol Kriterleri:
- Hareket Akıcılığı: Lerp/Slerp/SmoothDamp var mı? Input smoothing?
- Combat Responsiveness: Input → Aksiyon gecikmesi riski?
- Fizik Tutarlılığı: FixedUpdate doğru kullanılıyor mu? Gravity scale mantıklı mı?
- Kamera: Smooth follow var mı? Sarsıntı riski?
- Genel Polish: Juice efektleri, feedback döngüsü var mı?
"""
import logging
import json
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


class GameFeelAgent:
    """
    Oyun hissiyatını puanlayan ajan.
    Critic'ten farklı olarak, kod kalitesine değil, oyuncunun kodu çalıştırdığında
    ne hissedeceğine odaklanır.
    """

    GAME_FEEL_PROMPT = """# GÖREV: UNITY OYUN HİSSİYATI ANALİZİ (GAME FEEL SCORING)

Sen Unity oyun geliştirme konusunda 15+ yıl deneyimli bir **Gameplay Programmer ve Game Designer**'sın.
Görevin, aşağıdaki Unity C# kodunu analiz ederek kodun oyun içinde nasıl "hissettireceğini" puanlamaktır.

[ÖNEMLİ] Bu bir "kod kalitesi" incelemesi DEĞİLDİR. 
Temiz yazılmış ama oyunda berbat hissettiren bir kod 2/10 alabilir.
Kötü yazılmış ama oyuncuya harika hissettiren bir kod 7/10 alabilir.

# ANALİZ KRİTERLERİ

## 🕹️ HAREKET HİSSİYATI (Movement Feel) — 30 puan
- Oyuncu hareketi anında mı tepki veriyor (snappy) yoksa kaygan mı (floaty)?
- `rb.AddForce` ile hareket = genellikle kaygan. `rb.velocity` veya `CharacterController.Move` = keskin.
- Hız değişimi ani mi yoksa yumuşak geçişli mi (Lerp/SmoothDamp)?
- Yere değme kontrolü (ground check) var mı?

## ⚔️ COMBAT / ETKİLEŞİM (Combat Responsiveness) — 25 puan
- Saldırı/aksiyon tetiklendiğinde gecikme var mı?
- Input → Animasyon → Efekt zinciri akıcı mı?
- Cooldown/combo sistemi var mı?
- Geri bildirim (feedback) var mı? (kamera sarsıntısı, partikül, ses tetikleme)

## 🎯 FİZİK TUTARLILIĞI (Physics Consistency) — 20 puan
- Fizik kodu `FixedUpdate` içinde mi, `Update` içinde mi?
- Zıplama havada çok mu asılı kalıyor (floaty jump)?
- Düşüş hızlandırması (fall multiplier) var mı?
- Rigidbody interpolation ayarı belirtilmiş mi?

## 📷 KAMERA (Camera Feel) — 15 puan
- Kamera takibi smooth mu yoksa sert mi?
- `SmoothDamp` veya `Lerp` ile takip var mı?
- LateUpdate içinde mi?

## ✨ POLİSH / JUICE (Game Juice) — 10 puan
- Squash & stretch, screen shake, partikül gibi "juice" referansları var mı?
- Ses/efekt tetikleme noktaları belirli mi?
- Time.timeScale manipülasyonu (hit-stop gibi) var mı?

# KOD
```csharp
{code}
```

# BAĞLAM
{context}

# ÇIKTI FORMATI (SADECE JSON)
Cevabını aşağıdaki JSON formatında ver. Başka hiçbir şey yazma!

```json
{{
    "game_feel_score": 7.5,
    "movement": {{
        "score": 8,
        "verdict": "snappy|floaty|balanced",
        "detail": "Kısa açıklama"
    }},
    "combat": {{
        "score": 6,
        "verdict": "responsive|delayed|none",
        "detail": "Kısa açıklama"
    }},
    "physics": {{
        "score": 7,
        "verdict": "consistent|inconsistent|none",
        "detail": "Kısa açıklama"
    }},
    "camera": {{
        "score": 5,
        "verdict": "smooth|rigid|none",
        "detail": "Kısa açıklama"
    }},
    "juice": {{
        "score": 3,
        "verdict": "polished|basic|none",
        "detail": "Kısa açıklama"
    }},
    "suggestions": [
        "Somut iyileştirme önerisi 1",
        "Somut iyileştirme önerisi 2"
    ],
    "summary": "Tek paragraf genel oyun hissiyatı değerlendirmesi"
}}
```"""

    def __init__(self, provider: Any):
        self.provider = provider

    def evaluate(self, code: str, context: str = "Kod analiz ediliyor.") -> Dict[str, Any]:
        """Verilen kodu oyun hissiyatı açısından değerlendirir."""
        logger.info("  [Game Feel Agent] 🎮 Oyun hissiyatı analiz ediliyor...")

        prompt = self.GAME_FEEL_PROMPT.format(code=code, context=context)

        try:
            response = self.provider.analyze_code(prompt)
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
        if not response:
            return self._fallback_result("Boş yanıt")

        text = response.strip()

        # Markdown JSON bloğu
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        else:
            # Direkt JSON bloğu
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                text = match.group(0).strip()

        try:
            parsed = json.loads(text, strict=False)

            # Toplam skoru normaliz et (0-10 aralığı)
            score = float(parsed.get("game_feel_score", 5.0))
            parsed["game_feel_score"] = max(0.0, min(10.0, score))

            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"  [Game Feel Agent] JSON parse hatası: {e}")
            return self._fallback_result(f"JSON parse hatası: {e}")

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
        """Game Feel sonuçlarını kullanıcı dostu Markdown formatına çevirir."""
        if result.get("game_feel_score", -1) < 0:
            return ""

        score = result["game_feel_score"]
        
        # Emoji'li skor gösterimi
        if score >= 8:
            emoji = "🔥"
            verdict = "Harika Hissettiriyor!"
        elif score >= 6:
            emoji = "👍"
            verdict = "İyi Ama Geliştirilebilir"
        elif score >= 4:
            emoji = "⚠️"
            verdict = "Orta — İyileştirme Gerekli"
        else:
            emoji = "❌"
            verdict = "Zayıf — Ciddi İyileştirme Gerekli"

        lines = [
            f"\n\n---\n**{emoji} OYUN HİSSİYATI PUANI: {score}/10 — {verdict}**\n",
        ]

        # Kategori detayları
        categories = [
            ("🕹️ Hareket", "movement"),
            ("⚔️ Combat", "combat"),
            ("🎯 Fizik", "physics"),
            ("📷 Kamera", "camera"),
            ("✨ Polish", "juice"),
        ]
        for label, key in categories:
            cat = result.get(key, {})
            if cat.get("verdict") != "none" and cat.get("score", 0) > 0:
                lines.append(f"- {label}: **{cat.get('verdict', '?')}** ({cat.get('score', '?')}/10) — {cat.get('detail', '')}")

        # Öneriler
        suggestions = result.get("suggestions", [])
        if suggestions:
            lines.append("\n**💡 İyileştirme Önerileri:**")
            for s in suggestions[:3]:  # Max 3 öneri
                lines.append(f"- {s}")

        return "\n".join(lines)
