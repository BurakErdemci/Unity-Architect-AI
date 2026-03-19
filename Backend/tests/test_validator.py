import unittest
import sys
import os

# App dizinini path'e ekle
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../app')))

from validator import ResponseValidator

class TestResponseValidator(unittest.TestCase):

    def test_validate_success(self):
        """Doğru formatlanmış C# kodu."""
        text = "```csharp\npublic class Test : MonoBehaviour {}\n```"
        success, issues = ResponseValidator.validate(text)
        self.assertTrue(success)
        self.assertEqual(len(issues), 0)

    def test_validate_no_code_block(self):
        """Kod bloğu olmayan yanıt."""
        text = "Bu sadece düz bir yazı, kod içermiyor."
        success, issues = ResponseValidator.validate(text)
        self.assertFalse(success)
        self.assertIn("Kod bloğu (```csharp) eksik.", issues)

    def test_validate_lazy_code(self):
        """AI'nın kodda ... kullanarak kolaya kaçması."""
        text = "```csharp\nvoid Start() {\n    ...\n}\n```"
        success, issues = ResponseValidator.validate(text)
        self.assertFalse(success)
        self.assertTrue(any("yarım bırakılmış" in issue for issue in issues))

    def test_code_integrity_braces(self):
        """Süslü parantez dengesizliği."""
        code = "public class Test { void Update() { "
        issues = ResponseValidator._check_code_integrity(code)
        self.assertTrue(any("parantez dengesi bozuk" in issue for issue in issues))

    def test_unity_fixed_update_input(self):
        """Unity Best Practice: FixedUpdate içinde Input olmamalı."""
        code = "void FixedUpdate() { if (Input.GetKeyDown(KeyCode.Space)) Jump(); }"
        issues = ResponseValidator._check_code_integrity(code)
        self.assertTrue(any("FixedUpdate içinde hala Input" in issue for issue in issues))

    def test_json_extraction_markdown(self):
        """Markdown içindeki JSON'ı parse etme."""
        text = "```json\n{\"score\": 8.0, \"status\": \"ok\"}\n```"
        success, result = ResponseValidator.validate_json_response(text)
        self.assertTrue(success)
        self.assertEqual(result["score"], 8.0)

    def test_json_recovery_from_text(self):
        """Etrafında yazı olan JSON'ı kurtarma."""
        text = "Rapor sonucu: {\"score\": 7.5} Teşekkürler."
        success, result = ResponseValidator.validate_json_response(text)
        self.assertTrue(success)
        self.assertEqual(result["score"], 7.5)

    def test_json_recovery_with_newlines(self):
        """Tırnak içinde unescaped newline olan JSON'ı kurtarma (Kritik Case)."""
        # json.loads normalde burada hata verir çünkü "msg" içindeki newline escape edilmemiş.
        text = '{"msg": "Merhaba\nDünya", "score": 5.0}'
        success, result = ResponseValidator.validate_json_response(text)
        self.assertTrue(success)
        # Parse edildikten sonra içerideki \\n gerçek bir newline (\n) olur.
        self.assertEqual(result["msg"], "Merhaba\nDünya")
        self.assertEqual(result["score"], 5.0)

if __name__ == '__main__':
    unittest.main()
