"""Shared-secret gate for the local (non-remote-hosted) control plane.

Everything a local server exposes -- the REST routes under /api, the
streamable-http MCP transport, the plugin WebSocket hub and /register-tools --
is reachable by every process running as this user, and each of them can reach
into a connected Unity Editor or into the tool list the user's AI clients read.
They therefore all check the same secret, and they all check it the same way,
which is what this module is for.

Remote-hosted deployments do not use any of this: they authenticate per request
through ApiKeyService instead.
"""

from __future__ import annotations

import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from core.config import config
from core.constants import (API_KEY_HEADER, LOCAL_API_TOKEN_ENV,
                            MCP_TRANSPORT_BASE_PATH)

# Well-known path of the file holding the shared secret. Referenced here only to
# make the rejection log actionable; the file is written by the process that
# launches this server, and read back by the Unity Editor package
# (WebSocketTransportClient.ReadLocalApiToken). ~/.unity-mcp is the directory the
# Python and C# sides already share on every platform (port registry, status
# files), which is why the secret lives there too.
LOCAL_API_TOKEN_FILE_HINT = "~/.unity-mcp/local-api-token"


def local_token_matches(provided: str | None) -> bool:
    """True when `provided` is exactly the configured local shared secret.

    Fails closed when no secret is configured: a server without a secret must
    never read "sent nothing" as "sent the right thing".
    """
    expected = config.local_api_token
    if not expected:
        return False
    # compare_digest on bytes, not str: the str overload raises TypeError on
    # non-ASCII input and the value being compared is attacker-controlled.
    return hmac.compare_digest(
        (provided or "").encode("utf-8"), expected.encode("utf-8"))


def require_local_token(request: Request) -> JSONResponse | None:
    """Reject a local HTTP request unless it carries the shared secret.

    Returns the error response to send, or None when the request may proceed.
    """
    if not config.local_api_token:
        return JSONResponse(
            {"success": False,
             "error": f"Local API disabled: {LOCAL_API_TOKEN_ENV} is not set"},
            status_code=503,
        )
    if not local_token_matches(request.headers.get(API_KEY_HEADER)):
        return JSONResponse(
            {"success": False,
             "error": f"Missing or invalid {API_KEY_HEADER} header"},
            status_code=401,
        )
    return None


class LocalTokenHeaderMiddleware:
    """ASGI gate that lets the MCP transport authenticate by HEADER, not by URL.

    Why this exists: the secret used to ride in the transport's URL path
    (`/mcp/<secret>`) because header support "had not been verified" across the
    MCP clients this project drives. That was an assumption, and it was measured
    to be wrong on 2026-07-27 -- claude, kimi and codex all deliver a configured
    header on every MCP request (codex only under the key `http_headers`; the
    obvious-looking `headers` is accepted and then silently dropped, which is the
    worst failure shape there is and is exactly why this was measured instead of
    read).

    A URL is not a credential container: it is written into workspace
    `.mcp.json` files the model itself can read, it appears in `ps` output when a
    registration command runs, and it lands in log lines verbatim. A header does
    none of that. Four separate findings in one audit came from that single
    choice.

    The `/mcp/<secret>` path form is NOT kept as a fallback: keeping it would
    preserve exactly the leak this class exists to remove. An old config now
    fails closed with 401 instead of working while leaking.

    Header lookup is CASE-INSENSITIVE on purpose: the same measurement showed
    claude and codex emit `x-api-key` while kimi emits `X-API-Key`. A
    case-sensitive comparison would have rejected two clients out of three, and
    only in the field.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or config.http_remote_hosted:
            await self.app(scope, receive, send)
            return

        # SCOPE THIS TO THE TRANSPORT PATH ONLY.
        #
        # FastMCP applies `middleware=` to the whole Starlette app, not to the
        # transport mount alone. The first version of this class therefore
        # guarded every route - including /health, which is deliberately open
        # because the desktop app polls it to decide whether the server is up.
        # /health started answering 401, the liveness probe read that as "not
        # running", and the toggle sat spinning forever with no way to cancel it.
        # Caught in live testing, not by any unit test or probe: both suites
        # exercised the transport, and nothing asserted that /health stays open.
        #
        # Everything else keeps the guard it already had: /api/* and
        # /register-tools call require_local_token themselves, and the WebSocket
        # hub authenticates on connect. This middleware exists only so the MCP
        # transport can authenticate by header instead of by a secret in its URL.
        path = scope.get("path", "")
        base = MCP_TRANSPORT_BASE_PATH
        if not (path == base or path.startswith(base + "/")):
            await self.app(scope, receive, send)
            return

        # Starlette lowercases nothing for us here: headers arrive as raw bytes.
        wanted = API_KEY_HEADER.lower().encode("latin-1")
        provided: str | None = None
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.lower() == wanted:
                provided = raw_value.decode("latin-1")
                break

        if not local_token_matches(provided):
            response = JSONResponse(
                {"success": False,
                 "error": f"Missing or invalid {API_KEY_HEADER}. The local MCP "
                          f"transport requires the shared secret from "
                          f"{LOCAL_API_TOKEN_FILE_HINT}."},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
