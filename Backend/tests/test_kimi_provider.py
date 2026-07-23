"""Kimi CLI, Moonshot ve yeni Gemini model entegrasyonu birim testleri."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestManagerRouting(unittest.TestCase):
    def test_kimi_subscription_routing(self):
        from providers.kimi_provider import KimiProvider
        from providers.manager import AIProviderManager

        for model_name in ("kimi-k3", "kimi-k2.7-code"):
            provider = AIProviderManager.get_provider({
                "provider_type": "subscription",
                "model_name": model_name,
            })
            self.assertIsInstance(provider, KimiProvider)

    def test_moonshot_endpoint(self):
        from providers.api_providers import OpenAICompatibleProvider
        from providers.manager import AIProviderManager

        provider = AIProviderManager.get_provider({
            "provider_type": "moonshot",
            "api_key": "x",
            "model_name": "kimi-k3",
        })
        self.assertIsInstance(provider, OpenAICompatibleProvider)
        self.assertEqual(provider.base_url, "https://api.moonshot.ai/v1")


class TestApiProviders(unittest.TestCase):
    def test_kimi_detection(self):
        from providers.api_providers import OpenAICompatibleProvider

        k3 = OpenAICompatibleProvider(
            api_key="x",
            base_url="https://api.moonshot.ai/v1",
            model_name="kimi-k3",
        )
        self.assertTrue(k3._is_kimi())
        self.assertTrue(k3._is_kimi_k3())

        k2 = OpenAICompatibleProvider(
            api_key="x",
            base_url="https://api.moonshot.ai/v1",
            model_name="kimi-k2.6",
        )
        self.assertTrue(k2._is_kimi())
        self.assertFalse(k2._is_kimi_k3())

    def test_gemini_model_normalization(self):
        from providers.api_providers import GeminiProvider

        self.assertEqual(
            GeminiProvider(api_key="x", model_name="gemini-3.6-flash").model_id,
            "gemini-3.6-flash",
        )
        self.assertEqual(
            GeminiProvider(api_key="x", model_name="gemini-3.5-flash-lite").model_id,
            "gemini-3.5-flash-lite",
        )


class TestKimiProvider(unittest.TestCase):
    def test_build_cmd(self):
        from providers.kimi_provider import KimiProvider

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.dict(os.environ, {"KIMI_CODE_HOME": tmpdir}), \
             patch(
                 "unity_ai_mcp.unity_mcp_manager.unity_mcp_manager.is_running",
                 return_value=False,
             ), \
             patch.object(KimiProvider, "_ensure_exec"):
            cmd = KimiProvider(binary_name="kimi-k3")._build_cmd(
                "HELLO_PROMPT",
                workspace=tmpdir,
            )

        expected_order = [
            "kimi",
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            "-m",
            "kimi-k3",
            "-p",
        ]
        positions = [cmd.index(item) for item in expected_order]
        self.assertEqual(positions, sorted(positions))
        prompt = cmd[cmd.index("-p") + 1]
        self.assertTrue(prompt.endswith("HELLO_PROMPT"))
        self.assertIn("mcp__unityai__save_file", prompt)

    def test_write_kimi_permissions_is_idempotent(self):
        from providers.kimi_provider import KimiProvider

        existing = '[providers.kimi]\napi_key="x"\n'
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.dict(os.environ, {"KIMI_CODE_HOME": tmpdir}):
            config_path = os.path.join(tmpdir, "config.toml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write(existing)

            provider = KimiProvider(binary_name="kimi-k3")
            provider._write_kimi_permissions()
            provider._write_kimi_permissions()

            with open(config_path, "r", encoding="utf-8") as config_file:
                content = config_file.read()

        self.assertIn(existing, content)
        self.assertEqual(content.count(provider._KIMI_MANAGED_MARKER), 1)
        self.assertIn('decision = "deny"', content)
        self.assertIn('pattern = "Write"', content)
        self.assertIn('pattern = "mcp__unityai__*"', content)


if __name__ == "__main__":
    unittest.main()
