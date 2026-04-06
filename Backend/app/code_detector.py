"""
Code Detector — Unity C# Kod Tespit ve Intent Sınıflandırma
============================================================

Bir metnin Unity C# kodu olup olmadığını ve kullanıcı niyetini
(intent) belirleyen sınıf.

Bu modül sadece TESPİT yapar — analiz, düzeltme veya üretim
işleri ilgili modüllere (analyzer.py, pipelines/, knowledge/)
devredilir.

Kullanım:
    from code_detector import CodeDetector

    if CodeDetector.is_csharp(text):
        # UnityAnalyzer'a gönder
    intent = CodeDetector.detect_intent(text)
"""

import re


class CodeDetector:
    """
    Unity C# kod tespiti ve temel intent sınıflandırması.

    Tüm metodlar statik — instantiate gerekmez.
    """

    # ─── C# Tespit Sabitleri ──────────────────────────────────────────────────

    # Genel programlama belirteçleri (en az 2 tanesi olmalı)
    _GENERAL_INDICATORS = ["{", "}", ";"]

    # Unity'ye özgü belirteçler (en az 1 tanesi olmalı)
    _UNITY_INDICATORS = [
        "using UnityEngine",
        "MonoBehaviour",
        "SerializeField",
        "void Update",
        "void Start",
        "GetComponent",
    ]

    # ─── Intent Sabitleri ─────────────────────────────────────────────────────

    _OUT_OF_SCOPE_TERMS = [
        "unreal", "godot", "python", "react", "django",
        "javascript", "html", "css", "atatürk", "yemek",
        "haber", "güncel", "siyaset",
    ]

    _GREETING_WORDS = [
        "selam", "merhaba", "hi", "hey", "nasılsın", "kimsin",
        "eyw", "saol", "teşekkür", "thanks", "hello",
    ]

    # ─── C# Tespit ────────────────────────────────────────────────────────────

    @classmethod
    def is_csharp(cls, text: str) -> bool:
        """
        Metnin gerçekten Unity C# kodu olup olmadığını belirler.

        Kural:
          - Genel belirteçlerden en az 2'si VE
          - Unity'ye özgü belirteçlerden en az 1'i bulunmalı
        """
        general_score = sum(1 for ind in cls._GENERAL_INDICATORS if ind in text)
        unity_score = sum(1 for ind in cls._UNITY_INDICATORS if ind in text)
        return general_score >= 2 and unity_score >= 1

    # ─── Intent Tespiti ───────────────────────────────────────────────────────

    @classmethod
    def detect_intent(cls, query: str) -> str:
        """
        Kullanıcı mesajının temel niyetini belirler.

        Dönüş değerleri:
          "OUT_OF_SCOPE" — Unity/C# dışı konu
          "GREETING"     — Selamlama / sosyal mesaj
          "GENERATION"   — Kod üretim isteği
          "ANALYSIS"     — Kod analiz isteği (varsayılan)
        """
        q = query.lower().strip()

        # Kapsam dışı
        if any(term in q for term in cls._OUT_OF_SCOPE_TERMS):
            return "OUT_OF_SCOPE"

        # Selamlama (kısa mesaj + selamlama kelimesi)
        # q.split() ile kelime bazlı kontrol — substring false positive'ini önler
        # Örnek: "hi" in "machine" → YANLIŞ, "hi" in ["hi", "there"] → DOĞRU
        q_words = set(q.split())
        if any(word in q_words for word in cls._GREETING_WORDS) and len(q_words) < 15:
            return "GREETING"

        # Kod üretim isteği
        if cls._is_generation_request(q):
            return "GENERATION"

        return "ANALYSIS"

    @staticmethod
    def _is_generation_request(q: str) -> bool:
        """Üretim isteği sinyallerini kontrol eder."""
        generation_signals = [
            # Türkçe fiiller
            "yaz", "oluştur", "yarat", "üret", "ekle", "kodla",
            "yap", "kur", "hazırla", "geliştir", "implement et",
            "sistemi yap", "sistemi kur", "sistemi oluştur",
            "nasıl yapılır", "nasıl yazılır",
            # İngilizce
            "write", "create", "generate", "make", "build",
            "implement", "setup", "add",
            # Kalıplar
            "örnek ver", "örnek kod", "kod ver", "kod yaz",
        ]
        return any(sig in q for sig in generation_signals)

    # ─── Kod İçeriği Analizi (İleri Tespit) ──────────────────────────────────

    @staticmethod
    def extract_code(text: str) -> str:
        """
        Kullanıcı mesajından C# kod bloğunu çıkarır.
        ```csharp ... ``` veya ``` ... ``` bloğu varsa içeriği döner,
        yoksa orijinal metni döner (zaten saf kod gönderilmiş olabilir).
        """
        m = re.search(r'```(?:csharp|cs)?\s*\n([\s\S]*?)\n```', text)
        if m:
            return m.group(1)
        return text

    @staticmethod
    def extract_class_name(code: str) -> str:
        """C# kodundan sınıf adını çıkarır."""
        match = re.search(r"class\s+(\w+)", code)
        return match.group(1) if match else "UnknownScript"

    @staticmethod
    def extract_unity_apis(code: str) -> set:
        """
        Kodda kullanılan Unity API sınıf adlarını çıkarır.
        KB eşleştirmesi için kullanılır.
        """
        api_pattern = re.compile(
            r"\b(Rigidbody2D|Rigidbody|CharacterController|AudioSource|AudioClip|"
            r"Animator|NavMeshAgent|Canvas|CanvasGroup|SceneManager|Physics2D|Physics|"
            r"Coroutine|WaitForSeconds|ScriptableObject|PlayerPrefs|JsonUtility|"
            r"NavMesh|Collider2D|Collider|Transform|Camera|UI)\b"
        )
        return set(api_pattern.findall(code))
