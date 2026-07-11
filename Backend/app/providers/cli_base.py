import os
import re
import sys
import shutil
import logging
import asyncio
import subprocess
import json
from typing import Dict, Any, Optional, List, AsyncGenerator

from .base import AIProvider, ThinkingResult, _strip_ansi

logger = logging.getLogger(__name__)

# Windows: konsol subprocess'i (özellikle agy — her tur ephemeral spawn) açılınca kısa bir
# konsol penceresi yanıp söner. CREATE_NO_WINDOW ile gizlenir (non-Windows'ta 0 = etkisiz).
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class BaseCLIProvider(AIProvider):
    """
    Claude Code, Codex ve agy CLI'larını UnityAI MCP Server üzerinden çalıştırır.
    """

    # Race condition önlemi: settings.json yazma + subprocess spawn atomik olmalı
    _AGY_LOCK = asyncio.Lock()

    # model ID → agy settings.json "model" değeri eşlemesi
    _AGY_MODEL_MAP = {
        # Gemini modelleri
        "gemini-3.5-flash":              "Gemini 3.5 Flash (High)",
        "gemini-3.5-flash-medium":       "Gemini 3.5 Flash (Medium)",
        "gemini-3.1-pro-preview":        "Gemini 3.1 Pro (High)",
        "gemini-3.1-pro-low":            "Gemini 3.1 Pro (Low)",
        "gemini-3-flash-preview":        "Gemini 3 Flash (High)",
        "gemini-2.5-pro":                "Gemini 2.5 Pro (High)",
        "gemini-2.5-flash":              "Gemini 2.5 Flash (High)",
        "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite (High)",
        # Antigravity CLI üzerinden Claude ve GPT modelleri
        "agy-claude-sonnet-4-6":         "Claude Sonnet 4.6 (Thinking)",
        "agy-claude-opus-4-6":           "Claude Opus 4.6 (Thinking)",
        "agy-gpt-oss-120b":              "GPT-OSS 120B (Medium)",
    }

    # agy CLI'ın kendi yerleşik araçlarının isimleri (onaysız çalışmayı engellemek amacıyla devre dışı bırakılır)
    # agy'nin GERÇEK built-in yazma araçları (agy'nin kendi raporundan doğrulandı).
    # Bunları kapatınca agy dosya yazmak için tek yol olarak run_command'a düşer,
    # biz de onu 'unityai save-file' CLI'ına yönlendiririz → onay kartı çıkar.
    # run_command, view_file, list_dir AÇIK bırakılır (unityai CLI'ı çağırmak +
    # okuma için gerekli; okuma onay gerektirmez).
    _AGY_DISABLED_TOOLS = [
        "write_to_file", "replace_file_content", "multi_replace_file_content",
    ]

    def __init__(self, binary_name: str = "claude"):
        self.binary_name = binary_name
        self._pending_agy_model = "Gemini 3.5 Flash (High)"

    def _backend_dir(self) -> str:
        """Backend kökünü döndürür (run_mcp_server.sh + unityai orada yaşar).
        Frozen build: sys.executable = .../Backend/backend → dirname = .../Backend.
        Dev: bu dosya .../Backend/app/providers/cli_base.py → 3x dirname."""
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def _launcher_path(self, name: str) -> str:
        """Platforma uygun launcher yolunu döndürür.
        name: 'run_mcp_server' → Windows'ta run_mcp_server.cmd, diğer OS'te run_mcp_server.sh.
              'unityai'        → Windows'ta unityai.cmd, diğer OS'te unityai (bash)."""
        backend_dir = self._backend_dir()
        if sys.platform == "win32":
            fname = f"{name}.cmd"
        else:
            fname = "run_mcp_server.sh" if name == "run_mcp_server" else name
        return os.path.join(backend_dir, fname)

    @staticmethod
    def _resolve_exec(cmd: List[str]) -> List[str]:
        """cmd[0]'i (CLI ismi) PATH'te tam yola çözer ve Windows'a uygun spawn listesi döner.
        Windows'ta npm CLI'ları (claude/codex/agy) .cmd/.bat shim olarak kurulur;
        CreateProcess bunları ne çıplak isimle bulur (WinError 2) ne de doğrudan çalıştırabilir
        → cmd.exe /c ile sarılmalı. .exe / POSIX binary ise doğrudan çalıştırılır."""
        if not cmd:
            return cmd
        resolved = shutil.which(cmd[0]) or cmd[0]
        rest = list(cmd[1:])
        if sys.platform == "win32" and resolved.lower().endswith((".cmd", ".bat")):
            return ["cmd", "/c", resolved, *rest]
        return [resolved, *rest]

    @staticmethod
    def _cli_installed(name: str) -> bool:
        """CLI binary'si PATH'te (Windows'ta PATHEXT ile .cmd/.exe dahil) bulunabiliyor mu?"""
        if os.path.isabs(name):
            return os.path.exists(name)
        return shutil.which(name) is not None

    @staticmethod
    def _ensure_exec(path: str) -> None:
        """Launcher'ın çalıştırılabilir olduğundan emin ol — paket kopyalama exec bit'i düşürebilir."""
        try:
            if os.path.exists(path):
                os.chmod(path, 0o755)
        except OSError:
            pass

    def _get_file_tree(self, workspace: str, max_files: int = 80) -> str:
        """Workspace dosya ağacını string olarak döner (Codex context'i için)."""
        lines = []
        count = 0
        skip_dirs = {".git", "node_modules", "__pycache__", ".next", "venv", "obj", "Library", "Temp"}
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            rel = os.path.relpath(root, workspace)
            prefix = "" if rel == "." else rel + "/"
            for f in files:
                if count >= max_files:
                    lines.append("... (daha fazla dosya var)")
                    return "\n".join(lines)
                lines.append(prefix + f)
                count += 1
        return "\n".join(lines) if lines else "(boş workspace)"

    def _register_mcp(self, launcher: str, workspace: str, backend_url: str):
        """Subclass'lar kendi MCP kayıt mantığını override eder."""
        pass

    def _write_mcp_config(self, workspace: str) -> str:
        """
        Claude Code için workspace'e .mcp.json yazar.
        Codex için ~/.codex/config.toml içindeki unityai MCP kaydını günceller.
        Gemini CLI için MCP kaydını günceller.
        Döndürür: Claude config dosyasının tam yolu.
        """
        launcher = self._launcher_path("run_mcp_server")
        self._ensure_exec(launcher)
        backend_url = os.environ.get("UNITYAI_URL", os.environ.get("ANTIGRAVITY_URL", "http://localhost:8000"))
        local_app_token = os.environ.get("LOCAL_APP_TOKEN", "")
        unityai_env = {"UNITYAI_URL": backend_url}
        if local_app_token:
            unityai_env["LOCAL_APP_TOKEN"] = local_app_token

        # Claude Code: workspace/.mcp.json
        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
        config = {
            "mcpServers": {
                "unityai": {
                    "command": launcher,
                    "args": ["--workspace", workspace],
                    "env": unityai_env,
                }
            }
        }
        # Unity MCP: sadece aktifse ekle, kapalıysa kesinlikle ekleme
        # (Codex/Claude CLI başlarken bağlanamadığı MCP'de crash yapar)
        if unity_mcp_manager.is_running():
            config["mcpServers"]["unityMCP"] = {
                "url": f"http://localhost:{unity_mcp_manager.mcp_port}/mcp"
            }
            logger.info("[CLIProvider] Unity MCP aktif, .mcp.json'a eklendi.")

        config_path = os.path.join(workspace, ".mcp.json")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        # Subclass'a MCP kayıt yaptır (claude, codex, agy için farklı davranış)
        self._register_mcp(launcher, workspace, backend_url)

        return config_path

    def _build_cmd(self, prompt: str, thinking_level: str = "medium", workspace: str = None) -> list:
        """Subclass'lar kendi komut satırlarını override eder."""
        return [self.binary_name, prompt]

    async def analyze_code(self, prompt: str, max_tokens: int = 4096,
                           images: Optional[List[str]] = None,
                           thinking_level: str = "medium", cwd: Optional[str] = None,
                           interactive: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            workspace = cwd or os.getcwd()
            # Güvenlik ağı: seçili workspace klasörü silinmiş/taşınmış olabilir.
            # Bu durumda .mcp.json yazımı FileNotFoundError ile çöküp sohbeti
            # sessizce boş bırakıyordu — kullanıcıya net mesaj ver, çakma.
            if not os.path.isdir(workspace):
                yield {"type": "error", "content": (
                    "📁 Çalışma klasörü bulunamadı (silinmiş veya taşınmış olabilir). "
                    "Lütfen sol üstten yeni bir proje klasörü seçin."
                )}
                return
            self._write_mcp_config(workspace)

            # Codex için prompt'a gerçek dosya ağacını ekle (hallucination'ı önler)
            enriched_prompt = prompt
            if self.binary_name.startswith("gpt-"):
                file_tree = self._get_file_tree(workspace)
                enriched_prompt = (
                    f"WORKSPACE: {workspace}\n"
                    f"CURRENT FILES:\n{file_tree}\n\n"
                    f"{prompt}"
                )

            cmd = self._build_cmd(enriched_prompt, thinking_level, workspace)
            _is_agy = self.binary_name.startswith("gemini") or self.binary_name.startswith("agy-")
            _env = {**os.environ, "NO_COLOR": "1", "TERM": "xterm-256color",
                    "COLUMNS": "220", "LINES": "50"}

            # CLI binary bu PC'de kurulu mu? Değilse korkunç traceback yerine temiz uyarı ver.
            if not self._cli_installed(cmd[0]):
                _labels = {"agy": "Antigravity (agy)", "claude": "Claude Code", "codex": "Codex"}
                _label = _labels.get(os.path.basename(cmd[0]).lower(), cmd[0])
                logger.warning(f"[CLIProvider:{self.binary_name}] CLI bulunamadı (PATH'te yok): {cmd[0]}")
                yield {"type": "error", "content": f"⚠️ {_label} CLI bu bilgisayarda kurulu değil (PATH'te bulunamadı). Lütfen kurun veya farklı bir model seçin."}
                return

            # cmd[0]'i tam yola çöz + Windows .cmd/.bat ise cmd.exe ile sar (WinError 2 fix).
            spawn_cmd = self._resolve_exec(cmd)

            logger.info(f"[CLIProvider:{self.binary_name}][CMD] {' '.join(cmd)}")
            logger.info(f"[CLIProvider:{self.binary_name}][CWD] {workspace}")
            logger.info(f"[CLIProvider:{self.binary_name}][ENV] LOCAL_APP_TOKEN={'set' if _env.get('LOCAL_APP_TOKEN') else 'unset'} UNITYAI_URL={_env.get('UNITYAI_URL', _env.get('ANTIGRAVITY_URL', 'unset'))}")

            _pty_master_fd = None
            if _is_agy:
                async with BaseCLIProvider._AGY_LOCK:
                    self._set_agy_model(self._pending_agy_model, workspace)
                    # agy --print HİÇBİR MCP yüklemez (test edildi). agy'nin gördüğü tek
                    # köprü built-in run_command. Yazma araçları (write_to_file vb.)
                    # _AGY_DISABLED_TOOLS ile kapalı → agy yazmak için 'unityai' CLI'ını
                    # run_command ile çağırmak zorunda kalır → onay kartı çıkar.
                    unityai_cli = self._launcher_path("unityai")
                    self._ensure_exec(unityai_cli)
                    mcp_hint = (
                        "IMPORTANT: You MUST respond in Turkish (Türkçe) at all times.\n\n"
                        "You have a command-line tool 'unityai' for file WRITES, DELETES and shell.\n"
                        "Your own write_to_file/replace_file_content tools are DISABLED on purpose —\n"
                        "the ONLY way to create, edit, delete a file or run shell is via run_command\n"
                        "calling 'unityai' with its ABSOLUTE PATH:\n"
                        f"  {unityai_cli}\n\n"
                        "CRITICAL RULES — follow exactly:\n"
                        "1. CREATE or EDIT a file — pipe the content via stdin (handles multiline):\n"
                        f"   run_command: {unityai_cli} save-file --path \"<rel/path>\" --content-stdin <<'UNITYAI_EOF'\n"
                        "   ...full file content here...\n"
                        "   UNITYAI_EOF\n"
                        "   FORBIDDEN for writing files: python3 -c, printf, echo, cat, tee, or shell\n"
                        "   redirection (>). These bypass user approval. ALWAYS use unityai save-file.\n"
                        f"2. DELETE a file:    run_command: {unityai_cli} delete-file --path \"<rel/path>\"\n"
                        f"3. SHELL commands (git, npm, mkdir, rm, mv, etc.):\n"
                        f"   run_command: {unityai_cli} bash --command \"<shell command>\"\n"
                        "4. To READ a file or LIST a directory you MAY use your own view_file / list_dir.\n\n"
                        "Every write, delete and shell command MUST go through unityai so the user can\n"
                        "approve it in the IDE. SCOPE: Only the current workspace. No unprompted test files.\n\n"
                        "REPLY STYLE — keep your text answer SHORT and clean:\n"
                        "- NEVER paste the file's full content/code block in your reply. The IDE approval\n"
                        "  card already shows the code and diff to the user.\n"
                        "- NEVER explain the approval mechanics (do not say 'onayınızı bekliyor',\n"
                        "  'onay verdikten sonra', 'komutu çalıştırdım' etc.).\n"
                        "- Do NOT repeat yourself or describe the same file twice.\n"
                        "- After a file/shell action, reply with ONE short Turkish sentence stating what\n"
                        "  you did (e.g. 'TestScripts.cs oluşturuldu.'). Add a brief note only if it gives\n"
                        "  real extra value.\n\n"
                    )
                    # Prompt = mcp_hint + enriched_prompt, SON POZİSYONEL ARG olarak
                    # verilir (stdin DEĞİL — agy 1.1.1 ham-metin stdin'i bozuk okuyup
                    # help/derail'e düşüyor; canlı doğrulandı). stdin=DEVNULL. Uzunluk
                    # sınırı _run_agy_session'da yönetiliyor (Windows ~32K argv limiti).
                    agy_prompt = mcp_hint + enriched_prompt
                    process = await asyncio.create_subprocess_exec(
                        *spawn_cmd, agy_prompt,
                        stdin=asyncio.subprocess.DEVNULL,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=_env,
                        cwd=workspace,
                        creationflags=_CREATE_NO_WINDOW,
                    )
            else:
                # Windows .cmd shim (cmd /c): cmd.exe komut satırındaki çok satırlı arg'ı
                # ilk newline'da keser → claude/codex prompt'u (son arg) bozulur. Bu durumda
                # prompt'u argv yerine stdin'den ver (claude --print ve codex exec stdin'i okur).
                _stdin_prompt = None
                if spawn_cmd[:2] == ["cmd", "/c"] and len(spawn_cmd) > 3:
                    _stdin_prompt = spawn_cmd.pop()  # son eleman = prompt metni
                process = await asyncio.create_subprocess_exec(
                    *spawn_cmd,
                    stdin=(asyncio.subprocess.PIPE if _stdin_prompt is not None
                           else asyncio.subprocess.DEVNULL),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=_env,
                    cwd=workspace,
                    creationflags=_CREATE_NO_WINDOW,
                )
                if _stdin_prompt is not None:
                    process.stdin.write(_stdin_prompt.encode("utf-8"))
                    await process.stdin.drain()
                    process.stdin.close()
            _stdout_reader = process.stdout
            logger.info(f"[CLIProvider:{self.binary_name}] PID={process.pid} başlatıldı")

            stderr_buffer = []

            async def _drain_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="ignore").rstrip()
                    stderr_buffer.append(decoded)
                    logger.warning(f"[CLIProvider:{self.binary_name}][STDERR] {decoded}")

            stderr_task = asyncio.create_task(_drain_stderr())

            full_text = ""
            line_count = 0
            _start = asyncio.get_event_loop().time()

            while True:
                try:
                    line = await asyncio.wait_for(_stdout_reader.readline(), timeout=15.0)
                except asyncio.TimeoutError:
                    _now = asyncio.get_event_loop().time()
                    # Onay beklerken CLI uzun süre stdout üretmez — bu normal.
                    # Tek satırlık watchdog; detaylı DIAG dump'ları kaldırıldı (log flood'a
                    # yol açıyordu: codex session jsonl + devasa MCP tool şemaları her 15s).
                    logger.warning(
                        f"[CLIProvider:{self.binary_name}][WAIT] "
                        f"{_now-_start:.0f}s stdout yok (onay/işlem bekleniyor olabilir) | "
                        f"pid={process.pid} | rc={process.returncode}"
                    )
                    if process.returncode is not None:
                        logger.error(f"[CLIProvider:{self.binary_name}] Process bitti rc={process.returncode}")
                        break
                    # Onay (approval) beklerken CLI uzun süre sessiz kalabilir; hard-kill
                    # bu süreyi kapsamalı (approval_bridge 180s bekliyor). 300s tüm provider'lar.
                    _hard_timeout = 300
                    if _now - _start > _hard_timeout:
                        logger.error(f"[CLIProvider:{self.binary_name}] {_hard_timeout}s timeout — kill")
                        process.kill()
                        break
                    continue

                if not line:
                    logger.info(f"[CLIProvider:{self.binary_name}] stdout EOF (toplam {line_count} satır)")
                    break

                raw = _strip_ansi(line.decode("utf-8", errors="ignore")).strip()
                if not raw:
                    continue
                # agy interactive mode: "You >" ve "You (press Ctrl+D..." prompt kalıntılarını filtrele
                if _is_agy and re.match(r'^You\s*(>|\(press)', raw):
                    continue
                line_count += 1
                # Ham stdout — Codex için her satırı logla (debug)
                if self.binary_name.startswith("gpt-"):
                    _preview = raw[:300] + ("..." if len(raw) > 300 else "")
                    logger.info(f"[CLIProvider:{self.binary_name}][RAW#{line_count}] {_preview}")

                import json as _json
                _is_json_provider = (
                    self.binary_name.startswith("claude") or
                    self.binary_name.startswith("gemini") or
                    self.binary_name.startswith("agy-") or
                    self.binary_name.startswith("gpt-")
                )
                if _is_json_provider:
                    try:
                        ev = _json.loads(raw)
                        ev_type = ev.get("type", "")

                        # ── Claude stream-json ──────────────────────────────
                        if ev_type == "assistant":
                            for block in ev.get("message", {}).get("content", []):
                                btype = block.get("type", "")
                                if btype == "thinking":
                                    t = block.get("thinking", "").strip()
                                    if t:
                                        yield {"type": "thinking", "text": t}
                                elif btype == "tool_use":
                                    name = block.get("name", "")
                                    inp = block.get("input", {})
                                    hint = f"🔧 `{name}`"
                                    if "path" in inp:
                                        hint += f" → `{inp['path']}`"
                                    elif "action" in inp:
                                        hint += f" → `{inp['action']}`"
                                    yield {"type": "thinking", "text": hint}
                                elif btype == "text":
                                    t = block.get("text", "")
                                    if t:
                                        full_text += t
                                        yield {"type": "delta", "text": t}
                        elif ev_type == "tool":
                            content = ev.get("content", "")
                            result_text = content[:200] if isinstance(content, str) else ""
                            if result_text:
                                yield {"type": "thinking", "text": f"↩ {result_text}"}
                        elif ev_type == "result":
                            result = ev.get("result", "")
                            if result and not full_text:
                                full_text = result

                        # ── agy / Gemini CLI JSONL (hot-swap) ───────────────
                        elif ev_type in ("content", "error"):
                            t = ev.get("content", ev.get("text", ev.get("error", "")))
                            if t:
                                if self.binary_name.startswith(("gemini", "agy-")) and "timed out" in t.lower():
                                    yield {"type": "error", "text": "agy zaman aşımına uğradı."}
                                else:
                                    full_text += t
                                    yield {"type": "delta", "text": t}
                        elif ev_type == "tool_call":
                            name = ev.get("tool", ev.get("name", ""))
                            inp = ev.get("input", ev.get("args", {}))
                            hint = f"🔧 `{name}`"
                            if isinstance(inp, dict):
                                if "path" in inp:
                                    hint += f" → `{inp['path']}`"
                                elif "action" in inp:
                                    hint += f" → `{inp['action']}`"
                            yield {"type": "thinking", "text": hint}
                        elif ev_type == "tool_result":
                            res = str(ev.get("result", ev.get("content", "")))[:200]
                            if res:
                                yield {"type": "thinking", "text": f"↩ {res}"}

                        # ── Codex --json (yeni format: item.completed) ──────
                        elif ev_type == "item.completed":
                            item = ev.get("item", {})
                            it_type = item.get("type", "")
                            if it_type == "agent_message":
                                t = item.get("text", "")
                                if t:
                                    full_text += t
                                    yield {"type": "delta", "text": t}
                            elif it_type == "reasoning":
                                t = item.get("text", item.get("content", "")).strip()
                                if t:
                                    yield {"type": "thinking", "text": t}
                            elif it_type == "function_call":
                                name = item.get("name", "")
                                args = item.get("arguments", {})
                                hint = f"🔧 `{name}`"
                                if isinstance(args, dict):
                                    if "path" in args:
                                        hint += f" → `{args['path']}`"
                                    elif "action" in args:
                                        hint += f" → `{args['action']}`"
                                yield {"type": "thinking", "text": hint}
                            elif it_type == "function_call_output":
                                out = str(item.get("output", ""))[:200]
                                if out:
                                    yield {"type": "thinking", "text": f"↩ {out}"}

                        # ── Codex --json (eski format) ──────────────────────
                        elif ev_type == "function_call":
                            name = ev.get("name", "")
                            args = ev.get("arguments", {})
                            hint = f"🔧 `{name}`"
                            if isinstance(args, dict):
                                if "path" in args:
                                    hint += f" → `{args['path']}`"
                                elif "action" in args:
                                    hint += f" → `{args['action']}`"
                            yield {"type": "thinking", "text": hint}
                        elif ev_type == "function_call_output":
                            out = str(ev.get("output", ""))[:200]
                            if out:
                                yield {"type": "thinking", "text": f"↩ {out}"}
                        elif ev_type == "reasoning":
                            t = ev.get("content", ev.get("text", "")).strip()
                            if t:
                                yield {"type": "thinking", "text": t}
                        elif ev_type == "message":
                            # Codex final message veya Gemini user/assistant message
                            role = ev.get("role", "")
                            if role == "assistant":
                                content = ev.get("content", "")
                                if isinstance(content, str) and content:
                                    full_text += content
                                    yield {"type": "delta", "text": content}
                                elif isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict) and block.get("type") == "text":
                                            t = block.get("text", "")
                                            if t:
                                                full_text += t
                                                yield {"type": "delta", "text": t}

                        continue
                    except _json.JSONDecodeError:
                        pass  # JSON değilse plain text olarak işle

                # Plain text fallback
                full_text += raw + "\n"
                yield {"type": "delta", "text": raw + "\n"}

            await process.wait()
            await stderr_task
            # PTY master fd cleanup
            if _pty_master_fd is not None:
                try:
                    os.close(_pty_master_fd)
                except OSError:
                    pass

            logger.info(
                f"[CLIProvider:{self.binary_name}][DONE] "
                f"rc={process.returncode} | lines={line_count} | chars={len(full_text)} | "
                f"stderr={len(stderr_buffer)} | süre={asyncio.get_event_loop().time()-_start:.1f}s"
            )

            if process.returncode not in (0, 1, None):
                stderr_full = "\n".join(stderr_buffer)
                logger.error(f"[CLIProvider:{self.binary_name}][FAILED] rc={process.returncode}\nSTDERR:\n{stderr_full}")
                yield {"type": "error", "content": f"❌ CLI hata (rc={process.returncode}): {stderr_full[:500] or '(boş)'}"}
            elif line_count == 0 and not _is_agy:
                # NOT: agy --print stdout'u non-TTY'de SESSİZCE kaybolur (repo bug #76) —
                # bu agy için NORMALDİR (yanıt conversation .db'sinden okunur, bkz.
                # agent_runner._run_agy_session). Bu yüzden agy'de boş stdout'u hata SAYMA;
                # diğer CLI'larda (claude/codex) boş stdout gerçek başarısızlıktır.
                stderr_full = "\n".join(stderr_buffer)
                logger.error(f"[CLIProvider:{self.binary_name}][NO_OUTPUT] Stdout boş!\nSTDERR:\n{stderr_full}")
                yield {"type": "error", "content": f"⚠️ Çıktı yok. Hata: {stderr_full[:500]}"}

            yield {"type": "final", "text": self._clean_response(full_text)}

        except Exception as e:
            logger.exception(f"[CLIProvider:{self.binary_name}] Exception in analyze_code")
            yield {"type": "error", "content": f"❌ CLI Bridge Hatası: {str(e)}"}

    async def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096,
                                         images: Optional[List[str]] = None,
                                         thinking_level: str = "medium", cwd: Optional[str] = None,
                                         interactive: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        async for ev in self.analyze_code(prompt, max_tokens, images, thinking_level, cwd, interactive):
            yield ev

    def _set_agy_model(self, agy_model_name: str, workspace: str = ""):
        """Subclass'lar agy model ayarını override edebilir. Base'de no-op."""
        pass


# Backward-compat alias
CLIProvider = BaseCLIProvider
