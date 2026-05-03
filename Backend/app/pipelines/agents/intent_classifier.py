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

    - GREETING     : Sadece selamlama
    - GENERATION   : Kod üretme isteği (ŞİMDİ yaz)
    - ANALYSIS     : Mevcut kodu detaylı analiz et, rapor çıkar
    - FIX          : Belirtilen hatayı düzelt
    - CHAT         : Unity ile ilgili genel soru, planlama, fikir alışverişi
    - OUT_OF_SCOPE : Unity/C# dışı konular
    """

    INTENT_PROMPT = """Sen bir metin sınıflandırıcısın. Kullanıcının mesajını analiz edip,
TAM OLARAK aşağıdaki 6 kategoriden BİRİNİ döndür. Başka hiçbir şey yazma.

KATEGORİLER:
- GREETING     → Sadece selamlama, hal hatır sorma, teşekkür etme.
- GENERATION   → Kullanıcı ŞİMDİ bir kod, script veya sistem YAZILMASINI istiyorsa.
- ANALYSIS     → Mevcut kodu detaylı analiz etmek, rapor çıkarmak istiyorsa.
- FIX          → Belirli bir hatayı, bug'ı düzeltmek istiyorsa.
- CHAT         → Unity ile ilgili genel soru, kavram açıklaması, FİKİR ALIŞVERİŞİ, PLANLAMA veya BAĞLAM kurma.
- OUT_OF_SCOPE → Mesaj Unity/C# ile hiç ilgisi yoksa.

ÖNEMLİ KURALLAR:
1. "Kuracağız", "yapacağız", "mimariyi konuşalım", "aklınızda bulunsun" gibi cümleler GENERATION değildir! Bunlar CHAT (Planlama/Bağlam) kategorisidir.
2. Sadece "yaz", "oluştur", "kodunu ver", "kod üret" gibi NET EMİRLER varsa GENERATION seç.
3. Kullanıcı bir hatadan bahsediyorsa veya "neden çalışmıyor" diyorsa FIX seç.
4. Eğer mesaj hem selamlama hem iş içeriyorsa işin türünü seç.
5. Emin değilsen CHAT seç. Kullanıcıyı dinlemek, hemen kod üretmekten daha güvenlidir.

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
        """
        q = message.lower().strip()
        q_clean = re.sub(r'[!?.,:;]', '', q).strip()
        words = q_clean.split()
        
        if len(words) <= 3 and q_clean in _PURE_GREETINGS:
            return "GREETING"
        
        if len(words) == 1 and words[0] in _PURE_GREETINGS:
            return "GREETING"
        
        unity_keywords = ["unity", "c#", "csharp", "gameobject", "monobehaviour", "oyun", "game"]
        has_unity_context = any(kw in q for kw in unity_keywords)
        has_out_of_scope = any(kw in q for kw in _OUT_OF_SCOPE_KEYWORDS)
        
        if has_out_of_scope and not has_unity_context and len(words) < 20:
            return "OUT_OF_SCOPE"
        
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
        valid_intents = {"GREETING", "GENERATION", "ANALYSIS", "FIX", "CHAT", "OUT_OF_SCOPE"}
        
        first_word = clean.split()[0] if clean.split() else ""
        first_word = re.sub(r'[^A-Z_]', '', first_word)
        
        if first_word in valid_intents:
            return first_word
        
        for intent in valid_intents:
            if intent in clean:
                return intent
        
        return "CHAT"
