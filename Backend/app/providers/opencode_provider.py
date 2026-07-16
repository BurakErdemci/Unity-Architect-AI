import os
import json
import logging
from .cli_base import BaseCLIProvider
from .oneshot_cli import resolve_opencode_cmd, split_model_id

logger = logging.getLogger(__name__)


class OpenCodeProvider(BaseCLIProvider):
    """OpenCode — `opencode run` + resmi -s/--session resume.

    • Model: `opencode:<provider/model>` bizim ID'si → `-m provider/model`.
      OpenCode'un opencode/* modelleri auth'suz ÜCRETSİZ çalışır (canlı
      doğrulandı) → uygulamamıza sıfır-kurulum "bedava mod" kazandırır.
    • Çıktı: --format json → event akışı (text / tool_use / step_start /
      step_finish; sessionID her event'te) — cli_base'de işlenir.
    • İzinler: workspace opencode.json'da edit/bash "deny" → dosya/shell
      yalnız unityai MCP'den (onaylı) geçebilir. Kullanıcının mevcut
      opencode.json'ı varsa merge edilir, diğer ayarlarına dokunulmaz.
    """

    resume_session_id = None   # önceki turun sessionID'si (-s)

    def _build_cmd(self, prompt: str, thinking_level: str = "medium", workspace: str = None) -> list:
        base = resolve_opencode_cmd()
        if not base:
            return ["opencode-not-found", prompt]

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
            "\nFILE & TERMINAL operations — your built-in edit and bash tools are\n"
            "DENIED by workspace policy. Use ONLY the unityai MCP tools:\n"
            "- Create/edit files:  unityai save_file\n"
            "- Delete files:       unityai delete_file\n"
            "- Shell commands:     unityai run_terminal_command\n"
            "- Read file:          unityai read_file  |  List dir: unityai list_directory\n"
            "Be concise. Never claim you cannot do something — use the tools.\n\n"
        )

        cmd = [*base, "run", "--format", "json"]
        if model:
            cmd += ["-m", model]
        if self.resume_session_id:
            cmd += ["-s", self.resume_session_id]
        # Mesaj son pozisyonel arg (opencode.exe native → çok satırlı argv güvenli)
        cmd.append(mcp_hint + prompt)
        return cmd

    def _register_mcp(self, launcher: str, workspace: str, backend_url: str):
        """Workspace opencode.json'a unityai/unityMCP kaydı + izin politikası yazar."""
        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager

        try:
            cfg_path = os.path.join(workspace, "opencode.json")
            unityai_env = {"UNITYAI_URL": backend_url, "WORKSPACE": workspace}
            token = os.environ.get("LOCAL_APP_TOKEN", "")
            if token:
                unityai_env["LOCAL_APP_TOKEN"] = token

            mcp = {
                "unityai": {
                    "type": "local",
                    "command": [launcher, "--workspace", workspace],
                    "environment": unityai_env,
                    "enabled": True,
                }
            }
            if unity_mcp_manager.is_running():
                mcp["unityMCP"] = {
                    "type": "remote",
                    "url": f"http://localhost:{unity_mcp_manager.mcp_port}/mcp",
                    "enabled": True,
                }

            existing = {}
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        existing = json.load(f) or {}
                except Exception:
                    existing = {}

            merged = {
                "$schema": existing.get("$schema", "https://opencode.ai/config.json"),
                **existing,
                "mcp": {**existing.get("mcp", {}), **mcp},
                # Yazma/shell CLI içinde kapalı → unityai MCP (onaylı) tek yol
                "permission": {**existing.get("permission", {}), "edit": "deny", "bash": "deny"},
            }
            if not unity_mcp_manager.is_running():
                merged["mcp"].pop("unityMCP", None)

            # Reasoning effort: opencode CLI flag sunmaz — model options'a yazılır
            # (provider.<id>.models.<model>.options.reasoningEffort). auto → dokunma.
            try:
                from .oneshot_cli import split_model_id
                from .effort_caps import map_effort
                _, _mid = split_model_id(self.binary_name)
                _lvl = getattr(self, "_effort_level", "auto")
                _r = map_effort("subscription", f"opencode:{_mid or ''}", _lvl).get("opencode_reasoning")
                if _r and _mid and "/" in _mid:
                    _pid, _m = _mid.split("/", 1)
                    node = (merged.setdefault("provider", {})
                                  .setdefault(_pid, {})
                                  .setdefault("models", {})
                                  .setdefault(_m, {}))
                    node.setdefault("options", {})["reasoningEffort"] = _r
            except Exception:
                pass

            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
            logger.info("[OpenCodeProvider] opencode.json yazıldı.")
        except Exception as e:
            logger.warning(f"[OpenCodeProvider] opencode.json yazılamadı: {e}")
