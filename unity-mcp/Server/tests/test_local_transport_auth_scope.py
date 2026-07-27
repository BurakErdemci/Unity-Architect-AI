"""The header gate must cover the MCP transport and NOTHING else.

Regression for a live-only failure. LocalTokenHeaderMiddleware is handed to
FastMCP as `middleware=`, and FastMCP applies that to the whole Starlette app
rather than to the transport mount. The first version therefore also guarded
/health, which is deliberately unauthenticated because the desktop app polls it
to decide whether the server is up. /health answered 401, the liveness probe
read that as "not running", and the product's toggle spun forever with no way
to cancel it.

Neither the unit suites nor twelve audit probes caught it: every one of them
exercised the transport, and none asserted that the open route stayed open. A
security gate is only correct if it is the right SIZE, and the too-wide
direction is the one nobody writes a test for.
"""

import asyncio

import pytest

from core.config import config
from core.local_auth import LocalTokenHeaderMiddleware

SECRET = "test-shared-secret-value"


class _Sentinel:
    """Stands in for the wrapped app; records that the request got through."""

    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def _run(path, headers=(), scope_type="http"):
    inner = _Sentinel()
    mw = LocalTokenHeaderMiddleware(inner)
    status = {}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": scope_type, "path": path, "headers": list(headers)}
    asyncio.run(mw(scope, receive, send))
    return inner.called, status.get("code")


@pytest.fixture(autouse=True)
def _local_mode(monkeypatch):
    monkeypatch.setattr(config, "local_api_token", SECRET, raising=False)
    monkeypatch.setattr(config, "http_remote_hosted", False, raising=False)


# ── The gate must not be too WIDE (the bug that shipped) ────────────────────

@pytest.mark.parametrize("path", ["/health", "/api/instances", "/api/command",
                                  "/register-tools", "/"])
def test_non_transport_routes_are_not_touched(path):
    """/health especially: the toggle's liveness probe depends on it.

    /api/* and /register-tools are not "unprotected" here - they call
    require_local_token themselves. This middleware simply must not be the
    thing that answers for them.
    """
    passed_through, _ = _run(path)
    assert passed_through, f"{path} was blocked by the transport gate"


def test_websocket_scope_is_not_touched():
    """/mcp/hub/plugin lives under the transport prefix but is a WebSocket and
    authenticates on connect in plugin_hub. Blocking it here would break the
    Unity Editor's bridge."""
    passed_through, _ = _run("/mcp/hub/plugin", scope_type="websocket")
    assert passed_through


# ── The gate must not be too NARROW either ─────────────────────────────────

def test_transport_without_header_is_rejected():
    passed_through, code = _run("/mcp")
    assert not passed_through
    assert code == 401


def test_transport_with_wrong_header_is_rejected():
    passed_through, code = _run("/mcp", [(b"x-api-key", b"wrong")])
    assert not passed_through
    assert code == 401


def test_transport_with_correct_header_is_allowed():
    """Without this direction a middleware that rejects everything would pass."""
    passed_through, _ = _run("/mcp", [(b"x-api-key", SECRET.encode())])
    assert passed_through


@pytest.mark.parametrize("name", [b"X-API-Key", b"x-api-key", b"X-Api-Key"])
def test_header_name_is_case_insensitive(name):
    """Measured 2026-07-27: claude and codex send `x-api-key`, kimi sends
    `X-API-Key`. A case-sensitive lookup would have locked out two clients of
    three, and only in the field."""
    passed_through, _ = _run("/mcp", [(name, SECRET.encode())])
    assert passed_through, f"{name!r} was rejected"


def test_old_secret_in_path_no_longer_authenticates():
    """The path form was removed on purpose; keeping it would preserve the leak
    this gate exists to remove. An old config must fail closed, not work."""
    passed_through, code = _run(f"/mcp/{SECRET}")
    assert not passed_through
    assert code == 401
