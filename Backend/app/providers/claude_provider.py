import os
import logging
from .cli_base import BaseCLIProvider

logger = logging.getLogger(__name__)


class ClaudeCodeProvider(BaseCLIProvider):

    def _build_cmd(self, prompt: str, thinking_level: str = "medium", workspace: str = None) -> list:
        full_id = self.binary_name
        # Built-in tehlikeli araçları blokla → Claude MCP'lerimizi kullanmak ZORUNDA kalır
        # bypassPermissions modu --allowedTools'u pasifleştirdiği için sadece deny-list işe yarar
        disallowed = ",".join([
            "Bash",          # → mcp__unityai__bash
            "Write",         # → mcp__unityai__save_file
            "Edit",          # → mcp__unityai__save_file
            "MultiEdit",     # → mcp__unityai__save_file
            "NotebookEdit",
        ])
        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
        unity_running = unity_mcp_manager.is_running()
        unity_section = ""
        if unity_running:
            unity_section = (
                "\nUNITY EDITOR — unityMCP tools (use these for ALL Unity scene/UI operations):\n"
                "- Scene hierarchy:               mcp__unityMCP__manage_scene action=get_hierarchy\n"
                "- Create/modify GameObjects:     mcp__unityMCP__manage_gameobject\n"
                "- Add/remove/edit components:    mcp__unityMCP__manage_components\n"
                "- UI elements (Canvas/Button):   mcp__unityMCP__manage_ui\n"
                "- Scripts (create/attach):       mcp__unityMCP__manage_script\n"
                "- Materials/shaders:             mcp__unityMCP__manage_material\n"
                "- Console logs:                  mcp__unityMCP__read_console\n"
                "RULE: Never write Editor scripts to create scene objects — use unityMCP tools directly.\n"
                "Only use mcp__unityai__save_file for runtime C# scripts (.cs), NOT for scene setup.\n"
            )
        subagent_prefix = (
            "SUBAGENT EXECUTION MODE: You are a subagent dispatched to execute a specific task. "
            "Do NOT invoke any skills, do NOT brainstorm, do NOT offer visual companions or mockups, "
            "do NOT ask clarifying questions. Execute the task IMMEDIATELY using available MCP tools. "
            "Respond in Turkish (Türkçe).\n"
            + unity_section + "\n"
        )
        return [
            "claude", "--model", full_id,
            "--permission-mode", "bypassPermissions",
            "--disallowedTools", disallowed,
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--verbose",
            "-p", subagent_prefix + prompt,
        ]

    def _register_mcp(self, launcher: str, workspace: str, backend_url: str):
        """
        Claude Code'un user-scope config'ine unityai ve unityMCP server'larını yazar.
        Project-scope .mcp.json -p (headless) modda approval gerektirdiği için kullanılamaz.
        """
        import subprocess as sp
        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager

        # unityai (stdio)
        try:
            sp.run(["claude", "mcp", "remove", "unityai", "--scope", "user"],
                   capture_output=True, timeout=5)
            sp.run(
                [
                    "claude", "mcp", "add", "unityai",
                    "--scope", "user",
                    "-e", f"UNITYAI_URL={backend_url}",
                    *(["-e", f"LOCAL_APP_TOKEN={os.environ.get('LOCAL_APP_TOKEN', '')}"] if os.environ.get("LOCAL_APP_TOKEN") else []),
                    "-e", f"WORKSPACE={workspace}",
                    "--", launcher, "--workspace", workspace,
                ],
                capture_output=True, timeout=5, check=True,
            )
            logger.info("[CLIProvider] Claude unityai MCP kaydedildi (user scope).")
        except Exception as e:
            logger.warning(f"[CLIProvider] Claude unityai MCP kaydı yapılamadı: {e}")

        # unityMCP (http) — sadece Unity MCP server çalışıyorsa
        try:
            sp.run(["claude", "mcp", "remove", "unityMCP", "--scope", "user"],
                   capture_output=True, timeout=5)
            if unity_mcp_manager.is_running():
                sp.run(
                    [
                        "claude", "mcp", "add", "unityMCP",
                        "--scope", "user",
                        "--transport", "http",
                        f"http://localhost:{unity_mcp_manager.mcp_port}/mcp",
                    ],
                    capture_output=True, timeout=5, check=True,
                )
                logger.info("[CLIProvider] Claude unityMCP kaydedildi (user scope).")
        except Exception as e:
            logger.warning(f"[CLIProvider] Claude unityMCP kaydı yapılamadı: {e}")
