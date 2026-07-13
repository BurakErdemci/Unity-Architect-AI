"""Cursor / Copilot / OpenCode entegrasyonu birim testleri.

Kapsam:
  1. Model ID eşlemesi (split_model_id)
  2. Manager routing (subscription prefix'leri doğru provider'a gider)
  3. Komut satırı inşası (_build_cmd) — resume/session bayrakları
  4. cli_base JSON event parser — canlı yakalanan GERÇEK event örnekleriyle
     (2026-07-13 canlı problardan alındı)
"""
import os
import sys
import json
import asyncio
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestSplitModelId(unittest.TestCase):
    def test_cursor(self):
        from providers.oneshot_cli import split_model_id
        self.assertEqual(split_model_id("cursor-composer-2.5"), ("cursor", "composer-2.5"))
        # Cursor'ın kendi id'si zaten cursor- ile başlayanlar (cursor-grok-4.5-high)
        self.assertEqual(split_model_id("cursor-cursor-grok-4.5-high"), ("cursor", "cursor-grok-4.5-high"))

    def test_copilot(self):
        from providers.oneshot_cli import split_model_id
        self.assertEqual(split_model_id("copilot-claude-sonnet-5"), ("copilot", "claude-sonnet-5"))
        self.assertEqual(split_model_id("copilot-auto"), ("copilot", "auto"))

    def test_opencode(self):
        from providers.oneshot_cli import split_model_id
        self.assertEqual(split_model_id("opencode:opencode/big-pickle"), ("opencode", "opencode/big-pickle"))
        self.assertEqual(split_model_id("opencode:google/gemini-3.5-flash"), ("opencode", "google/gemini-3.5-flash"))

    def test_unknown(self):
        from providers.oneshot_cli import split_model_id
        self.assertEqual(split_model_id("claude-sonnet-5"), (None, "claude-sonnet-5"))


class TestManagerRouting(unittest.TestCase):
    def _get(self, model):
        from providers.manager import AIProviderManager
        return AIProviderManager.get_provider({"provider_type": "subscription", "model_name": model})

    def test_routing(self):
        from providers.cursor_provider import CursorProvider
        from providers.copilot_provider import CopilotProvider
        from providers.opencode_provider import OpenCodeProvider
        from providers.claude_provider import ClaudeCodeProvider
        from providers.codex_provider import CodexProvider
        self.assertIsInstance(self._get("cursor-composer-2.5"), CursorProvider)
        self.assertIsInstance(self._get("copilot-gpt-5.5"), CopilotProvider)
        self.assertIsInstance(self._get("opencode:opencode/big-pickle"), OpenCodeProvider)
        # Mevcut routing bozulmadı:
        self.assertIsInstance(self._get("gpt-5.5"), CodexProvider)
        self.assertIsInstance(self._get("claude-sonnet-5"), ClaudeCodeProvider)
        # copilot-gpt-* Codex'e DÜŞMEMELİ (prefix önceliği):
        self.assertIsInstance(self._get("copilot-gpt-5.6-sol"), CopilotProvider)

    def test_nvidia_routing(self):
        """NVIDIA NIM → OpenAI-uyumlu provider, doğru base_url ile."""
        from providers.manager import AIProviderManager
        from providers.api_providers import OpenAICompatibleProvider
        p = AIProviderManager.get_provider({
            "provider_type": "nvidia", "api_key": "nvapi-test",
            "model_name": "nvidia/nemotron-3-super-120b-a12b",
        })
        self.assertIsInstance(p, OpenAICompatibleProvider)
        self.assertIn("integrate.api.nvidia.com", getattr(p, "base_url", ""))


def _mock_unity_mcp(running=False):
    """unity_ai_mcp.unity_mcp_manager import'unu mock'lar."""
    m = MagicMock()
    m.unity_mcp_manager.is_running.return_value = running
    m.unity_mcp_manager.mcp_port = 8080
    return patch.dict(sys.modules, {"unity_ai_mcp": MagicMock(unity_mcp_manager=m.unity_mcp_manager),
                                    "unity_ai_mcp.unity_mcp_manager": m})


