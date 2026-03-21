"""
Intent Classifier Agent — LLM tabanlı niyet tespiti.

Mevcut keyword-based sistemin yerine geçer.
"Merhaba, bana şu sistemi kur" gibi karışık cümlelerde
asıl niyeti (GENERATION) doğru tespit eder.
"""
import logging
import re
import asyncio
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─── Hızlı Statik Ön-Filtre (LLM çağrısını atlamak için) ───
# Sadece pür selamlama veya pür kapsam dışı cümleler buradan döner.
# Karışık cümleler LLM'e gider.

_PURE_GREETINGS = {
    "merhaba", "selam", "hi", "hello", "hey", "selamlar",
    "nasılsın", "nasılsın?", "naber", "naber?",
    "merhaba!", "selam!", "hey!", "hi!",
    "eyw", "saol", "sağol", "teşekkürler", "teşekkür ederim",
    "iyi günler", "günaydın", "iyi akşamlar",
    "sa", "as", "mrb",
}

_OUT_OF_SCOPE_KEYWORDS = [
    "unreal", "godot", "python", "react", "django", "javascript",
    "html", "css", "flutter", "swift", "kotlin", "rust",
    "yemek", "tarif", "siyaset", "futbol", "hava durumu",
]


class IntentClassifierAgent:
    """
    Kullanıcı mesajını aşağıdaki kategorilere sınıflandırır:
    
    - GREETING     : Sadece selamlama (merhaba, selam, nasılsın)
    - GENERATION   : Kod üretme isteği (yaz, oluştur, kur, yap)
    - ANALYSIS     : Mevcut kodu analiz etme / hata bulma
    - CHAT         : Unity ile ilgili genel soru-cevap
    - OUT_OF_SCOPE : Unity/C# dışı konular
    """
    
    INTENT_PROMPT = """Sen bir metin sınıflandırıcısın. Kullanıcının mesajını analiz edip,
TAM OLARAK aşağıdaki 5 kategoriden BİRİNİ döndür. Başka hiçbir şey yazma.

KATEGORİLER:
- GREETING     → Mesajın TEK amacı selamlama, hal hatır sorma, teşekkür etme ise
- GENERATION   → Kullanıcı yeni bir kod, script, sistem, class yazılmasını istiyorsa
- ANALYSIS     → Kullanıcı mevcut bir kodu incelemek, hataları bulmak, optimize etmek istiyorsa
- CHAT         → Unity/C# ile ilgili genel bilgi sorusu, kavram açıklaması istiyorsa
- OUT_OF_SCOPE → Mesaj Unity/C# ile hiç ilgisi yoksa (yemek, siyaset, başka diller gibi)

ÖNEMLİ KURALLAR:
1. Mesaj selamlama İÇERSE AMA başka bir istek de varsa → o isteğin türünü seç (GREETING değil!)
   Örnek: "Merhaba, bana bir hareket sistemi yazar mısın?" → GENERATION
   Örnek: "Selam, Raycast nedir?" → CHAT
2. Mesajda "yaz", "kur", "oluştur", "yap", "geliştir", "ekle", "implement" gibi fiiller varsa → GENERATION
3. Mesajda "analiz et", "incele", "kontrol et", "hata bul", "optimize et" gibi fiiller varsa → ANALYSIS
4. Mesajda Unity kavramları (Raycast, GetComponent, Coroutine vb.) geçip basit bir açıklama isteniyorsa → CHAT

KULLANICI MESAJI:
"{message}"

CEVAP (tek kelime):"""

    def __init__(self, provider: Any):
        self.provider = provider

    def classify(self, message: str) -> str:
        """Senkron sınıflandırma — önce statik filtre, sonra LLM."""
        # 1. Hızlı statik ön-filtre
        static_result = self._static_prefilter(message)
        if static_result:
            logger.info(f"  [IntentClassifier] Statik filtre sonucu: {static_result}")
            return static_result
        
        # 2. LLM tabanlı sınıflandırma
        return self._llm_classify(message)
    
    async def classify_async(self, message: str) -> str:
        """Asenkron sınıflandırma — thread pool ile."""
        static_result = self._static_prefilter(message)
        if static_result:
            logger.info(f"  [IntentClassifier] Statik filtre sonucu: {static_result}")
            return static_result
        
        return await asyncio.to_thread(self._llm_classify, message)

    def _static_prefilter(self, message: str) -> Optional[str]:
        """
        Çok net durumları LLM'e sormadan yakalar.
        Sadece tek kelime / kısa selamlama veya açıkça kapsam dışı mesajlar.
        Karışık mesajlar (selamlama + istek) buradan geçer → LLM karar verir.
        """
        q = message.lower().strip()
        q_clean = re.sub(r'[!?.,:;]', '', q).strip()
        words = q_clean.split()
        
        # Pür selamlama: 1-3 kelime ve hepsi selamlama sözlüğünde
        if len(words) <= 3 and q_clean in _PURE_GREETINGS:
            return "GREETING"
        
        # Pür selamlama (tek kelime eşleşme)
        if len(words) == 1 and words[0] in _PURE_GREETINGS:
            return "GREETING"
        
        # Açıkça kapsam dışı (Unity kelimesi yoksa + kapsam dışı kelime varsa)
        unity_keywords = ["unity", "c#", "csharp", "gameobject", "monobehaviour", "oyun", "game"]
        has_unity_context = any(kw in q for kw in unity_keywords)
        has_out_of_scope = any(kw in q for kw in _OUT_OF_SCOPE_KEYWORDS)
        
        if has_out_of_scope and not has_unity_context and len(words) < 20:
            return "OUT_OF_SCOPE"
        
        # Kod içeren mesajlarda intent tespiti (LLM'siz)
        # "analiz et", "incele", "kontrol et" gibi fiiller + Unity kodu = ANALYSIS
        code_indicators = ["{", "}", "void ", "class ", "using "]
        has_code = sum(1 for ind in code_indicators if ind in message) >= 2

        if has_code:
            analysis_words = [
                "analiz", "incele", "kontrol", "bak", "hata bul", "optimize",
                "review", "check", "değerlendir", "nasıl", "ne dersin",
                "düzelt", "iyileştir", "sorun", "yanlış", "hatalı",
            ]
            generation_words = [
                "yaz", "oluştur", "kur", "yap", "geliştir", "ekle",
                "implement", "create", "generate", "build",
            ]
            q_lower = q

            if any(w in q_lower for w in analysis_words):
                return "ANALYSIS"
            if any(w in q_lower for w in generation_words):
                return "GENERATION"
            # Kod var ama yönlendirme yok → varsayılan olarak analiz
            return "ANALYSIS"

        # Karışık veya belirsiz → LLM'e bırak
        return None
    
    def _llm_classify(self, message: str) -> str:
        """LLM'e sorarak sınıflandır."""
        prompt = self.INTENT_PROMPT.format(message=message)
        
        try:
            response = self.provider.analyze_code(prompt)
            intent = self._parse_intent(response)
            logger.info(f"  [IntentClassifier] LLM sonucu: {intent} (ham: '{response.strip()[:50]}')")
            return intent
        except Exception as e:
            logger.error(f"  [IntentClassifier] LLM hatası, fallback CHAT: {e}")
            return "CHAT"
    
    def _parse_intent(self, response: str) -> str:
        """LLM yanıtından temiz bir intent çıkar."""
        if not response:
            return "CHAT"
        
        clean = response.strip().upper()
        
        # Doğrudan eşleşme
        valid_intents = {"GREETING", "GENERATION", "ANALYSIS", "CHAT", "OUT_OF_SCOPE"}
        
        # İlk kelimeye bak (LLM bazen açıklama ekleyebilir)
        first_word = clean.split()[0] if clean.split() else ""
        # Noktalama temizle
        first_word = re.sub(r'[^A-Z_]', '', first_word)
        
        if first_word in valid_intents:
            return first_word
        
        # Yanıtta geçen intent'i ara
        for intent in valid_intents:
            if intent in clean:
                return intent
        
        # Hiçbiri bulunamazsa güvenli fallback
        return "CHAT"
