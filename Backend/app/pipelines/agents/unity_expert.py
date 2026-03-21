import logging
from typing import Any

logger = logging.getLogger(__name__)

class UnityExpertAgent:
    """
    Kodu asıl düzelten ve yazan Ajan (Coder).
    Orkestratörün planını alır ve temiz, optimize edilmiş bir Unity C# kodu üretir.
    """
    def __init__(self, provider: Any):
        self.provider = provider
        
    def fix_code(self, code: str, plan: str, lang_instr: str, rules: str, learned_rules: str, max_tokens: int = 8192) -> str:
        logger.info(f"  [Unity Expert] Kod düzeltiliyor (Limit: {max_tokens})...")
        
        prompt = f"""
        # GÖREV: MİMARİ PLANA GÖRE C# KODUNU DÜZELT
        
        Aşağıda kullanıcının orijinal kodu ve Baş Mimarın (Orchestrator) bu kod için çıkardığı "Düzeltme Planı" bulunuyor.
        Görevin, sadece bu plana ve Best Practice kurallarına uyarak kodun EN İYİ (Enterprise Level) halini yazmaktır.
        
        [DİL TALİMATI]: {lang_instr}
        
        {learned_rules}
        
        # MİMARIN DÜZELTME PLANI
        {plan}
        
        # ORİJİNAL KOD
        ```csharp
        {code}
        ```
        
        {rules}
        
        # ÇIKTI FORMATI
        LÜTFEN SADECE DÜZELTİLMİŞ TAM C# KODUNU VER!
        Kod bloğu (```csharp ... ```) dışında HİÇBİR AÇIKLAMA YAPMA. Aksi halde pipeline kırılır.
        """
        
        try:
            fixed_code = self.provider.analyze_code(prompt)
            # Eğer model yine de dışına metin eklediyse temizle (pipeline tarafında da temizleniyor olabilir)
            return fixed_code
        except Exception as e:
            logger.error(f"[Unity Expert] Hata: {e}")
            return ""