class TestBuildCmd(unittest.TestCase):
    def test_cursor_cmd_resume(self):
        from providers.cursor_provider import CursorProvider
        p = CursorProvider(binary_name="cursor-composer-2.5")
        p.resume_session_id = "chat-123"
        with _mock_unity_mcp(), \
             patch("providers.cursor_provider.resolve_cursor_cmd", return_value=["C:/node.exe", "C:/index.js"]):
            cmd = p._build_cmd("merhaba", workspace="C:/ws")
        self.assertEqual(cmd[:2], ["C:/node.exe", "C:/index.js"])
        self.assertIn("-p", cmd)
        self.assertIn("--resume", cmd)
        self.assertEqual(cmd[cmd.index("--resume") + 1], "chat-123")
        self.assertEqual(cmd[cmd.index("--model") + 1], "composer-2.5")
        self.assertIn("stream-json", cmd)
        self.assertTrue(cmd[-1].endswith("merhaba"))  # prompt son pozisyonel arg

    def test_cursor_auto_model_explicit(self):
        """'auto' da AÇIKÇA --model auto olarak geçirilir: bayraksız çağrı CLI'ın
        kayıtlı adlı modelini dener ve Free planda patlar (canlı doğrulandı)."""
        from providers.cursor_provider import CursorProvider
        p = CursorProvider(binary_name="cursor-auto")
        with _mock_unity_mcp(), \
             patch("providers.cursor_provider.resolve_cursor_cmd", return_value=["agent"]):
            cmd = p._build_cmd("hi")
        self.assertEqual(cmd[cmd.index("--model") + 1], "auto")

    def test_copilot_first_turn_vs_resume(self):
        from providers.copilot_provider import CopilotProvider
        p = CopilotProvider(binary_name="copilot-claude-sonnet-5")
        p.fresh_session_id = "uuid-1"
        with _mock_unity_mcp(), \
             patch("providers.copilot_provider.resolve_copilot_cmd", return_value=["node", "loader.js"]):
            cmd1 = p._build_cmd("ilk tur")
            p.fresh_session_id = None
            p.resume_session_id = "uuid-1"
            cmd2 = p._build_cmd("ikinci tur")
        self.assertIn("--session-id=uuid-1", cmd1)
        self.assertNotIn("--session-id=uuid-1", cmd2)
        self.assertIn("--resume=uuid-1", cmd2)
        # Yazma/shell reddedilir, unityai'ye izin verilir:
        self.assertIn("write", cmd1[cmd1.index("--deny-tool") + 1])
        self.assertIn("unityai", cmd1)
        # prompt -p'nin değeri:
        self.assertEqual(cmd1[cmd1.index("-p") + 1][-7:], "ilk tur")

    def test_opencode_cmd(self):
        from providers.opencode_provider import OpenCodeProvider
        p = OpenCodeProvider(binary_name="opencode:opencode/big-pickle")
        p.resume_session_id = "ses_abc"
        with _mock_unity_mcp(), \
             patch("providers.opencode_provider.resolve_opencode_cmd", return_value=["opencode.exe"]):
            cmd = p._build_cmd("soru")
        self.assertEqual(cmd[0], "opencode.exe")
        self.assertEqual(cmd[1], "run")
        self.assertEqual(cmd[cmd.index("-m") + 1], "opencode/big-pickle")
        self.assertEqual(cmd[cmd.index("-s") + 1], "ses_abc")
        self.assertIn("--format", cmd)


