import os
import json
import logging
import tempfile
from .cli_base import BaseCLIProvider
from .oneshot_cli import resolve_copilot_cmd, split_model_id

logger = logging.getLogger(__name__)


class CopilotProvider(BaseCLIProvider):
    """GitHub Copilot CLI — -p (programatik mod) + resmi session resume.

    • İlk tur: --session-id=<bizim ürettiğimiz uuid> (UUID'i BİZ seçeriz,
      yakalama derdi yok). Sonraki turlar: --resume=<uuid>.
    • Çıktı: --output-format json → JSONL event akışı
      (assistant.message_delta / assistant.reasoning_delta / assistant.message
      / result) — cli_base'de işlenir.
    • İzinler: built-in write/shell REDDEDİLİR, unityai + unityMCP araçlarına
      izin verilir → tüm dosya/shell işleri onaylı unityai MCP'den geçer.
    • MCP: --additional-mcp-config @<dosya> ile SESSION-BAZLI enjekte edilir
      (global ~/.copilot config'ine dokunmayız).
    """

    resume_session_id = None   # önceki turların uuid'i (--resume)
    fresh_session_id = None    # ilk tur için bizim ürettiğimiz uuid (--session-id)
    _mcp_cfg_path = None       # bu tur için yazılan geçici MCP config dosyası

    def _build_cmd(self, prompt: str, thinking_level: str = "medium", workspace: str = None) -> list:
        base = resolve_copilot_cmd()
        if not base:
            return ["copilot-not-found", prompt]

        _, model = split_model_id(self.binary_name)

        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
        unity_running = unity_mcp_manager.is_running()
        unity_section = ""
        if unity_running:
            unity_section = (
                "\nUNITY EDITOR — unityMCP tools (use for ALL Unity scene/UI operations):\n"
                "- Scene hierarchy:            unityMCP manage_scene action=get_hierarchy\n"
                "- Create/modify GameObjects:  unityMCP manage_gameobject\n"
                "- Components:                 unityMCP manage_components\n"
                "- UI (Canvas/Button/Text):    unityMCP manage_ui\n"
                "- Console logs:               unityMCP read_console\n"
                "RULE: NEVER read .unity/.prefab/.asset files to answer Unity questions —\n"
                "      always query the live editor via unityMCP.\n"
            )

        mcp_hint = (
            "IMPORTANT — follow exactly:\n"
            "- Respond in Turkish (Türkçe).\n"
            + unity_section +
            "\nFILE & TERMINAL operations — your built-in write and shell tools are\n"
            "DENIED by policy. Use ONLY the unityai MCP tools:\n"
            "- Create/edit files:  unityai save_file\n"
            "- Delete files:       unityai delete_file\n"
            "- Shell commands:     unityai run_terminal_command\n"
            "- Read file:          unityai read_file  |  List dir: unityai list_directory\n"
            "Be concise. Never claim you cannot do something — use the tools.\n\n"
        )

        cmd = [
            *base,
            "--output-format", "json",
            "--no-color",
            "--no-ask-user",
            "--no-auto-update",
            "--deny-tool", "write",
            "--deny-tool", "shell",
            "--allow-tool", "unityai",
        ]
        if unity_running:
            cmd += ["--allow-tool", "unityMCP"]
        cmd += ["--model", model or "auto"]
        if self.resume_session_id:
            cmd += [f"--resume={self.resume_session_id}"]
        elif self.fresh_session_id:
            cmd += [f"--session-id={self.fresh_session_id}"]
        if self._mcp_cfg_path:
            cmd += ["--additional-mcp-config", f"@{self._mcp_cfg_path}"]
        # NOT: --effort BİLEREK verilmiyor — "auto" ve bazı modeller reasoning effort
        # konfigürasyonunu desteklemiyor ve CLI hata verip hiç yanıt üretmiyor
        # (canlı doğrulandı: 'Model "auto" does not support reasoning effort').
        cmd += ["-p", prompt]
        return cmd

    def _register_mcp(self, launcher: str, workspace: str, backend_url: str):
        """Session-bazlı MCP config dosyası yazar (--additional-mcp-config @path)."""
        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager

        try:
            unityai_env = {"UNITYAI_URL": backend_url, "WORKSPACE": workspace}
            token = os.environ.get("LOCAL_APP_TOKEN", "")
            if token:
                unityai_env["LOCAL_APP_TOKEN"] = token

            servers = {
                "unityai": {
                    "type": "local",
                    "command": launcher,
                    "args": ["--workspace", workspace],
                    "env": unityai_env,
                    "tools": ["*"],
                }
            }
            if unity_mcp_manager.is_running():
                servers["unityMCP"] = {
                    "type": "http",
                    "url": f"http://localhost:{unity_mcp_manager.mcp_port}/mcp",
                    "tools": ["*"],
                }

            fd, path = tempfile.mkstemp(prefix="uai_copilot_mcp_", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"mcpServers": servers}, f, indent=2)
            self._mcp_cfg_path = path
            logger.info(f"[CopilotProvider] session MCP config yazıldı: {path}")
        except Exception as e:
            self._mcp_cfg_path = None
            logger.warning(f"[CopilotProvider] MCP config yazılamadı: {e}")
