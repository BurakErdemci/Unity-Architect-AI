import os
import json
import shutil
import logging
from .cli_base import BaseCLIProvider

logger = logging.getLogger(__name__)


class AgyProvider(BaseCLIProvider):

    @staticmethod
    def _agy_binary() -> str:
        """agy CLI'ını kullanıcının PC'sinde bulur (gömülü değil — dış kurulum).
        PATH'te yoksa yaygın kurulum yollarına bakar, son çare 'agy'."""
        found = shutil.which("agy")
        if found:
            return found
        for cand in (
            os.path.expanduser("~/.local/bin/agy"),
            "/opt/homebrew/bin/agy",
            "/usr/local/bin/agy",
        ):
            if os.path.exists(cand):
                return cand
        return "agy"  # PATH'e güven (subprocess başlatılınca çözülür)

    def _build_cmd(self, prompt: str, thinking_level: str = "medium", workspace: str = None) -> list:
        """agy komutunu kurar. Prompt cli_base tarafından SON POZİSYONEL ARG olarak
        eklenir (stdin DEĞİL — agy 1.1.1 stdin'i bozdu: ham-metin stdin verilince
        prompt'u görmeyip help/derail'e düşüyor; canlı doğrulandı).

        agy 1.1.1 derail kuralı (canlı doğrulandı): bazı flag'ler modele 'kullanıcı bu
        flag'i soruyor' gibi görünüp built-in antigravity-guide skill'ini tetikliyor →
        kullanıcının mesajı hiç yanıtlanmıyor. Bu yüzden:
        - --dangerously-skip-permissions YOK → yerine settings.json toolPermission=always-proceed
        - --print-timeout YOK → default 5dk + kendi subprocess timeout'umuz
        - --mode YOK → hâlâ derail ediyor (1.1.2 canlı doğrulandı)
        - --conversation VAR (RESUME AKTİF, 2026-07-15): 1.1.2'de NORMAL devam mesajıyla
          derail ETMİYOR (canlı: 'Gölge Avcısı' görevini hatırlayıp doğal devam etti;
          'analiz' framing'i yalnız transcript'e dair META-sorularda çıkıyor). _resume_uuid
          set'liyse native disk-resume → context prompt'a enjekte edilmez (26K kırpma yok).
        """
        full_id = self.binary_name
        # Tüm agy modelleri: Gemini, Claude Sonnet/Opus, GPT-OSS
        self._pending_agy_model = self._AGY_MODEL_MAP.get(full_id, "Gemini 3.6 Flash (High)")
        cmd = [self._agy_binary()]
        if workspace:
            cmd += ["--add-dir", workspace]
        resume_uuid = getattr(self, "_resume_uuid", None)
        if resume_uuid:
            cmd += [f"--conversation={resume_uuid}"]
        cmd += ["--print"]  # prompt cli_base'de son arg olarak eklenir
        # ⚠️ --model FLAG'İ EKLENMEZ — derail tetikliyor (agy guide-skill'e düşüp
        # kullanıcının mesajını yanıtlamıyor; 2026-07-24 canlı doğrulandı). Model,
        # _set_agy_model ile settings.json "model" key'inden seçilir.
        return cmd

    def _set_agy_model(self, agy_model_name: str, workspace: str = ""):
        """~/.gemini/antigravity-cli/settings.json ve global ~/.gemini/settings.json
        içindeki modeli, trustedWorkspaces, toolPermission ve disabledTools'u günceller.

        Model seçimi SADECE buradan yapılır (komut satırında --model YOK — o derail
        tetikliyor, bkz. _build_cmd). Her çağrıda "model" key'i GÜNCEL değere yazılır;
        bu sayede eski stale değer (örn. önceki oturumdan "Gemini 3.5 Flash (High)")
        üzerine yazılır — canlı doğrulandı (2026-07-24): stale key kalınca model
        kendini yanlış tanıtıyordu, güncel display-name yazılınca düzeliyor."""
        # 1. Lokal antigravity-cli settings.json
        settings_path = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")
        try:
            with open(settings_path) as f:
                settings = json.load(f)
        except Exception:
            settings = {"colorScheme": "dark", "trustedWorkspaces": []}
        settings["model"] = agy_model_name
        settings["toolPermission"] = "always-proceed"  # --dangerously-skip-permissions flag'i YERİNE (canlı doğrulandı: geçerli değer, flag'siz auto-approve → skill-derail'i tetiklemez)
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
        global_settings["toolPermission"] = "always-proceed"  # --dangerously-skip-permissions YERİNE (geçerli değer, flag'siz auto-approve)
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

    def _write_cli_env(self, launcher: str, workspace: str, backend_url: str):
        """Backend/.unityai_cli.env yazar — 'unityai' wrapper bu dosyayı source eder.
        launcher = .../Backend/run_mcp_server.sh → backend_dir = .../Backend."""
        backend_dir = os.path.dirname(launcher)
        env_path = os.path.join(backend_dir, ".unityai_cli.env")
        lines = [
            f"UNITYAI_URL={backend_url}",
            f"WORKSPACE={workspace}",
        ]
        # LOCAL_APP_TOKEN bu env dosyasına yazılmıyor; 0600 dosyadan okunuyor.
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
        # Bu env sözlüğü ~/.gemini/settings.json'a yazılıyor — token oraya
        # girmiyor: dosya paylaşımlı (Jarvan da aynı dosyayı kullanıyor) ve
        # sırrın config'e yayılması denetimin C grubu bulgusuydu.
        env = {"UNITYAI_URL": backend_url, "WORKSPACE": workspace}

        # 0. unityai CLI env dosyası — agy run_command env'i propagate etmese bile
        #    CLI doğru backend'e/token'a/workspace'e bağlanmayı garanti eder.
        self._write_cli_env(launcher, workspace, backend_url)
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
        # ⚠️ DOĞRULANMADI: agy'nin `headers` alanını gönderdiği ölçülemedi — bu
        # config `~/.gemini/settings.json`'ı paylaşıyor (başka bir asistan da onu
        # kullanıyor) ve izole bir kopyayla ölçmek mümkün olmadı. Alan yine de
        # yazılıyor: yok sayılırsa bağlantı 401 alır, yani sessiz sızıntı değil
        # gürültülü arıza olur. None → kayıt silinir.
        unity_mcp_url = unity_mcp_manager.mcp_url(host="127.0.0.1")
        if unity_mcp_url:
            config["mcpServers"]["unityMCP"] = {
                "serverUrl": unity_mcp_url,
                "headers": unity_mcp_manager.api_headers(),
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

        # 1b. GÖÇ SONRASI yol: ~/.gemini/config/mcp_config.json
        # KRİTİK (2026-07-14 canlı doğrulandı, agy 1.1.2): agy artık MCP server'larını
        # BU göç-sonrası yoldan okuyor (~/.gemini/config/.migrated marker'ı mevcut; CLI
        # issue #60). Eski antigravity-cli/mcp_config.json ARTIK OKUNMUYOR → sadece oraya
        # yazınca agy hiçbir MCP tool'u görmüyordu (yalnız built-in default_api:*). Aynı
        # config'i buraya da yazınca --print modunda unityMCP + meshy + unityai tool'ları
        # görünüyor (canlı: meshy_check_balance çağrısı PASS). Migrated dosyada zaten olan
        # (IDE'nin eklediği meshy/playwright gibi) server'ları koru; taze unityai/unityMCP öncelikli.
        migrated_path = os.path.expanduser("~/.gemini/config/mcp_config.json")
        try:
            migrated_cfg = {}
            try:
                with open(migrated_path) as f:
                    _raw = f.read().strip()
                    migrated_cfg = json.loads(_raw) if _raw else {}
            except Exception:
                migrated_cfg = {}
            merged_servers = dict(migrated_cfg.get("mcpServers", {}))
            merged_servers.update(config.get("mcpServers", {}))  # taze unityai/unityMCP kazanır
            merged_servers.pop("antigravity", None)
            out_cfg = dict(migrated_cfg)
            out_cfg["mcpServers"] = merged_servers
            out_cfg.pop("disabledTools", None)  # geçersiz key → agy tüm dosyayı yoksayar
            os.makedirs(os.path.dirname(migrated_path), exist_ok=True)
            with open(migrated_path, "w") as f:
                json.dump(out_cfg, f, indent=2)
            logger.info(f"[CLIProvider] agy MIGRATED mcp_config.json yazıldı ({len(merged_servers)} server): {migrated_path}")
        except Exception as e:
            logger.warning(f"[CLIProvider] agy migrated mcp_config.json yazılamadı: {e}")

        # 2. ~/.gemini/antigravity-cli/settings.json güncelle
        settings_path = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")
        try:
            with open(settings_path) as f:
                settings = json.load(f)
        except Exception:
            settings = {"colorScheme": "dark", "trustedWorkspaces": []}
        settings.setdefault("mcpServers", {}).pop("antigravity", None)
        settings["mcpServers"]["unityai"] = dict(unityai_entry)
        settings["toolPermission"] = "always-proceed"  # --dangerously-skip-permissions flag'i YERİNE (canlı doğrulandı: geçerli değer, flag'siz auto-approve → skill-derail'i tetiklemez)
        settings["disabledTools"] = self._AGY_DISABLED_TOOLS
        if unity_mcp_url:
            settings["mcpServers"]["unityMCP"] = {
                "serverUrl": unity_mcp_url,
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
        global_settings["toolPermission"] = "always-proceed"  # --dangerously-skip-permissions YERİNE (geçerli değer, flag'siz auto-approve)
        global_settings["disabledTools"] = self._AGY_DISABLED_TOOLS
        if unity_mcp_url:
            global_settings["mcpServers"]["unityMCP"] = {
                "serverUrl": unity_mcp_url,
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
