"""
Response Validator — AI çıktılarını doğrular ve güvenli hale getirir.

Bu modül 3 katmanlı koruma sağlar:
1. AI yanıtının boş/bozuk olup olmadığını kontrol eder
2. C# kod bloğu bütünlüğünü denetler (açılış/kapanış parantezleri, namespace vb.)
3. Unity-spesifik kalite kurallarını kontrol eder (FixedUpdate+Input vb.)
"""
import re
import json
import logging
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ResponseValidator:
    """AI çıktısını denetleyen ve düzeltme talep eden katman."""
    
    @staticmethod
    def validate(response: str) -> Tuple[bool, List[str]]:
        """
        AI yanıtını doğrular. (bool: geçerli mi?, List: sorunlar)
        """
        issues = []
        
        if not response or not response.strip():
            issues.append("AI yanıtı boş döndü.")
            return (False, issues)
        
        # 1. Kod bloğu var mı?
        if "```csharp" not in response and "```cs" not in response:
            issues.append("Kod bloğu (```csharp) eksik.")
        
        # 2. Tembellik kontrolü (AI kodu yarım mı bıraktı?)
        lazy_patterns = ["...", "// ..", "// rest of", "// remaining", "// diğer", "// kalan"]
        for pattern in lazy_patterns:
            if pattern in response:
                issues.append(f"Kod yarım bırakılmış ('{pattern}' bulundu). Lütfen tam kodu yaz.")
                break

        # 3. C# Kod Bloğu Bütünlük Kontrolü
        code_blocks = re.findall(r'```(?:csharp|cs)\s*(.*?)\s*```', response, re.DOTALL)
        for block in code_blocks:
            block_issues = ResponseValidator._check_code_integrity(block)
            issues.extend(block_issues)

        return (len(issues) == 0, issues)
    
    @staticmethod
    def _check_code_integrity(code: str) -> List[str]:
        """C# kod bloğunun yapısal bütünlüğünü kontrol eder."""
        issues = []
        
        # Parantez dengesi kontrolü
        open_braces = code.count("{")
        close_braces = code.count("}")
        if open_braces != close_braces:
            issues.append(f"Süslü parantez dengesi bozuk: {{ açılış: {open_braces}, }} kapanış: {close_braces}")
        
        # Kritik Unity Hatası: FixedUpdate içinde Input kalmış mı?
        if "void FixedUpdate" in code and "Input." in code:
            issues.append("HATA: FixedUpdate içinde hala Input tespiti var. Bunu Update'e taşı!")
        
        # Class tanımı var mı? (çok kısa kod blokları hariç)
        if len(code.strip().split("\n")) > 5 and "class " not in code:
            issues.append("Kod bloğunda class tanımı eksik — yalnızca metod parçacığı mı gönderildi?")
        
        return issues

    @staticmethod
    def validate_json_response(response: str, required_keys: List[str] = None) -> Tuple[bool, Optional[Dict]]:
        """
        AI yanıtını JSON olarak parse etmeyi dener.
        Markdown bloğu içindeki JSON'ı da yakalar.
        
        Returns: (başarılı mı?, parse edilen dict veya None)
        """
        if not response or not response.strip():
            logger.warning("[Validator] JSON parse: yanıt boş.")
            return (False, None)
        
        text = response.strip()
        
        # Markdown JSON bloğu içindeyse çıkar
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            text = json_match.group(1).strip()
        
        # Direkt JSON ise
        try:
            parsed = json.loads(text)
            
            # Gerekli alanlar kontrolü
            if required_keys:
                missing = [k for k in required_keys if k not in parsed]
                if missing:
                    logger.warning(f"[Validator] JSON'da eksik alanlar: {missing}")
                    return (False, parsed)
            
            return (True, parsed)
        except json.JSONDecodeError as e:
            logger.warning(f"[Validator] JSON parse hatası: {e}")
            
            # Kurtarma denemesi: yanıttan JSON bloğu çıkar
            json_pattern = re.search(r'\{[\s\S]*\}', text)
            if json_pattern:
                try:
                    parsed = json.loads(json_pattern.group())
                    logger.info("[Validator] JSON kurtarma başarılı (regex ile).")
                    return (True, parsed)
                except json.JSONDecodeError:
                    pass
            
            return (False, None)

    @staticmethod
    def safe_ai_call(provider, prompt: str, max_retries: int = 2, validate_fn=None) -> str:
        """
        AI çağrısını güvenli bir şekilde yapar.
        Başarısız olursa otomatik retry yapar.
        
        Args:
            provider: AI sağlayıcısı
            prompt: Gönderilecek prompt
            max_retries: Maksimum deneme sayısı
            validate_fn: Opsiyonel doğrulama fonksiyonu (response -> bool)
        """
        last_response = ""
        last_error = ""
        
        for attempt in range(1, max_retries + 1):
            try:
                response = provider.analyze_code(prompt)
                
                if not response or not response.strip():
                    last_error = "Boş yanıt"
                    logger.warning(f"[SafeAI] Deneme {attempt}: Boş yanıt geldi.")
                    continue
                
                # Özel doğrulama fonksiyonu varsa çalıştır
                if validate_fn and not validate_fn(response):
                    last_error = "Doğrulama başarısız"
                    logger.warning(f"[SafeAI] Deneme {attempt}: Doğrulama başarısız.")
                    last_response = response
                    # Prompt'a hata bilgisi ekle
                    prompt = f"ÖNCEKİ YANITINDA HATALAR VARDI. LÜTFEN DÜZELT:\n{prompt}"
                    continue
                
                logger.info(f"[SafeAI] Başarılı (deneme {attempt})")
                return response
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"[SafeAI] Deneme {attempt} hatası: {e}")
        
        # Tüm denemeler başarısız
        if last_response:
            logger.warning(f"[SafeAI] {max_retries} deneme sonrası en iyi yanıt döndürülüyor.")
            return last_response
        
        return f"❌ AI yanıt üretemedi ({max_retries} deneme sonrası). Son hata: {last_error}"