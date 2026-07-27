"""Server-wide protocol constants."""

# HTTP header name for API key authentication
API_KEY_HEADER = "X-API-Key"

# Environment variable carrying the shared secret that guards the local REST
# control plane (/api/*) and the streamable-http transport when the server is
# NOT remote-hosted. Passed via the environment rather than a CLI flag because
# argv is world-readable via `ps`.
LOCAL_API_TOKEN_ENV = "UNITY_MCP_LOCAL_API_TOKEN"

# Base path of the streamable-http MCP transport, and the whole path: the shared
# secret travels in the X-API-Key header, never in the URL.
#
# It used to be appended as a path segment (-> /mcp/<secret>). That form was
# removed on 2026-07-27 because a secret in the URL leaks into places a URL is
# allowed to go: the generated client configs (including one the model itself can
# read), the argv of the registration commands, and error logs. Clients were
# measured to support headers before the switch -- see core/local_auth.py.
MCP_TRANSPORT_BASE_PATH = "/mcp"
