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
        
        # ÇIKTI FORMATI (ÇOK ÖNEMLİ - GEREKSİZ SOHBET YASAK)
        Lütfen cevabını DOĞRUDAN KULLANICIYA SÖYLEYECEKMİŞ GİBİ tek bir cümle ile başlat. (Örn: "İşte oyun hissiyatı ön planda olan sisteminiz:")
        Ardından HEMEN ```csharp kod bloğu halinde tam ve çalışan kodu ver.
        Kodun altına "🎮 Editor Ayarları" diye sadece 1-2 maddelik, objeye eklenecek componentleri yaz.
        
        KESİNLİKLE YAPMA: Kodun nasıl çalıştığını uzun uzun anlatma. Merhaba/Güle güle deme. Sadece Mimarın planını harmanla ve KODU VER.
        """
        
        try:
            generated_response = self.provider.analyze_code(prompt, max_tokens=max_tokens)
            return generated_response
        except Exception as e:
            logger.error(f"[Coder - Gen] Hata: {e}")
            return f"❌ Kod üretimi başarısız oldu: {str(e)}"
