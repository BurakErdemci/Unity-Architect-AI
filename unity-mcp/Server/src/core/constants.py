"""Server-wide protocol constants."""

# HTTP header name for API key authentication
API_KEY_HEADER = "X-API-Key"

# Environment variable carrying the shared secret that guards the local REST
# control plane (/api/*) and the streamable-http transport when the server is
# NOT remote-hosted. Passed via the environment rather than a CLI flag because
# argv is world-readable via `ps`.
LOCAL_API_TOKEN_ENV = "UNITY_MCP_LOCAL_API_TOKEN"

# Base path of the streamable-http MCP transport. In local mode the shared
# secret is appended as an extra path segment (-> /mcp/<secret>); see
# resolve_http_transport_path() in main.py for why the secret rides in the URL
# instead of a header.
MCP_TRANSPORT_BASE_PATH = "/mcp"
