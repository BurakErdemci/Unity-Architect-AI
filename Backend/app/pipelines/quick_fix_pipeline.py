import json
import logging
import re
import time

from .base import BasePipeline, PipelineResult, StepResult

logger = logging.getLogger(__name__)

_FIX_PROMPT = """Sen bir Unity C# hata düzeltici ajansın. Kullanıcı şu sorunu bildirdi: "{user_message}"

İşte kod:
```csharp
{code}
```

Görevin:
1. Bildirilen soruna neden olan spesifik hatayı bul
2. SADECE o hatayı düzelt — refactor yapma, özellik ekleme, yeniden organize etme
3. Eğer sorun sadece kodda değil Unity Editor ayarlarında da olabiliyorsa (örn. eksik Rigidbody component, Inspector'da yanlış tag, Layer ayarı, Physics Material eksikliği vb.) bunu editor_hint alanında belirt
4. Eğer kod yoksa veya koddan düzeltilemeyecekse fixed_code null olsun

SADECE şu JSON formatında yanıt ver (markdown veya JSON dışında hiçbir şey yazma):
{{"explanation": "Tek cümle Türkçe açıklama: ne yanlıştı ve tam olarak ne değiştirdin", "fixed_code": "düzeltilmiş tam dosya içeriği ya da null", "editor_hint": "Unity Editor'da kontrol edilmesi gereken şey (varsa), yoksa null"}}"""


class QuickFixPipeline(BasePipeline):
    """
    Lightweight bug fix pipeline.
    Tek LLM çağrısı: hatayı bul, düzelt, structured diff döndür.
    Skor yok, rapor yok, game feel yok.
    """

    async def run(self) -> PipelineResult:
        start = time.time()
        logger.info("🔧 QuickFix Pipeline başlatılıyor...")

        if not self.code or not self.code.strip():
            self._result.combined_response = (
                "Düzeltmek için bir kod gerekli. Lütfen editörde bir `.cs` dosyası aç "
                "veya kodu **Kodu AI'ya Ekle** butonuyla gönder."
            )
            self._result.step2_analysis = StepResult(
                step_name="quick_fix", success=False,
                duration_ms=int((time.time() - start) * 1000),
                error="no_code"
            )
            return self._result

        prompt = _FIX_PROMPT.format(
            user_message=self.user_message or self.prompt,
            code=self.code,
        )

        try:
            raw = self.provider.analyze_code(prompt)
            explanation, fixed_code, editor_hint = self._parse_response(raw)

            duration_ms = int((time.time() - start) * 1000)
            logger.info(f"✅ QuickFix tamamlandı — {duration_ms}ms")

            self._result.fixed_code = fixed_code or ""
            self._result.combined_response = explanation
            self._result.step2_analysis = StepResult(
                step_name="quick_fix", success=True,
                duration_ms=duration_ms,
                output={"explanation": explanation, "fixed_code": fixed_code, "editor_hint": editor_hint}
            )

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"❌ QuickFix hatası: {e}")
            self._result.combined_response = f"Hata düzeltme sırasında sorun oluştu: {e}"
            self._result.step2_analysis = StepResult(
                step_name="quick_fix", success=False,
                duration_ms=duration_ms, error=str(e)
            )

        self._result.total_duration_ms = int((time.time() - start) * 1000)
        return self._result

    def _parse_response(self, raw: str) -> tuple[str, str | None]:
        if not raw:
            return "AI yanıt vermedi.", None

        candidate = raw.strip()

        # 1. ```json ... ``` bloğu
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', candidate, re.DOTALL)
        if m:
            candidate = m.group(1)
        else:
            # 2. İlk { den son } e kadar al
            start = candidate.find('{')
            end = candidate.rfind('}')
            if start != -1 and end != -1 and end > start:
                candidate = candidate[start:end + 1]

        try:
            data = json.loads(candidate)
            explanation = str(data.get("explanation") or "Hata düzeltildi.").strip()
            fixed_code = data.get("fixed_code") or None
            if isinstance(fixed_code, str) and fixed_code.strip().lower() in ("null", "none", ""):
                fixed_code = None
            editor_hint = data.get("editor_hint") or None
            if isinstance(editor_hint, str) and editor_hint.strip().lower() in ("null", "none", ""):
                editor_hint = None
            return explanation, fixed_code, editor_hint
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"[QuickFix] JSON parse başarısız, raw snippet: {raw[:200]}")
            return "Hatayı analiz ettim ancak yapılandırılmış yanıt üretilemedi. Lütfen tekrar deneyin.", None, None
