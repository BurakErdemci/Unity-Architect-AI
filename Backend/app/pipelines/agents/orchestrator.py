import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class OrchestratorAgent:
    """
    Planlayıcı ajan. Gelen kodu, analiz sorunlarını ve sistemdeki bağlamı alıp
    Unity uzmanına (Expert) nasıl bir düzeltme yapması gerektiğine dair bir 'İş Planı' çıkarır.
    """
    def __init__(self, provider: Any):
        self.provider = provider
        
    def plan_task(self, code: str, smells: List[Dict], user_message: str) -> str:
        logger.info("  [Orchestrator] İş planı oluşturuluyor...")
        
        prompt = f"""
        # GÖREV: UNITY C# KOD DÜZELTME PLANLAMASI
        
        Aşağıda kullanıcının gönderdiği Unity C# Kodu ve statik analizörün bulduğu hatalar (smells) yer alıyor.
        Senin görevin, kodu analiz eden bir Baş Mimar (Orchestrator) olarak, Unity Uzmanı (Expert) ajanın bu kodda
        neleri, hangi sırayla ve nasıl düzeltmesi gerektiğine dair ADIM ADIM bir plan oluşturmandır.
        
        [DİKKAT - OYUN HİSSİYATI (GAME FEEL)]
        Mükemmel yazılmış, %100 fizik kurallarına uyan bir kod oyun içinde oyuncuya iğrenç hissettirebilir (örn: Player hareketinde AddForce kullanmak).
        Bu yüzden mimari kararlarını verirken sadece teknik doğruluğu değil, "Oyun Hissiyatını" merkeze koy. Keskin, tatmin edici (snappy) kontroller sağlamak için RigidBody Velocity veya CharacterController kullanılmasını şart koşabilirsin.
        
        # MEVCUT KOD
        ```csharp
        {code}
        ```
        
        # STATİK ANALİZ BULGULARI
        {smells if smells else "Statik analizde kural ihlali bulunamadı."}
        
        # KULLANICI MESAJI / İSTEĞİ
        {user_message}
        
        # ÇIKTI FORMATI
        Lütfen sadece Uzman Ajan'ın anlayacağı net, kısa ve teknik bir "Düzeltme Adımları Listesi" veya "Mimari Revizyon Planı" ver.
        Kodu sen yazma, sadece planı çıkar.
        """
        
        try:
            plan = self.provider.analyze_code(prompt)
            return plan
        except Exception as e:
            logger.error(f"[Orchestrator] Hata: {e}")
            return f"Planlama başarısız oldu: {str(e)}"
