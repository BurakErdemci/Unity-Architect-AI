"""Codex app-server oturumu ve onay protokolü regresyon testleri."""
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from providers.codex_session import (
    CodexSession,
    _APP_SERVER_STREAM_LIMIT,
    _trusted_mcp_config,
)


class TestProtocolLimits(unittest.TestCase):
    def test_stream_limit_handles_large_unity_tool_schemas(self):
        self.assertGreater(_APP_SERVER_STREAM_LIMIT, 64 * 1024)
        self.assertLessEqual(_APP_SERVER_STREAM_LIMIT, 8 * 1024 * 1024)


class TestTrustedMcpConfig(unittest.TestCase):
    def _manager_modules(self, running: bool):
        manager_module = MagicMock()
        manager_module.unity_mcp_manager.is_running.return_value = running
        package = MagicMock()
        package.unity_mcp_manager = manager_module.unity_mcp_manager
        return patch.dict(
            sys.modules,
            {
                "unity_ai_mcp": package,
                "unity_ai_mcp.unity_mcp_manager": manager_module,
            },
        )

    def test_unityai_is_approved_at_codex_layer(self):
        with self._manager_modules(running=False), patch(
            "providers.codex_session._configured_codex_mcp_names",
            return_value={"unityai"},
        ):
            config = _trusted_mcp_config()

        self.assertEqual(
            config["mcp_servers"]["unityai"]["default_tools_approval_mode"],
            "approve",
        )
        self.assertNotIn("unityMCP", config["mcp_servers"])

    def test_running_unity_mcp_is_approved_at_codex_layer(self):
        with self._manager_modules(running=True), patch(
            "providers.codex_session._configured_codex_mcp_names",
            return_value={"unityai", "unityMCP"},
        ):
            config = _trusted_mcp_config()

        self.assertEqual(
            config["mcp_servers"]["unityMCP"]["default_tools_approval_mode"],
            "approve",
        )

    def test_unregistered_unity_mcp_does_not_break_thread_config(self):
        with self._manager_modules(running=True), patch(
            "providers.codex_session._configured_codex_mcp_names",
            return_value={"unityai"},
        ):
            config = _trusted_mcp_config()

        self.assertNotIn("unityMCP", config["mcp_servers"])


class TestCodexApprovalResponses(unittest.IsolatedAsyncioTestCase):
    async def test_client_request_omits_jsonrpc_wire_field(self):
        session = CodexSession(0)
        sent = []

        async def fake_send(message):
            sent.append(message)
            session._pending[message["id"]].set_result({
                "id": message["id"],
                "result": {"ok": True},
            })

        session._send = fake_send

        response = await session._request("config/read", {})

        self.assertEqual(response["result"], {"ok": True})
        self.assertNotIn("jsonrpc", sent[0])
        self.assertEqual(sent[0]["method"], "config/read")

    async def test_client_notification_omits_jsonrpc_wire_field(self):
        session = CodexSession(0)
        session._send = AsyncMock()

        await session._notify("initialized")

        session._send.assert_awaited_once_with({"method": "initialized"})

    async def test_permissions_approval_uses_current_appserver_schema(self):
        session = CodexSession(1)
        requested = {
            "fileSystem": {"read": ["/project"]},
            "network": {"enabled": False},
        }
        session._resolve_approval = AsyncMock(return_value="accept")
        session._send = AsyncMock()

        await session._handle_server_request({
            "id": 7,
            "method": "item/permissions/requestApproval",
            "params": {"permissions": requested, "reason": "MCP tool call"},
        })

        session._send.assert_awaited_once_with({
            "id": 7,
            "result": {
                "permissions": requested,
                "scope": "turn",
            },
        })

    async def test_permissions_rejection_grants_nothing(self):
        session = CodexSession(2)
        session._resolve_approval = AsyncMock(return_value="decline")
        session._send = AsyncMock()

        await session._handle_server_request({
            "id": 8,
            "method": "item/permissions/requestApproval",
            "params": {"permissions": {"network": {"enabled": True}}},
        })

        session._send.assert_awaited_once_with({
            "id": 8,
            "result": {
                "permissions": {},
                "scope": "turn",
            },
        })

    async def test_command_approval_keeps_decision_response(self):
        session = CodexSession(3)
        session._resolve_approval = AsyncMock(return_value="accept")
        session._send = AsyncMock()

        await session._handle_server_request({
            "id": 9,
            "method": "item/commandExecution/requestApproval",
            "params": {"command": "git status"},
        })

        session._send.assert_awaited_once_with({
            "id": 9,
            "result": {"decision": "accept"},
        })
