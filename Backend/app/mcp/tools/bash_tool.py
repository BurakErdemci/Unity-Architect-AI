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

    @mcp.tool()
    async def bash(command: str) -> str:
        """
        Terminal komutu çalıştırır.
        Güvenli komutlar (git status, ls vb.) direkt çalışır.
        Tehlikeli komutlar (git push, rm, npm install vb.) ONAY GEREKTİRİR.
        """
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
