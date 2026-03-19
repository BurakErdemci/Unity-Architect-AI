import unittest
import sys
import os

# App dizinini path'e ekle
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../app')))

from pipelines.agents.intent_classifier import IntentClassifierAgent

class TestIntentClassifier(unittest.TestCase):

    def setUp(self):
        self.classifier = IntentClassifierAgent(provider=None)

    def test_intent_pure_greeting(self):
        """Sadece selamlama mesajları."""
        self.assertEqual(self.classifier._static_prefilter("merhaba"), "GREETING")
        self.assertEqual(self.classifier._static_prefilter("Selam!"), "GREETING")
        self.assertEqual(self.classifier._static_prefilter("hi"), "GREETING")

    def test_intent_out_of_scope(self):
        """Kapsam dışı (Unity ile ilgisi olmayan) mesajlar."""
        self.assertEqual(self.classifier._static_prefilter("python ile web sitesi nasıl yapılır?"), "OUT_OF_SCOPE")
        self.assertEqual(self.classifier._static_prefilter("yemek tarifi verir misin"), "OUT_OF_SCOPE")

    def test_intent_ambiguous_goes_to_llm(self):
        """Karışık mesajlar statik filtreyi geçip LLM'e (None) gitmeli."""
        # Selamlama + İstek
        self.assertIsNone(self.classifier._static_prefilter("merhaba bana bir zıplama kodu yaz"))
        # Unity kavramı içeren soru
        self.assertIsNone(self.classifier._static_prefilter("Raycast nedir?"))

    def test_intent_parse_logic(self):
        """LLM yanıtından intent'i doğru ayıklama."""
        # Doğrudan büyük harf
        self.assertEqual(self.classifier._parse_intent("GENERATION"), "GENERATION")
        # Açıklamalı yanıt
        self.assertEqual(self.classifier._parse_intent("Bu bir GENERATION kategori."), "GENERATION")
        # Küçük harf ve noktalama
        self.assertEqual(self.classifier._parse_intent("  Greeting!  "), "GREETING")
        # Geçersiz yanıt -> Fallback CHAT
        self.assertEqual(self.classifier._parse_intent("Bilmiyorum"), "CHAT")

if __name__ == '__main__':
    unittest.main()
