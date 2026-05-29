import os
import json
import logging
from .cli_base import BaseCLIProvider

logger = logging.getLogger(__name__)


class AgyProvider(BaseCLIProvider):

    def _build_cmd(self, prompt: str, thinking_level: str = "medium", workspace: str = None) -> list:
        full_id = self.binary_name
        # Tüm agy modelleri: Gemini, Claude Sonnet/Opus, GPT-OSS
        # Prompt stdin'den geçecek (ARG_MAX güvenliği) — cmd'ye dahil edilmez
        self._pending_agy_model = self._AGY_MODEL_MAP.get(full_id, "Gemini 3.5 Flash (High)")
        cmd = [
            "/Users/burakemreerdemci/.local/bin/agy",
            "--print",
            "--dangerously-skip-permissions",
            "--print-timeout", "180s",
        ]
        if workspace:
            cmd = [cmd[0], "--add-dir", workspace] + cmd[1:]
        return cmd

    def _set_agy_model(self, agy_model_name: str, workspace: str = ""):
        """~/.gemini/antigravity-cli/settings.json ve global ~/.gemini/settings.json içindeki modeli, trustedWorkspaces ve disabledTools'u günceller."""
        # 1. Lokal antigravity-cli settings.json
        settings_path = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")
        try:
            with open(settings_path) as f:
                settings = json.load(f)
        except Exception:
            settings = {"colorScheme": "dark", "trustedWorkspaces": []}
        settings["model"] = agy_model_name
        settings.pop("toolPermission", None)  # geçersiz/junk değer agy'nin TÜM ayarı (disabledTools dahil) reddetmesine yol açıyor
        settings["disabledTools"] = self._AGY_DISABLED_TOOLS
        if workspace:
            trusted = settings.get("trustedWorkspaces", [])
            if workspace not in trusted:
                trusted.append(workspace)
            settings["trustedWorkspaces"] = trusted
        try:
            with open(settings_path, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            logger.warning(f"[CLIProvider] Lokal agy settings.json model güncellenemedi: {e}")

        # 2. Global ~/.gemini/settings.json
        global_settings_path = os.path.expanduser("~/.gemini/settings.json")
        try:
            with open(global_settings_path) as f:
                global_settings = json.load(f)
        except Exception:
            global_settings = {}
        global_settings["model"] = agy_model_name
        global_settings.pop("toolPermission", None)  # geçersiz/junk değer agy ayar yüklemesini bozuyor
        global_settings["disabledTools"] = self._AGY_DISABLED_TOOLS
        if workspace:
            global_trusted = global_settings.get("trustedWorkspaces", [])
            if workspace not in global_trusted:
                global_trusted.append(workspace)
            global_settings["trustedWorkspaces"] = global_trusted
        try:
            with open(global_settings_path, "w") as f:
                json.dump(global_settings, f, indent=2)
        except Exception as e:
            logger.warning(f"[CLIProvider] Global settings.json model güncellenemedi: {e}")

        logger.info(f"[CLIProvider] agy model → {agy_model_name}, trusted → {workspace}")

    def _write_cli_env(self, launcher: str, workspace: str, backend_url: str, local_app_token: str):
        """Backend/.unityai_cli.env yazar — 'unityai' wrapper bu dosyayı source eder.
        launcher = .../Backend/run_mcp_server.sh → backend_dir = .../Backend."""
        backend_dir = os.path.dirname(launcher)
        env_path = os.path.join(backend_dir, ".unityai_cli.env")
        lines = [
            f"UNITYAI_URL={backend_url}",
            f"WORKSPACE={workspace}",
        ]
        if local_app_token:
            lines.append(f"LOCAL_APP_TOKEN={local_app_token}")
        try:
            with open(env_path, "w") as f:
                f.write("\n".join(lines) + "\n")
            logger.info(f"[CLIProvider] unityai CLI env yazıldı: {env_path}")
        except Exception as e:
            logger.warning(f"[CLIProvider] unityai CLI env yazılamadı: {e}")

    def _register_mcp(self, launcher: str, workspace: str, backend_url: str):
        """agy config dosyalarını günceller.

        ÖNEMLİ: agy --print modu HİÇBİR MCP server'ını yüklemez (stdio da HTTP da)
        — doğrudan test edildi. Bu yüzden agy mcp__unityai__* araçlarını GÖREMEZ.
        Bunun yerine agy, run_command built-in aracıyla 'unityai' CLI'ını çağırır
        (bkz. cli_base mcp_hint). Buradaki MCP kaydı sadece agy interaktif modda
        kullanılırsa diye tutulur; --print akışında etkisizdir. Asıl iş .unityai_cli.env
        + disabledTools (agy'nin gerçek write araçlarını kapatma) ile yapılır.
        """
        local_app_token = os.environ.get("LOCAL_APP_TOKEN", "")
        env = {"UNITYAI_URL": backend_url, "WORKSPACE": workspace}
        if local_app_token:
            env["LOCAL_APP_TOKEN"] = local_app_token

        # 0. unityai CLI env dosyası — agy run_command env'i propagate etmese bile
        #    CLI doğru backend'e/token'a/workspace'e bağlanmayı garanti eder.
        self._write_cli_env(launcher, workspace, backend_url, local_app_token)
        unityai_entry = {
            "command": launcher, "args": ["--workspace", workspace],
            "env": env, "trust": True,
        }

        # 1. ~/.gemini/antigravity-cli/mcp_config.json güncelle
        config_path = os.path.expanduser("~/.gemini/antigravity-cli/mcp_config.json")
        try:
            with open(config_path) as f:
                config = json.load(f)
        except Exception:
            config = {}
        config.setdefault("mcpServers", {}).pop("antigravity", None)
        config["mcpServers"]["unityai"] = dict(unityai_entry)
        # disabledTools mcp_config.json'da OLMAMALI — agy geçersiz key görünce tüm dosyayı
        # yoksayarak MCP server'ları başlatmaz. disabledTools sadece settings.json'da olmalı.
        config.pop("disabledTools", None)

        from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
        if unity_mcp_manager.is_running():
            config["mcpServers"]["unityMCP"] = {
                "serverUrl": f"http://127.0.0.1:{unity_mcp_manager.mcp_port}/mcp",
                "type": "http", "trust": True,
            }
        else:
            config["mcpServers"].pop("unityMCP", None)

        try:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            logger.info(f"[CLIProvider] agy mcp_config.json güncellendi: {backend_url} → {workspace}")
        except Exception as e:
            logger.warning(f"[CLIProvider] agy mcp_config.json yazılamadı: {e}")

        # 2. ~/.gemini/antigravity-cli/settings.json güncelle
        settings_path = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")
        try:
            with open(settings_path) as f:
                settings = json.load(f)
        except Exception:
            settings = {"colorScheme": "dark", "trustedWorkspaces": []}
        settings.setdefault("mcpServers", {}).pop("antigravity", None)
        settings["mcpServers"]["unityai"] = dict(unityai_entry)
        settings.pop("toolPermission", None)  # geçersiz/junk değer agy'nin TÜM ayarı (disabledTools dahil) reddetmesine yol açıyor
        settings["disabledTools"] = self._AGY_DISABLED_TOOLS
        if unity_mcp_manager.is_running():
            settings["mcpServers"]["unityMCP"] = {
                "serverUrl": f"http://127.0.0.1:{unity_mcp_manager.mcp_port}/mcp",
                "type": "http", "trust": True,
            }
        else:
            settings["mcpServers"].pop("unityMCP", None)

        try:
            with open(settings_path, "w") as f:
                json.dump(settings, f, indent=2)
            logger.info(f"[CLIProvider] agy settings.json güncellendi: {backend_url} → {workspace}")
        except Exception as e:
            logger.warning(f"[CLIProvider] agy settings.json yazılamadı: {e}")

        # 3. Global ~/.gemini/settings.json güncelle
        global_settings_path = os.path.expanduser("~/.gemini/settings.json")
        try:
            with open(global_settings_path) as f:
                global_settings = json.load(f)
        except Exception:
            global_settings = {}
        global_settings.setdefault("mcpServers", {})["unityai"] = dict(unityai_entry)
        global_settings.pop("toolPermission", None)  # geçersiz/junk değer agy ayar yüklemesini bozuyor
        global_settings["disabledTools"] = self._AGY_DISABLED_TOOLS
        if unity_mcp_manager.is_running():
            global_settings["mcpServers"]["unityMCP"] = {
                "serverUrl": f"http://127.0.0.1:{unity_mcp_manager.mcp_port}/mcp",
                "type": "http", "trust": True,
            }
        else:
            global_settings["mcpServers"].pop("unityMCP", None)

        try:
            with open(global_settings_path, "w") as f:
                json.dump(global_settings, f, indent=2)
            logger.info(f"[CLIProvider] Global settings.json güncellendi: {backend_url} → {workspace}")
        except Exception as e:
            logger.warning(f"[CLIProvider] Global settings.json yazılamadı: {e}")

    def _write_gemini_policy(self, workspace: str) -> str:
        """
        Gemini CLI'ın built-in araçlarını deny eden policy dosyasını TOML formatında yazar.
        --policy flag'i JSON değil TOML bekler; JSON olunca sessizce ignore edilir.
        """
        deny_tools = [
            "run_shell_command",  # Native terminal → MCP run_terminal_command kullanmak zorunda kalır
            "replace",            # Native text replace → MCP write_file kullanmak zorunda kalır
        ]
        # Her araç için ayrı [[rule]] bloğu gerekiyor (TOML array of tables)
        lines = []
        for i, tool in enumerate(deny_tools, start=1):
            lines.append("[[rule]]")
            lines.append(f'toolName = "{tool}"')
            lines.append('decision = "deny"')
            lines.append(f'priority = {i}')
            lines.append("")
        toml_content = "\n".join(lines)

        policy_path = os.path.join(workspace, ".gemini_antigravity_policy.toml")
        try:
            with open(policy_path, "w") as f:
                f.write(toml_content)
        except Exception as e:
            logger.error(f"[CLIProvider] Gemini policy yazılamadı: {e}")
        return policy_path

    # Backward-compat alias: eski kod _register_agy_mcp'yi de çağırabilir
    _register_agy_mcp = _register_mcp
