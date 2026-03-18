import logging
from typing import Any

logger = logging.getLogger(__name__)

class ArchitectGenerationAgent:
    """
    Sıfırdan kod üretimi için Mimar ajan.
    Kullanıcının isteğini alır ve hangi scriptlerin, hangi mimariye 
    ve hangi best practice'lere göre yazılacağını belirler.
    """
    def __init__(self, provider: Any):
        self.provider = provider
        
    def plan_architecture(self, prompt: str, lang_instr: str, rules: str) -> str:
        logger.info("  [Architect - Gen] Sıfırdan Mimari Plan oluşturuluyor...")
        
        system_prompt = f"""
        # GÖREV: SIFIRDAN UNITY OYUN GELİŞTİRME MİMARİSİ
        
        Sen üst düzey bir Unity Oyun Mimarsısın. 
        Kullanıcı sana sıfırdan oluşturulmasını istediği bir özellik (örn: Envanter Sistemi, Karakter Kontrolcüsü, Düşman Yapay Zekası) fikriyle geldi.
        Görevin, Unity Uzmanı (Coder) ajanın kodu yazmadan önce izlemesi gereken ADIM ADIM bir yazılım tasarım planı (Blueprint) oluşturmaktır.
        
        [DİKKAT - OYUN HİSSİYATI (GAME FEEL)]
        Mükemmel yazılmış bir kod oyun içinde oyuncuya iğrenç hissettirebilir (örn: Player hareketinde AddForce kullanmak).
        Mimari kararlarını verirken teknik doğruluğun yanında kesinlikle "Oyun Hissiyatını" merkeze koy.
        
        {lang_instr}
        
        [KULLANICI İSTEĞİ - FİKİR]
        {prompt}
        
        [KURALLAR]
        {rules}
        
        # ÇIKTI FORMATI (ÇOK ÖNEMLİ - HIZ İÇİN KISA TUT)
        1. Gereksiz hiçbir açıklama veya merhaba veda kelimesi kullanma.
        2. Sadece 3-4 maddelik ÇOK KISA bir teknik harita çıkar (Hangi script, hangi ana fonksiyonlar, hangi fizik yöntemi).
        3. Tüm cevabın maksimum 100 kelimeyi aşmasın.
        SEN KOD YAZMA!
        """
        
        try:
            plan = self.provider.analyze_code(system_prompt)
            return plan
        except Exception as e:
            logger.error(f"[Architect - Gen] Hata: {e}")
            return f"Planlama başarısız oldu: {str(e)}"
