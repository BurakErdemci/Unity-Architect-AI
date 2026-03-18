import logging
import json
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

class CriticAgent:
    """
    Puanlayıcı ve Denetmen Ajan.
    Uzmanın yazdığı yeni kodu ve eski kodu alır. Son derece acımasız ve katı kurallarla kodu puanlar.
    Eğer kodda syntax hatası, '=' atama hatası veya fatal error varsa, kodu 5.0'dan başlatır.
    """
    def __init__(self, provider: Any):
        self.provider = provider
        
    def evaluate(self, original_code: str, fixed_code: str, plan: str, lang_instr: str) -> Dict[str, Any]:
        logger.info("  [Critic Agent] Kod denetleniyor ve puanlanıyor...")
        
        prompt = f"""
        # GÖREV: KULLANICIYA DOSTANE AÇIKLAMALAR SUNAN KOD İNCELEMESİ (USER-CENTRIC REVIEW & SCORING)
        
        Sen son derece bilgili ama bir o kadar da **yardımsever ve sabırlı bir Unity Eğitmenisin (Senior Mentor)**.
        Aşağıda kullanıcının (oyun geliştiricisi) bize gönderdiği "Orijinal Kod" ve bizim sistemimizin (Uzman Ajan) onun için yazdığı "Geliştirilmiş Kod" var.
        Görevin: Kullanıcıya hitap ederek, onun kodunu nasıl daha iyi (profesyonel, performanslı ve güvenli) hale getirdiğimizi basit, sevecen ve açıklayıcı bir dille anlatmak ve koda bir puan (0.0 - 10.0) vermektir.
        Aşırı teknik terimlere boğmadan, "Senin kodunda X vardı, biz bunu Y yaptık ki daha iyi çalışsın" mantığını kullanarak anlat. Sanki onun kodunu beraber baştan yazıyormuşsunuz gibi hissettir.
        
        [DİL TALİMATI]: Lütfen analizini '{lang_instr}' diliyle yap.
        
        # Orijinal Kod
        ```csharp
        {original_code}
        ```
        
        # Düzeltilmiş Kod
        ```csharp
        {fixed_code}
        ```
        
        # PUANLAMA KURALLARI (İHLAL EDİLEMEZ)
        1. [ÖLÜMCÜL HATALAR] Eğer Orijinal Kodda bariz bir derleme hatası varsa (örneğin if(x = y) atama hatası, syntax error) max 5.0 PUAN verebilirsin.
        2. [PERFORMANS] Update içinde GetComponent, FindGameObject varsa her ihlal için -1.0 puan düş.
        3. [MİMARİ] Public variable yerine [SerializeField] private kullanılmamışsa veya namespace yoksa her ihlal için -0.5 puan düş.
        
        # ÇÖZÜM FORMATI (Tasarım ve Okunabilirlik Kuralları)
        Lütfen cevabını JSON formatında verirken, "review_message" alanını ÇOK TEMİZ, FERAH, YENİ BAŞLAYAN DOSTU bir Markdown metni olarak hazırla:
        - Kullanıcıya doğrudan ve dostane hitap et ("Merhaba! Kodunu inceledik ve senin için harika hale getirdik. Bak neler yaptık:").
        - **Kalın yazılar**, boş satırlar ve Emojiler (✅, ❌, ⚠️, 💡) kullanarak metni böl. Asla blok ve sıkıcı paragraflar yazma.
        - ÖNEMLİ: json formatının bozulmaması için metin içindeki satır atlamalarını MUTLAKA `\\n` şeklinde escape (kaçış) karakteriyle yaz. Doğrudan enter'a basma!
        - Maddeler halinde (Bullet points) listele. Örnek:
          ✅ **Derleme Hatası Giderildi:** Kodundaki `if` içindeki eşittir işaretini (`==`) düzelttik, artık kodun sorunsuz çalışacak!\\n\\n💡 **Performans İpucu:** Fizik kodlarını `Update` yerine `FixedUpdate` içine taşıdık ki oyunun kasmadan pürüzsüz çalışsın.

        # İSTENEN ÇIKTI (SADECE JSON)
        Lütfen cevabını AŞAĞIDAKİ JSON FORMATINDA ver. Markdown JSON bloğu (```json ... ```) kullanabilirsin ama DIŞINA HİÇBİR TEXT YAZMA!
        
        {{
            "score": 4.5, // Float, kurallara göre hesaplanmış
            "review_message": "Buraya eleştirilerini ve neyin neden düşük/yüksek puan aldığını FERAH, MADDE MADDE VE EMOJİLİ BİR ŞEKİLDE yaz.",
            "fatal_errors_found": true // Eğer derleme hatası yakaladıysan true, yoksa false
        }}
        """
        
        try:
            response = self.provider.analyze_code(prompt)
            # Extract JSON from response
            json_str = response.strip()
            
            # 1. Try to find markdown json block
            match = re.search(r'```json\s*(.*?)\s*```', json_str, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
            else:
                # 2. Try to find standard { ... } block
                match = re.search(r'\{.*\}', json_str, re.DOTALL)
                if match:
                    json_str = match.group(0).strip()
            
            # Temizlik önlemi: Eğer LLM yine de escape etmemiş newlines koyduysa (string içinde),
            # re.sub ile string value'ları yakalayıp düzeltmek risklidir (JSON parsing).
            # strict=False kullanarak parser'ın control karakterlerini yutmasını sağlayabiliriz.
            result = json.loads(json_str, strict=False)
            return {
                "score": float(result.get("score", 0.0)),
                "review_message": result.get("review_message", "Eleştiri metni bulunamadı."),
                "fatal_errors_found": result.get("fatal_errors_found", False),
            }
        except Exception as e:
            logger.error(f"[Critic Agent] Hata: {e}")
            return {
                "score": -1.0,
                "review_message": f"Eleştirmen Ajanı bir JSON hatasıyla karşılaştı. Hata: {str(e)}\n\n(Ham Yanıt: {response if 'response' in locals() else 'Yok'})",
                "fatal_errors_found": False
            }
