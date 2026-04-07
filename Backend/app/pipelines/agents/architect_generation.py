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

        [#1 KURAL — KULLANICI PRİORİTESİ]
        Kullanıcının istediği HER özellik MUTLAKA üretilmelidir. Bu kuralın istisnası yoktur.
        Kullanıcı "envanter istiyorum" dediyse → envanter dosyaları PLANA GİRMELİDİR.
        Kullanıcı "quest sistemi istiyorum" dediyse → quest dosyaları PLANA GİRMELİDİR.
        Kullanıcı "save/load istiyorum" dediyse → save/load dosyaları PLANA GİRMELİDİR.
        Hiçbir özelliği "karmaşık olur", "sonra eklenebilir" diye ATLAMA.
        Bir özelliği atlarsan sistem eksik kalır ve kullanıcı aldatılmış hisseder.

        [#2 KURAL — SIRALAMA]
        Önce kullanıcının açıkça istediği özellikler → sonra bunları destekleyen yan sistemler.
        Destekleyici sistemler (interface, base class, manager singletonlar) kullanıcı isteğini
        karşılamak için gerekliyse ekle, yoksa ekleme.

        [KRİTİK — "BACKEND" TANIMI]
        Kullanıcı "sadece backend", "UI yok", "backend yeterli" dediğinde ŞUNU kasteder:
        → Oyun MANTIĞI scriptleri: CharacterController, CombatSystem, AbilitySystem, EnemyAI, LevelSystem, EquipmentSystem
        → UI scriptleri (Canvas, Button, Text, Slider) YAZMA — bu kadar
        "Backend" = DataManager, FileIO, JSON serializer DEĞILDIR.
        Kullanıcı "RPG savaş sistemi" istiyorsa → savaş scriptlerini yaz, veri katmanı ajanı DEĞİLSİN.

        [DİKKAT - OYUN HİSSİYATI (GAME FEEL)]
        Mükemmel yazılmış bir kod oyun içinde oyuncuya iğrenç hissettirebilir (örn: Player hareketinde AddForce kullanmak).
        Mimari kararlarını verirken teknik doğruluğun yanında kesinlikle "Oyun Hissiyatını" merkeze koy.

        {lang_instr}

        [KULLANICI İSTEĞİ]
        {prompt}

        [KURALLAR]
        {rules}

        # ÇIKTI FORMATI (KESİNLİKLE UYULMALI)

        ## ADIM 0 — KULLANICI İSTEKLERİNİ ÇIKAR (ATLANAMAZ)
        Kullanıcının mesajındaki her açık isteği numaralandır:
        İSTEK-1: [kullanıcının tam olarak istediği özellik]
        İSTEK-2: [kullanıcının tam olarak istediği özellik]
        ...
        TOPLAM: X istek

        Bu liste ADIM 3'teki doğrulamada kullanılacak. Hiçbir isteği bu listeden çıkarma.

        ## ADIM 1 — GEREKSİNİM ÇIKARIMI
        Kullanıcının istediği her özelliği iki gruba ayır:

        [OYUNCU MEKANİKLERİ]
        GEREKSİNİM-P1: [özellik] → PlanlananDosya.cs
        GEREKSİNİM-P2: [özellik] → PlanlananDosya.cs
        ...

        [OYUN/DÜNYA SİSTEMLERİ]
        GEREKSİNİM-W1: [özellik] → PlanlananDosya.cs
        GEREKSİNİM-W2: [özellik] → PlanlananDosya.cs
        ...

        KURAL: Her gereksinim bir dosyaya bağlanmalı. Hiçbiri karşılıksız kalmasın.

        ## ADIM 2 — İKİ BÖLÜMLÜ MİMARİ PLAN

        İlk satır MUTLAKA: "ANA SİSTEM: <kullanıcının istediği sistem>"

        ### == BÖLÜM A: OYUNCU MEKANİKLERİ ==
        [BU BÖLÜM ASLA BOŞ BIRAKILAMAZ]
        Karakter sınıfları, yetenekler, stat sistemi, envanter, ekipman, save/load, kontroller...
        Her dosya için: adı, ne iş yapar, ana metotlar, diğer dosyalarla interface'i.

        ### == BÖLÜM B: OYUN/DÜNYA SİSTEMLERİ ==
        [BU BÖLÜM ASLA BOŞ BIRAKILAMAZ]
        Düşman AI, spawner, loot, level/oda sistemi, status efektleri, boss...
        Her dosya için: adı, ne iş yapar, ana metotlar, BÖLÜM A dosyalarıyla interface'i.

        ## ADIM 3 — KAPSAM DOĞRULAMA (ATLANAMAZ)
        ADIM 0'daki her İSTEK-N için kontrol et:
        ✅ İSTEK-1: [özellik] → karşılayan dosya(lar): [DosyaAdi.cs]
        ✅ İSTEK-2: [özellik] → karşılayan dosya(lar): [DosyaAdi.cs]
        ❌ İSTEK-N: [özellik] → DOSYA YOK — hemen ADIM 2'ye ekle, sonra buraya dön

        Tüm istekler ✅ olduktan sonra MUTLAKA:
        DOSYALAR: DosyaAdi1.cs | DosyaAdi2.cs | ...
        SEN KOD YAZMA!
        """
        
        try:
            plan = self.provider.analyze_code(system_prompt, max_tokens=16384)
            return plan
        except Exception as e:
            logger.error(f"[Architect - Gen] Hata: {e}")
            return f"Planlama başarısız oldu: {str(e)}"