class TestEventParsing(unittest.TestCase):
    """cli_base.analyze_code'un JSON satırlarını doğru event'lere çevirdiğini,
    sahte bir subprocess'le (echo JSONL) uçtan uca doğrular."""

    def _run_provider(self, provider, jsonl_lines):
        """Provider'ın analyze_code'unu sahte komutla çalıştırıp event listesi döner.
        Sahte komut: python -c ile stdout'a JSONL basar."""
        script = "import sys\n" + "".join(
            f"sys.stdout.write({json.dumps(line + chr(10))})\n" for line in jsonl_lines
        )
        with _mock_unity_mcp(), \
             patch.object(type(provider), "_build_cmd", lambda self, *a, **k: [sys.executable, "-c", script]), \
             patch.object(type(provider), "_write_mcp_config", lambda self, ws: ""):
            async def collect():
                evs = []
                async for ev in provider.analyze_code("test", cwd=os.getcwd()):
                    evs.append(ev)
                return evs
            return asyncio.run(collect())

    def test_cursor_stream(self):
        """Gerçek cursor stream-json örneği: parçalı delta + tam metin tekrarı + result."""
        from providers.cursor_provider import CursorProvider
        p = CursorProvider(binary_name="cursor-composer-2.5")
        sid = "e6301622-314f-4980-8ced-248772b378f1"
        lines = [
            json.dumps({"type": "system", "subtype": "init", "session_id": sid, "model": "Auto"}),
            json.dumps({"type": "thinking", "subtype": "delta", "text": "düşünüyor...", "session_id": sid}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "TAM"}]}, "session_id": sid}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "AM-1"}]}, "session_id": sid}),
            # Cursor'ın tam-metin tekrar event'i (dedup edilmeli):
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "TAMAM-1"}]}, "session_id": sid}),
            json.dumps({"type": "result", "subtype": "success", "result": "TAMAM-1", "session_id": sid}),
        ]
        evs = self._run_provider(p, lines)
        metas = [e for e in evs if e["type"] == "session_meta"]
        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0]["session_id"], sid)
        deltas = "".join(e["text"] for e in evs if e["type"] == "delta")
        self.assertEqual(deltas, "TAMAM-1")  # tam-metin tekrarı MÜKERRER basılmadı
        self.assertTrue(any(e["type"] == "thinking" for e in evs))
        final = [e for e in evs if e["type"] == "final"][0]
        self.assertEqual(final["text"], "TAMAM-1")

    def test_copilot_stream(self):
        """Gerçek copilot JSONL örneği: reasoning delta + message delta + tam mesaj + result."""
        from providers.copilot_provider import CopilotProvider
        p = CopilotProvider(binary_name="copilot-claude-haiku-4.5")
        lines = [
            json.dumps({"type": "session.mcp_servers_loaded", "data": {"servers": []}}),
            json.dumps({"type": "assistant.reasoning_delta", "data": {"reasoningId": "r1", "deltaContent": "kısa düşünce"}}),
            json.dumps({"type": "assistant.message_delta", "data": {"messageId": "m1", "deltaContent": "MERHABA-"}}),
            json.dumps({"type": "assistant.message_delta", "data": {"messageId": "m1", "deltaContent": "42"}}),
            # Tam mesaj (delta'ları akıtıldı → tekrar basılmamalı):
            json.dumps({"type": "assistant.message", "data": {"messageId": "m1", "content": "MERHABA-42", "toolRequests": []}}),
            json.dumps({"type": "result", "sessionId": "0065763b-761e-4c7e-ae1d-b5cc2f455471", "exitCode": 0}),
        ]
        evs = self._run_provider(p, lines)
        deltas = "".join(e["text"] for e in evs if e["type"] == "delta")
        self.assertEqual(deltas, "MERHABA-42")
        metas = [e for e in evs if e["type"] == "session_meta"]
        self.assertEqual(metas[0]["session_id"], "0065763b-761e-4c7e-ae1d-b5cc2f455471")
        self.assertTrue(any("kısa düşünce" in e.get("text", "") for e in evs if e["type"] == "thinking"))
        final = [e for e in evs if e["type"] == "final"][0]
        self.assertEqual(final["text"], "MERHABA-42")

    def test_copilot_message_without_deltas(self):
        """Delta akmadıysa assistant.message'ın tam içeriği basılır (stream=off senaryosu)."""
        from providers.copilot_provider import CopilotProvider
        p = CopilotProvider(binary_name="copilot-auto")
        lines = [
            json.dumps({"type": "assistant.message", "data": {"messageId": "m1", "content": "SELAM"}}),
            json.dumps({"type": "result", "sessionId": "abc", "exitCode": 0}),
        ]
        evs = self._run_provider(p, lines)
        deltas = "".join(e["text"] for e in evs if e["type"] == "delta")
        self.assertEqual(deltas, "SELAM")

    def test_opencode_stream(self):
        """Gerçek opencode --format json örneği: tool_use + text + step_finish."""
        from providers.opencode_provider import OpenCodeProvider
        p = OpenCodeProvider(binary_name="opencode:opencode/big-pickle")
        sid = "ses_0a49b7dfbffe84bVZY1idV7JmY"
        lines = [
            json.dumps({"type": "step_start", "sessionID": sid, "part": {"type": "step-start"}}),
            json.dumps({"type": "tool_use", "sessionID": sid, "part": {"type": "tool", "tool": "bash",
                        "state": {"status": "completed", "title": "Write-Output \"hi\"", "output": "hi\r\n"}}}),
            json.dumps({"type": "text", "sessionID": sid, "part": {"type": "text", "text": "hi"}}),
            json.dumps({"type": "step_finish", "sessionID": sid, "part": {"reason": "stop",
                        "tokens": {"total": 8234, "input": 71, "output": 4}}}),
        ]
        evs = self._run_provider(p, lines)
        metas = [e for e in evs if e["type"] == "session_meta"]
        self.assertEqual(metas[0]["session_id"], sid)
        deltas = "".join(e["text"] for e in evs if e["type"] == "delta")
        self.assertEqual(deltas, "hi")
        hints = [e["text"] for e in evs if e["type"] == "thinking"]
        self.assertTrue(any("bash" in h for h in hints))


