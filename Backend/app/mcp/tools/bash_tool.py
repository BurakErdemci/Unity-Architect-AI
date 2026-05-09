"""
MCP Bash Aracı — güvenli komutlar direkt, tehlikeli komutlar onay gerektirir.
"""
import os
import subprocess
from mcp.server.fastmcp import FastMCP

from app.mcp.approval_bridge import request_approval

_SAFE_PREFIXES = (
    "ls", "ll", "find ", "grep ", "cat ", "head ", "tail ",
    "echo ", "pwd", "wc ", "tree ",
    "git status", "git log", "git diff", "git show",
    "git branch", "git remote -v", "git stash list",
)


def _is_safe(command: str) -> bool:
    stripped = command.strip().lower()
    return any(stripped == s.strip() or stripped.startswith(s) for s in _SAFE_PREFIXES)


def register_bash_tool(mcp: FastMCP, get_workspace: callable):

    async def _run_command(command: str) -> str:
        workspace = get_workspace()

        if not _is_safe(command):
            result = await request_approval(
                tool_name="bash",
                params={"command": command},
                workspace_path=workspace,
            )
            if not result.get("approved"):
                return f"❌ Komut reddedildi: {command}"

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            if len(output) > 8000:
                output = output[:8000] + "\n... (kısaltıldı)"
            return output or "(çıktı yok)"
        except subprocess.TimeoutExpired:
            return "❌ Zaman aşımı (300s)"
        except Exception as e:
            return f"❌ Hata: {str(e)}"

    @mcp.tool(
        description=(
            "Run a terminal/shell command in the workspace. Safe read-only commands may run directly; "
            "dangerous commands such as rm, mkdir, mv, git push, npm install, chmod, and writes "
            "request approval in the Antigravity UI before execution."
        )
    )
    async def bash(command: str) -> str:
        """
        Terminal komutu çalıştırır.
        Güvenli komutlar (git status, ls vb.) direkt çalışır.
        Tehlikeli komutlar (git push, rm, npm install vb.) ONAY GEREKTİRİR.
        """
        return await _run_command(command)

    @mcp.tool(
        name="run_terminal_command",
        description=(
            "Execute a terminal command in the workspace through Antigravity's approval bridge."
        ),
    )
    async def run_terminal_command(command: str) -> str:
        return await _run_command(command)

    @mcp.tool(
        name="execute_shell_command",
        description=(
            "Alias for run_terminal_command. Runs shell commands like git, mkdir, rm, mv, npm, "
            "python, and ls in the workspace, with approval for dangerous operations."
        ),
    )
    async def execute_shell_command(command: str) -> str:
        return await _run_command(command)
