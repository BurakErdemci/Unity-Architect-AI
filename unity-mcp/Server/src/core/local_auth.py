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

from core.config import config
from core.constants import API_KEY_HEADER, LOCAL_API_TOKEN_ENV

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
