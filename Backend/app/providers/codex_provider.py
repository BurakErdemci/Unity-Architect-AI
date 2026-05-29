import os
import logging
from .cli_base import BaseCLIProvider

logger = logging.getLogger(__name__)


class CodexProvider(BaseCLIProvider):

    def _build_cmd(self, prompt: str, thinking_level: str = "medium", workspace: str = None) -> list:
        full_id = self.binary_name
        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
        unity_running = unity_mcp_manager.is_running()

        unity_section = ""
        if unity_running:
            unity_section = (
                "\n\nUNITY EDITOR CONTROL (unityMCP tools — use these for ALL Unity operations):\n"
                "RULE: NEVER read .unity, .prefab or .asset files to answer Unity questions.\n"
                "      ALWAYS call the live Unity Editor via unityMCP tools instead.\n"
                "- Scene hierarchy & GameObjects: unityMCP/manage_scene (action='get_hierarchy')\n"
                "- Find objects:                  unityMCP/find_gameobjects\n"
                "- Create/modify/delete objects:  unityMCP/manage_gameobject\n"
                "- Components (add/remove/edit):  unityMCP/manage_components\n"
                "- UI elements (Button/Text/etc): unityMCP/manage_ui\n"
                "- Console errors/warnings:       unityMCP/read_console\n"
                "- Play/Pause/Save scene:         unityMCP/manage_editor\n"
                "- Materials/shaders:             unityMCP/manage_material\n"
                "- Physics settings:              unityMCP/manage_physics\n"
                "C# SCRIPTS (.cs): ALWAYS create/edit with mcp__unityai__save_file (user approval).\n"
                "  NEVER use unityMCP/manage_script to write .cs files — it bypasses approval.\n"
                "Only use unityai file tools for C# source files (.cs), NOT for Unity scene data.\n"
            )

        mcp_hint = (
            "\n\nIMPORTANT — Tool priority order (follow exactly, no exceptions):\n"
            + unity_section +
            "\nFILE & TERMINAL operations (unityai tools):\n"
            "- Shell commands (git, npm, mkdir, etc.): mcp__unityai__run_terminal_command\n"
            "- Create/edit .cs files:                  mcp__unityai__save_file\n"
            "- Delete files:                           mcp__unityai__delete_file\n"
            "- Read .cs source files:                  mcp__unityai__read_file\n"
            "- List directories:                       mcp__unityai__list_directory\n"
            "\nRESPOND IN TURKISH. Be concise. Never say you cannot do something — use the tools.\n"
        )

        cmd = [
            "codex", "exec",
            "-m", full_id,
            "-s", "read-only",
            "--skip-git-repo-check",
            "--disable", "shell_tool",
            "--disable", "unified_exec",
            "--json",
            "-c", 'mcp_servers.unityai.default_tools_approval_mode="approve"',
        ]
        if unity_running:
            cmd.extend(["-c", 'mcp_servers.unityMCP.default_tools_approval_mode="approve"'])
        if thinking_level != "off":
            cmd.extend(["-c", f"reasoning.effort={thinking_level}"])
        cmd.append(mcp_hint + "\n" + prompt)
        return cmd

    def _register_mcp(self, launcher: str, workspace: str, backend_url: str):
        """
        Codex'in ~/.codex/config.toml dosyasına unityai MCP server'ını yazar.
        Her çağrıda URL güncellenir (backend dinamik port kullanır).
        """
        import subprocess as sp
        try:
            from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager

            # Önce var olan kayıtları sil (URL güncel olmayabilir, eski isim kalmış olabilir)
            for old_name in ("unityai", "antigravity"):
                sp.run(["codex", "mcp", "remove", old_name], capture_output=True, timeout=5)
            # unityMCP global config'te stale kalırsa Codex kapalı 8080'e bağlanmaya
            # çalışıp tüm run'ı "Transport channel closed" ile düşürebiliyor.
            sp.run(
                ["codex", "mcp", "remove", "unityMCP"],
                capture_output=True, timeout=5,
            )

            local_app_token = os.environ.get("LOCAL_APP_TOKEN", "")
            env_args = [
                "--env", f"UNITYAI_URL={backend_url}",
                "--env", f"WORKSPACE={workspace}",
            ]
            if local_app_token:
                env_args.extend(["--env", f"LOCAL_APP_TOKEN={local_app_token}"])

            # Yeni kaydı ekle
            sp.run(
                [
                    "codex", "mcp", "add", "unityai",
                    *env_args,
                    "--", launcher, "--workspace", workspace,
                ],
                capture_output=True, timeout=5, check=True,
            )
            if unity_mcp_manager.is_running():
                sp.run(
                    [
                        "codex", "mcp", "add", "unityMCP",
                        "--url", f"http://127.0.0.1:{unity_mcp_manager.mcp_port}/mcp",
                    ],
                    capture_output=True, timeout=5, check=True,
                )
        except Exception as e:
            logger.warning(f"[CLIProvider] Codex MCP kaydı yapılamadı: {e}")
