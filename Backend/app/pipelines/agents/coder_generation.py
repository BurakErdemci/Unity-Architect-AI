import logging
from typing import Any

logger = logging.getLogger(__name__)

class CoderGenerationAgent:
    """
    Mimardan gelen plana göre sıfırdan hatasız ve best-practice C# kodu üreten ajan.
    """
    def __init__(self, provider: Any):
        self.provider = provider
        
    def generate_code(self, user_prompt: str, architecture_plan: str, lang_instr: str, rules: str, max_tokens: int = 8192) -> str:
        logger.info(f"  [Coder - Gen] Sıfırdan Kod üretiliyor (Limit: {max_tokens})...")
        
        prompt = f"""
        # GÖREV: MİMARİ PLANA GÖRE SIFIRDAN C# KODUNU ÜRETMESİ

        Aşağıda kullanıcının orijinal fikri ve Baş Mimarın (Architect) bu fikir için çıkardığı "Tasarım Planı" bulunuyor.
        Görevin, sadece bu plana ve Best Practice kurallarına uyarak kodun EN İYİ (Enterprise Level) halini sıfırdan yazmaktır.
        Hiçbir şeyi yarım bırakma, tüm metotların içini doldur.

        [DİL TALİMATI]: {lang_instr}

        # MİMARIN TASARIM PLANI
        {architecture_plan}

        # KULLANICI İSTEĞİ
        {user_prompt}

        {rules}

        # TOKEN LİMİTİ — ANLAMLI BİTİŞ
        Eğer tüm sistemi tek yanıtta TAMAMLAYAMAZSAN:
        1. En önemli ve tam çalışır parçayı yaz (yarım metot, açık süslü parantez, syntax hatası ASLA bırakma).
        2. Yanıtının en sonuna şu bölümü ekle:
           ⏳ **Devam:** [Yazılmayan dosya/class adlarını listele]
           Devam edeyim mi? ✋
        3. Eğer tüm sistemi yazabilirsen bu bölümü EKLEME.

        # ÇIKTI FORMATI (KESİNLİKLE UYULMALI)

        Cevabını DOĞRUDAN kullanıcıya söyler gibi tek bir cümle ile başlat. (Örn: "İşte diyalog sisteminiz:")

        Ardından HER DOSYA İÇİN şu formatı kullan — HİÇBİR İSTİSNA YOK:

        **📄 DosyaAdi.cs**
        ```csharp
        // tam ve çalışan kod buraya
        ```

        KURALLLAR:
        - Sistemde kaç dosya varsa HER BİRİ ayrı bir ```csharp bloğu olmalı. ASLA tek blokta birleştirme.
        - Her bloğun üstünde **📄 FileName.cs** başlığı ZORUNLU.
        - Her dosya kendi using ifadelerini içermeli (diğer dosyadan kopyalama değil, o dosyaya gerçekten gerekli olanlar).
        - Tek dosyalık basit sistemlerde yine tek ```csharp bloğu kullan (başlık yine **📄 FileName.cs** şeklinde olsun).
        - Tüm kodun altına "🎮 Editor Ayarları" diye 1-3 maddelik kurulum notu yaz.

        KESİNLİKLE YAPMA: Kodun nasıl çalıştığını uzun uzun anlatma. Merhaba/Güle güle deme.
        KESİNLİKLE YAPMA: Planda belirtilmemiş ekstra dosya veya script oluşturma. Sadece verilen DOSYALAR listesindeki dosyaları üret.
        """
        
        try:
            generated_response = self.provider.analyze_code(prompt, max_tokens=max_tokens)
            return generated_response
        except Exception as e:
            logger.error(f"[Coder - Gen] Hata: {e}")
            return f"❌ Kod üretimi başarısız oldu: {str(e)}"
