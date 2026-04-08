import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


class CriticAgent:
    """
    Teknik Denetçi Ajan (Pure Reviewer).
    SADECE puanlama ve kısa teknik bulgular üretir.
    ASLA kod yazmaz, ASLA uzun açıklama yapmaz.
    """

    # ─── MAX TOKEN LİMİTİ ───
    MAX_RESPONSE_TOKENS = 1024  # Uzun essay'leri engeller

    def __init__(self, provider: Any):
        self.provider = provider

    def evaluate(self, original_code: str, fixed_code: str, plan: str, lang_instr: str) -> Dict[str, Any]:
        logger.info("  [Critic Agent] Kod denetleniyor ve puanlanıyor...")

        prompt = f"""# GÖREV: KESKİN VE TEKNİK KOD DENETİMİ (STRICT TECHNICAL AUDIT)

Sen üst düzey bir Unity Teknik Denetçisisin. Görevin, Uzman (Expert) ajan tarafından yazılan "Düzeltilmiş Kod"u, "Orijinal Kod" ile karşılaştırarak teknik açıdan denetlemek ve puanlamaktır.

[BAĞLAM HATIRLATMASI]:
- "Orijinal Kod" = Kullanıcının gönderdiği ham kod.
- "Düzeltilmiş Kod" = Expert ajanın düzelttiği versiyon. SENİN DENETLEYECEĞİN KOD BUDUR.
- Görevin SADECE "Düzeltilmiş Kod"u teknik açıdan değerlendirmek ve puanlamaktır.

[NEGATİF KISITLAMALAR — İHLAL EDILEMEZ]:
1. ASLA KOD YAZMA. Kod bloğu (```csharp```) içeren hiçbir metin üretme.
2. ASLA GİRİŞ/ÇIKIŞ CÜMLESİ YAZMA ("Merhaba", "İşte analizim" vb. YASAKTIR).
3. ASLA CODER ROLÜNE BÜRÜNME. Kod önerisi veya refactor yapma.
4. "review_message" İÇİNDE KOD PARÇACIĞI KULLANMA. Sadece metin ve emoji kullan.
5. "review_message" MAX 5 MADDE İÇERSİN. Kısa ve öz ol.

[DİL TALİMATI]: Analizi '{lang_instr}' diliyle yap.

# Orijinal Kod
```csharp
{original_code}
```

# Düzeltilmiş Kod (DENETLENECEĞİN KOD)
```csharp
{fixed_code}
```

# PUANLAMA KRİTERLERİ
1. [TEKNİK DOĞRULUK] Derleme/çalışma zamanı hatası var mı? Dış bağımlılıklar (BulletPool, GameManager vb.) güvenli null-checked mi? (Varsa max 5.0)
2. [PERFORMANS] Update içinde pahalı çağrı (GetComponent, Find, new allocation) kalmış mı?
3. [DÜZELTME KALİTESİ] Expert hangi sorunları gerçekten düzeltti, hangilerini atladı veya yeni sorun ekledi?
4. [GEREKSİZ/TEHLİKELİ KOD] Savunmacı ama işlevsiz kontroller, yarış koşulu riski, Destroy/Instantiate kötüye kullanımı var mı?

[ÖNEMLİ]: "Düzeltilmiş Kod"u orijinale göre karşılaştırmalı değerlendir. Expert'in eklediği şeyleri övme — sadece EKSİK KALAN veya YENİ EKLENEN SORUNLARI belirt.

# ÇIKTI FORMATI (STRICT JSON — TEK SATIR AÇIKLAMA)
JSON dışında HİÇBİR metin yazma. Sadece aşağıdaki yapıyı döndür:

{{
    "score": 8.5,
    "review_message": "❌ GetComponent Update içinde.\\n⚠️ Namespace eksik.\\n✅ FixedUpdate doğru.",
    "fatal_errors_found": false
}}"""

        from validator import ResponseValidator

        try:
            response = self.provider.analyze_code(prompt, max_tokens=self.MAX_RESPONSE_TOKENS)

            # ─── POST-PROCESSING: Kod bloğu varsa strip et ───
            response = self._strip_code_blocks(response)

            # Centralized Validator kullanımı
            is_valid, result = ResponseValidator.validate_json_response(
                response,
                required_keys=["score", "review_message"]
            )

            if is_valid and result:
                # Score clamping: 0-10 aralığına zorla
                raw_score = float(result.get("score", 0.0))
                clamped_score = max(0.0, min(10.0, raw_score))

                return {
                    "score": clamped_score,
                    "review_message": result.get("review_message", "Eleştiri metni bulunamadı."),
                    "fatal_errors_found": result.get("fatal_errors_found", False),
                }
            else:
                raise ValueError("JSON parse edilemedi veya gerekli alanlar eksik.")

        except Exception as e:
            logger.error(f"[Critic Agent] Hata: {e}")
            # Fallback: Ham yanıtı truncate et (UI'da bozuk JSON göstermeyi önle)
            raw_preview = (response[:200] + "...") if 'response' in dir() and response else "Yok"
            return {
                "score": 5.0,  # -1 yerine nötr skor (skor tutarsızlığını önler)
                "review_message": f"⚠️ Denetim sırasında teknik hata oluştu. Kod yeniden değerlendirilecek.",
                "fatal_errors_found": False,
            }

    @staticmethod
    def _strip_code_blocks(text: str) -> str:
        """LLM yanıtından code blocks'ları temizler (role violation koruması)."""
        if not text:
            return ""
        # ```csharp ... ``` veya ```cs ... ``` bloklarını tamamen kaldır
        cleaned = re.sub(r'```(?:csharp|cs)\s*[\s\S]*?```', '', text)
        return cleaned.strip()
