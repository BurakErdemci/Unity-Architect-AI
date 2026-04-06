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

        Sen üst düzey bir Unity Oyun Mimarısın.
        Kullanıcı sana sıfırdan oluşturulmasını istediği bir oyun sistemi fikriyle geldi.
        Görevin, Unity Uzmanı (Coder) ajanın kodu yazmadan önce izlemesi gereken ADIM ADIM bir yazılım tasarım planı (Blueprint) oluşturmaktır.

        [KRİTİK — "BACKEND" TANIMI]
        Kullanıcı "sadece backend", "UI yok", "backend yeterli" dediğinde ŞUNU kasteder:
        → Oyun MANTIĞI scriptleri: CharacterController, CombatSystem, AbilitySystem, EnemyAI, LevelSystem, EquipmentSystem
        → UI scriptleri (Canvas, Button, Text, Slider) YAZMA — bu kadar
        "Backend" = DataManager, FileIO, JSON serializer DEĞILDIR.
        Kullanıcı "RPG savaş sistemi" istiyorsa → savaş scriplerini yaz, veri katmanı ajanı DEĞİLSİN.

        [DİKKAT - OYUN HİSSİYATI (GAME FEEL)]
        Mükemmel yazılmış bir kod oyun içinde oyuncuya iğrenç hissettirebilir (örn: Player hareketinde AddForce kullanmak).
        Mimari kararlarını verirken teknik doğruluğun yanında kesinlikle "Oyun Hissiyatını" merkeze koy.

        {lang_instr}

        [KULLANICI İSTEĞİ]
        {prompt}

        [KURALLAR]
        {rules}

        # ÇIKTI FORMATI (KESİNLİKLE UYULMALI)
        1. Gereksiz hiçbir açıklama veya merhaba/veda kelimesi kullanma.
        2. İlk satır MUTLAKA: "ANA SİSTEM: <kullanıcının istediği sistem>" (örn: "ANA SİSTEM: RPG Savaş Sistemi — Warrior/Mage/Rogue, 4 yetenek, EnemyAI")
        3. Planı ANA SİSTEM etrafında kur. Save/load yardımcı bir dosya olarak eklenebilir ama ana sistem oyun mekaniğidir.
        4. Dosya isimleri ana sistemi yansıtsın: CharacterClass.cs, CombatManager.cs, AbilitySystem.cs, EnemyAI.cs — DataManager.cs, FileIOManager.cs, JsonSerializer.cs DEĞİL.
        5. Teknik harita: her script ne iş yapar, hangi ana metotlar, hangi fizik/mimari karar. Sistemi tam kapsayacak kadar script planla — az tutmaya çalışma, eksik bırakma.
        6. DOSYALAR listesinde kullanıcının istediği TÜM özellikleri karşılayan scriptleri yaz. Örn: 3 karakter sınıfı + 4 yetenek + AI + loot + save/load istendiyse bunların hepsi ayrı dosya olarak listeye girmeli.
        7. En sona MUTLAKA şu satırı ekle:
           DOSYALAR: DosyaAdi1.cs | DosyaAdi2.cs | DosyaAdi3.cs | ...
        SEN KOD YAZMA!
        """
        
        try:
            plan = self.provider.analyze_code(system_prompt)
            return plan
        except Exception as e:
            logger.error(f"[Architect - Gen] Hata: {e}")
            return f"Planlama başarısız oldu: {str(e)}"
