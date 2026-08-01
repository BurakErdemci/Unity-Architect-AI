from secret_redaction import redact_secrets
import os
import json
import logging
from .cli_base import BaseCLIProvider
from .oneshot_cli import resolve_cursor_cmd, split_model_id
from .workspace_config import ensure_gitignored, guvenli_config_yaz

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
            # --force ŞART: headless modda MCP tool çağrıları onay bekleyip
            # reddediliyor (canlı doğrulandı). Native Write/Shell ise
            # .cursor/cli.json deny-list'i ile kapalı ("unless explicitly
            # denied") → tüm yazma/shell unityai MCP onayından geçer.
            "--force",
        ]
        # 'auto' da AÇIKÇA geçirilir: bayraksız çağrıda CLI kayıtlı varsayılan
        # (adlı) modeli dener ve Free planda "Named models unavailable" ile ölür
        # (canlı doğrulandı 2026-07-13).
        cmd += ["--model", model or "auto"]
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
            # Token config dosyasına yazılmıyor — 0600 dosyadan okunuyor
            # (bkz. local_token_file). Bu dosya model tarafından okunabilir.

            config = {
                "mcpServers": {
                    "unityai": {
                        "command": launcher,
                        "args": ["--workspace", workspace],
                        "env": unityai_env,
                    }
                }
            }
            # ⚠️ DOĞRULANMADI: cursor bu makinede kurulu değil, `headers` alanını
            # gerçekten gönderip göndermediği ÖLÇÜLEMEDİ. claude/kimi şemasıyla
            # aynı yazılıyor çünkü ikisi de bu adı kullanıyor; cursor sessizce
            # yok sayarsa bağlantı 401 alır — sessiz sızıntı değil, gürültülü
            # arıza. Kurulunca ölçülmeli.
            unity_mcp_url = unity_mcp_manager.mcp_url()
            if unity_mcp_url:
                config["mcpServers"]["unityMCP"] = {
                    "url": unity_mcp_url,
                    "headers": unity_mcp_manager.api_headers(),
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
            # Unity MCP kapalıysa VEYA sır bizde yoksa bayat kaydı temizle: ikinci
            # durumda eski URL artık 404 alır, CLI bağlanamayan MCP'de takılır.
            if not unity_mcp_url:
                merged["mcpServers"].pop("unityMCP", None)

            # ⚠️ Düz `open` DEĞİL: bu dosya kullanıcının projesinde ve yolu
            # yönlendirilmiş olabilir (K4, iki vektör de ayrıcalıksız ölçüldü).
            if not guvenli_config_yaz(workspace, ".cursor/mcp.json",
                                      json.dumps(merged, indent=2), sir_tasiyor=True):
                logger.error("[CursorProvider] .cursor/mcp.json güvenli yazılamadı; "
                             "unityMCP bu oturumda bağlanmayacak.")
                return
            logger.info("[CursorProvider] .cursor/mcp.json yazıldı.")
            # Dosyayı yazan nokta girdisini de yazar. Bu dosya unityMCP
            # `X-API-Key`'ini düz metin taşıyor ve kullanıcının deposunda duruyor;
            # 29 Tem ölçümünde gerçek bir projede İZLENİYORDU.
            ensure_gitignored(workspace, [".cursor/mcp.json"])

            # İzin politikası: --force ile birlikte native Write/Shell'i deny-list'le
            # kapat (şema hem allow hem deny İSTİYOR; BOM'suz yazılmalı).
            cli_cfg_path = os.path.join(cfg_dir, "cli.json")
            cli_existing = {}
            if os.path.exists(cli_cfg_path):
                try:
                    with open(cli_cfg_path, "r", encoding="utf-8-sig") as f:
                        cli_existing = json.load(f) or {}
                except Exception:
                    cli_existing = {}
            perms = cli_existing.get("permissions") or {}
            deny = list(perms.get("deny") or [])
            for rule in ("Write(**)", "Shell(**)"):
                if rule not in deny:
                    deny.append(rule)
            cli_existing["permissions"] = {"allow": list(perms.get("allow") or []), "deny": deny}
            # ⚠️ Bu dosya K4'ün EN SİNSİ vakası: Cursor'un `Write`/`Shell`
            # deny-list'ini taşıyor. Yönlendirilirse görünen sonuç bir dosyanın
            # ezilmesi DEĞİL, politikanın sessizce kaybı olur — kısıt hedef
            # workspace'e hiç uygulanmaz ve kimse fark etmez.
            if not guvenli_config_yaz(workspace, ".cursor/cli.json",
                                      json.dumps(cli_existing, indent=2)):
                logger.error("[CursorProvider] .cursor/cli.json güvenli yazılamadı; "
                             "izin politikası UYGULANMADI.")
                return
            logger.info("[CursorProvider] .cursor/cli.json izin politikası yazıldı.")
            ensure_gitignored(workspace, [".cursor/cli.json"])
        except Exception as e:
            logger.warning(f"[CursorProvider] MCP kaydı yapılamadı: {redact_secrets(str(e))}")
