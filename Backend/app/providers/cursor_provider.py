import os
import json
import logging
from .cli_base import BaseCLIProvider
from .oneshot_cli import resolve_cursor_cmd, split_model_id

logger = logging.getLogger(__name__)


class CursorProvider(BaseCLIProvider):
    """Cursor CLI (`agent`) — print-mode + resmi --resume ile tur bazlı sürülür.

    Çıktı formatı stream-json, Claude Code'un stream-json'ına çok yakın
    (type: system/user/assistant/thinking/result) — cli_base parser'ı
    çoğunu zaten anlıyor; cursor'a özgü eklemeler cli_base'de işlenir.
    Yazma izni İSTEMEZ (--force verilmez): dosya/shell işleri prompt'la
    unityai MCP'ye yönlendirilir → onay kartı bizim UI'da çıkar.
    """

    # agent_runner her tur spawn öncesi doldurur:
    resume_session_id = None   # önceki turun chatId'si (--resume)

    def _build_cmd(self, prompt: str, thinking_level: str = "medium", workspace: str = None) -> list:
        base = resolve_cursor_cmd()
        if not base:
            # cli_base._cli_installed bunu yakalayıp temiz hata verir
            return ["cursor-agent-not-found", prompt]

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
            "\nFILE & TERMINAL operations — use ONLY the unityai MCP tools (your own\n"
            "write/shell tools are sandboxed and will be denied):\n"
            "- Create/edit files:  unityai save_file\n"
            "- Delete files:       unityai delete_file\n"
            "- Shell commands:     unityai run_terminal_command\n"
            "- Read file:          unityai read_file  |  List dir: unityai list_directory\n"
            "Be concise. Never claim you cannot do something — use the tools.\n\n"
        )

        cmd = [
            *base,
            "-p",
            "--output-format", "stream-json",
            "--stream-partial-output",
            "--trust",
            "--approve-mcps",
        ]
        if model and model != "auto":
            cmd += ["--model", model]
        if self.resume_session_id:
            cmd += ["--resume", self.resume_session_id]
        # Prompt SON pozisyonel arg (cli_base'in cmd/c stdin-pop fallback'iyle uyumlu;
        # doğrudan node spawn'da çok satırlı argv zaten güvenli).
        cmd.append(mcp_hint + prompt)
        return cmd

    def _register_mcp(self, launcher: str, workspace: str, backend_url: str):
        """Cursor, workspace'teki .cursor/mcp.json'ı otomatik yükler."""
        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager

        try:
            cfg_dir = os.path.join(workspace, ".cursor")
            os.makedirs(cfg_dir, exist_ok=True)
            cfg_path = os.path.join(cfg_dir, "mcp.json")

            unityai_env = {"UNITYAI_URL": backend_url, "WORKSPACE": workspace}
            token = os.environ.get("LOCAL_APP_TOKEN", "")
            if token:
                unityai_env["LOCAL_APP_TOKEN"] = token

            config = {
                "mcpServers": {
                    "unityai": {
                        "command": launcher,
                        "args": ["--workspace", workspace],
                        "env": unityai_env,
                    }
                }
            }
            if unity_mcp_manager.is_running():
                config["mcpServers"]["unityMCP"] = {
                    "url": f"http://localhost:{unity_mcp_manager.mcp_port}/mcp"
                }

            # Kullanıcının kendi .cursor/mcp.json'ı varsa bizim server'ları üstüne
            # ekle, diğer kayıtlarına dokunma.
            existing = {}
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        existing = json.load(f) or {}
                except Exception:
                    existing = {}
            merged = {**existing, "mcpServers": {**existing.get("mcpServers", {}), **config["mcpServers"]}}
            # Unity MCP kapalıysa bayat kaydı temizle (CLI kapalı porta bağlanmaya çalışmasın)
            if not unity_mcp_manager.is_running():
                merged["mcpServers"].pop("unityMCP", None)

            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
            logger.info("[CursorProvider] .cursor/mcp.json yazıldı.")
        except Exception as e:
            logger.warning(f"[CursorProvider] MCP kaydı yapılamadı: {e}")