class TestModelListParsers(unittest.TestCase):
    def test_cursor_models_parse(self):
        raw = (
            "Available models\n\n"
            "auto - Auto (current, default)\n"
            "gpt-5.3-codex - Codex 5.3\n"
            "gpt-5.3-codex-fast - Codex 5.3 Fast\n"
            "composer-2.5 - Composer 2.5\n"
            "claude-fable-5-thinking-high - Fable 5 1M Thinking (NO ZDR)\n"
        )
        # config_routes içindeki parser'lar closure — mantığı burada bire bir doğrula
        models = []
        for line in raw.splitlines():
            line = line.strip()
            if " - " not in line or line.lower().startswith("available"):
                continue
            mid, _, name = line.partition(" - ")
            mid, name = mid.strip(), name.strip()
            if not mid or mid.endswith("-fast"):
                continue
            name = name.split(" (current")[0].split(" (default")[0].strip()
            models.append((f"cursor-{mid}", name))
        ids = [m[0] for m in models]
        self.assertIn("cursor-auto", ids)
        self.assertIn("cursor-composer-2.5", ids)
        self.assertNotIn("cursor-gpt-5.3-codex-fast", ids)  # -fast elendi
        self.assertEqual(dict(models)["cursor-auto"], "Auto")

    def test_opencode_models_parse(self):
        raw = (
            "opencode/big-pickle\n"
            "opencode/deepseek-v4-flash-free\n"
            "google/gemini-3.5-flash\n"
            "openai/gpt-5.4\n"
        )
        models = [l for l in raw.splitlines() if l.startswith("opencode/")]
        self.assertEqual(len(models), 2)  # yalnız opencode/* (ücretsiz) gösterilir


if __name__ == "__main__":
    unittest.main()
