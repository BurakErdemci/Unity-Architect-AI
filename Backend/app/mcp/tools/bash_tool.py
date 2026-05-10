"""
MCP Bash Aracı — güvenli komutlar direkt, tehlikeli komutlar onay gerektirir.
Dosya yazmaya çalışan terminal komutları DiffViewer'a yönlendirilir.
"""
import os
import re
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


def _parse_file_write(command: str):
    """
    Terminal komutu bir dosyaya içerik yazıyorsa (path, content) döner, değilse None.
    Desteklenen kalıplar:
      - python3 -c / python -c ile open(..., 'w').write(...)
      - printf 'content' > path
      - echo 'content' > path
      - touch path  (boş dosya)
    """
    c = command.strip()

    # python3 -c "...open('path','w')...write('content')..."
    m = re.search(
        r"""open\(\s*['"]([^'"]+)['"]\s*,\s*['"]w['"]\).*?\.write\(\s*['"](.+?)['"]\s*\)""",
        c, re.DOTALL
    )
    if m:
        path = m.group(1)
        content = m.group(2).replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"')
        return path, content

    # printf 'content' > path  /  echo 'content' > path
    m = re.search(r'(?:printf|echo)\s+[\'"](.+?)[\'"]\s*>\s*(\S+)', c, re.DOTALL)
    if m:
        content = m.group(1).replace("\\n", "\n")
        return m.group(2), content

    # printf 'content' | dd of=path  /  echo 'content' | dd of=path
    m = re.search(r'(?:printf|echo)\s+[\'"](.+?)[\'"]\s*\|.*?dd\s+of=(\S+)', c, re.DOTALL)
    if m:
        content = m.group(1).replace("\\n", "\n")
        return m.group(2), content

    # dd if=... of=path  (genel dd yazma)
    m = re.search(r'\bdd\b.*?\bof=(\S+)', c)
    if m:
        return m.group(1), ""  # İçerik parse edilemez ama path bilinir

    return None


def register_bash_tool(mcp: FastMCP, get_workspace: callable):

    async def _run_command(command: str) -> str:
        workspace = get_workspace()

        # Terminalle dosya yazma girişimi → DiffViewer'a yönlendir
        file_write = _parse_file_write(command)
        if file_write:
            path, new_content = file_write
            # Boş içerikli test dosyaları → reddet, write_file kullanmasını söyle
            if not new_content.strip():
                return "❌ Boş dosya oluşturma reddedildi. Dosya içeriğiyle birlikte mcp__antigravity__write_file kullan."
            abs_path = os.path.join(workspace, path) if not os.path.isabs(path) else path
            original = ""
            if os.path.exists(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        original = f.read()
                except Exception:
                    pass

            result = await request_approval(
                tool_name="write_file",
                params={"path": path, "content": new_content, "original": original},
                workspace_path=workspace,
            )
            if not result.get("approved"):
                return f"❌ Reddedildi: {path}"
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return f"✅ Yazıldı: {path}"

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
