import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from tools.tool_registry import _sanitize_gemini_schema


class TestGeminiSanitize(unittest.TestCase):
    def test_strips_unsupported_keeps_core(self):
        raw = {
            "type": "object",
            "title": "ManageGO",
            "additionalProperties": False,
            "$defs": {"X": {"type": "object"}},
            "properties": {
                "action": {"type": "string", "enum": ["create", "delete"], "title": "Action"},
                "count": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": 1},
                "ref": {"$ref": "#/$defs/X"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["action", "ghost"],
        }
        s = _sanitize_gemini_schema(raw)
        self.assertEqual(s["type"], "object")
        self.assertNotIn("title", s)
        self.assertNotIn("additionalProperties", s)
        self.assertNotIn("$defs", s)
        p = s["properties"]
        self.assertEqual(p["action"]["enum"], ["create", "delete"])
        self.assertNotIn("title", p["action"])
        self.assertEqual(p["count"]["type"], "integer")        # anyOf → integer
        self.assertTrue(p["count"].get("nullable"))
        self.assertEqual(p["ref"]["type"], "string")           # $ref → string fallback
        self.assertEqual(p["tags"]["type"], "array")
        self.assertEqual(p["tags"]["items"]["type"], "string")
        self.assertEqual(s["required"], ["action"])            # 'ghost' (prop'ta yok) elendi

    def test_type_list_nullable(self):
        s = _sanitize_gemini_schema({"type": ["string", "null"]})
        self.assertEqual(s["type"], "string")
        self.assertTrue(s.get("nullable"))

    def test_non_dict_and_empty(self):
        self.assertEqual(_sanitize_gemini_schema(None)["type"], "string")
        self.assertEqual(_sanitize_gemini_schema({"type": "object"})["properties"], {})


if __name__ == "__main__":
    unittest.main()
