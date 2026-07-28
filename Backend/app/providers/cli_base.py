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


# ── Alt sürece geçen ortamın İZİN LİSTESİ ────────────────────────────────────
#
# Neden allow-list, neden `{**os.environ}` değil (ölçüm 2026-07-28): altı canary
# ebeveynin ortamına konup her spawn noktasında çocuğun gördüğü env yakalandı;
# beş spawn noktasının BEŞİNDE de ALTISI birden geçiyordu — LOCAL_APP_TOKEN,
# API_KEY_ENCRYPTION_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY,
# AWS_SECRET_ACCESS_KEY. Yani kullanıcı Cursor'u seçtiğinde `cursor-agent`
# süreci Anthropic anahtarını, veritabanı şifreleme anahtarını ve backend'in tek
# yetki kanıtı olan bearer token'ı okuyabiliyordu.
#
# Aynı desen C# tarafında zaten uygulanmıştı (`omnisharp_manager._ENV_ALLOWLIST`);
# burası onun sağlayıcı tarafındaki eşi. Ondan farkı İKİ KATMANLI olması:
#   (a) _BASE_ENV_ALLOWLIST — her sağlayıcının çalışması için gereken işletimsel
#       taban (yol, ev dizini, yerel ayar, proxy, TLS kökü, node araç zinciri),
#   (b) _PROVIDER_ENV_ALLOWLIST — yalnız O sağlayıcının KENDİ kimlik/uç-nokta
#       değişkenleri. Bu ayrım düzeltmenin bütün değeri: tek düz liste ya
#       sızıntıyı sürdürür ya da env ile giriş yapan kullanıcının CLI'ını kırar.
#
# ⚠️ Listeyi DARALTIRKEN dikkat: buradan düşen bir ad sağlayıcının hiç
# çalışmamasına yol açar ve arıza SESSİZDİR — CLI bulunamaz, ya da kurumsal ağda
# her HTTPS çağrısı sertifika hatasıyla düşer, ya da CLI oturum dosyasını bulamayıp
# "giriş yapın" der. Bu düzeltmenin başarısızlık yönü sızıntı değil, ÜRÜNÜN
# SESSİZCE KIRILMASI.
#
# Liste bilerek TEK parça: Windows'a özgü adlar da burada duruyor ve yalnız
# gerçekten VAR olanlar kopyalanıyor (macOS'ta hiçbiri eklenmiyor). os.name'e
# göre dallanmak Windows dalını macOS'tan sınanamaz kılardı — bu depoda
# dallanmayı azaltmak doğrulanabilirliğin kendisi.
_BASE_ENV_ALLOWLIST = (
    # Süreç başlatma ve dosya sistemi. PATH olmadan CLI binary'si hiç bulunamaz
    # (main.py PATH'i ayrıca augment ediyor: Finder'dan başlatılan uygulamanın
    # PATH'i npm/nvm/homebrew dizinlerini taşımıyor). HOME her CLI'ın oturum ve
    # config dizini için zorunlu — ~/.claude, ~/.codex, ~/.gemini, ~/.kimi-code
    # hepsi oradan çözülüyor; HOME düşerse kullanıcı her turda "giriş yapın" alır.
    "PATH", "HOME", "TMPDIR", "TMP", "TEMP",
    # Yerel ayar. Sohbet Türkçe: UTF-8 olmayan bir çocukta CLI'ın kendi çıktısı
    # ve dosya adları bozuluyor, JSONL parse'ı da bundan etkileniyor.
    "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "TZ",
    # Kullanıcı kimliği (sır değil). CLI'lar `run_command` için kabuk açıyor;
    # SHELL düşerse /bin/sh'a düşülüyor ve kullanıcının kabuk ayarları kayboluyor.
    "USER", "LOGNAME", "SHELL",
    # ssh-agent soketi. Modeller onay kapısından geçerek `git push` çalıştırıyor;
    # bu düşerse SSH remote'lu her push parola sorup takılıyor. Soketin kendisi
    # bir sır değil ve çocuk zaten aynı kullanıcı olarak ~/.ssh'ı okuyabiliyor —
    # yani elemek güvenlik satın almadan kullanılabilirlik satardı.
    "SSH_AUTH_SOCK",
    # Terminal. NO_COLOR/TERM/COLUMNS/LINES çağrı yerinde ZORLA ezilir (overrides),
    # ama COLORTERM gibi kalanlar buradan geçiyor.
    "TERM", "COLORTERM",
    # XDG dizinleri: Linux'ta ve bazı CLI'larda config/cache kökü HOME değil bunlar.
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME",
    "XDG_RUNTIME_DIR",
    # Kurumsal proxy. Küçük harfli biçimler ayrı adlardır ve bazı istemciler
    # (curl, node'un undici'si) yalnız birini okuyor — ikisi de geçmeli.
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    # TLS güven kökü. TLS'i kesen bir kurumsal ağda bunlardan biri düşerse
    # sağlayıcıya giden HER istek sertifika hatasıyla ölür — ve kullanıcının
    # gördüğü mesaj sebebi tamamen gizler.
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
    # Node araç zinciri: claude/codex/agy/copilot/opencode npm CLI'ları ve
    # `node` çoğu makinede nvm/fnm/volta üzerinden geliyor. Bu değişkenler
    # düşerse PATH'teki shim doğru node kurulumunu bulamıyor.
    # ⚠️ NPM_TOKEN / NODE_AUTH_TOKEN BİLEREK YOK: registry kimlik bilgisi, sır.
    "NODE_OPTIONS", "NODE_PATH", "NVM_DIR", "NVM_BIN", "NVM_INC",
    "NPM_CONFIG_PREFIX", "NPM_CONFIG_USERCONFIG", "NPM_CONFIG_CACHE",
    "FNM_DIR", "FNM_MULTISHELL_PATH", "VOLTA_HOME", "COREPACK_HOME",
    # Bizim işletimsel değişkenlerimiz (sır DEĞİL — localhost adresi ve klasör
    # yolu). MCP sunucusu ve `unityai` CLI'ı backend'i bunlardan buluyor.
    "UNITYAI_URL", "ANTIGRAVITY_URL", "WORKSPACE",
    # Windows. macOS'tan sınanamayan tek yüzey burası olduğu için adlar tek
    # listede duruyor ve varlıklarına göre kopyalanıyor (bkz. testler).
    "SystemRoot", "SystemDrive", "WINDIR", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "APPDATA", "LOCALAPPDATA", "ProgramData", "ProgramFiles", "ProgramFiles(x86)",
    "ProgramW6432", "PATHEXT", "COMSPEC", "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE", "PROCESSOR_ARCHITEW6432", "ALLUSERSPROFILE",
    "PUBLIC", "USERDOMAIN", "COMPUTERNAME", "OS", "SESSIONNAME",
)

# BİLEREK DIŞARIDA BIRAKILANLAR — her biri bir karar, unutulmuş bir ad değil:
#   LOCAL_APP_TOKEN        backend'in tek yetki kanıtı. MCP sunucusu ona ortamdan
#                          DEĞİL 0600 bir dosyadan ulaşıyor (bkz. local_token_file),
#                          yani elenmesi hiçbir yolu kırmıyor.
#   API_KEY_ENCRYPTION_KEY veritabanındaki kullanıcı API anahtarlarının şifreleme
#                          anahtarı; hiçbir CLI'ın işi yok.
#   AWS_*                  Claude Code'un Bedrock kipi bunlarla çalışıyor ama
#                          AWS_SECRET_ACCESS_KEY ölçülen canary'lerden biri ve
#                          bir sır. Bedrock/Vertex kipi bilinçli olarak
#                          desteklenmiyor — kullanıcı `claude login` kullanır.
#   PYTHONPATH/PYTHONHOME/VIRTUAL_ENV
#                          backend'in kendi venv'i; çocuğun python'una dayatılırsa
#                          çocuk yorumlayıcısı kırılır (launcher'lar PYTHONPATH'i
#                          zaten kendileri kuruyor).
#   Sağlayıcıya ait olmayan tüm *_API_KEY / *_TOKEN / *_SECRET adları.

# Sağlayıcıya ÖZEL katman: yalnız o ailenin kendi kimlik ve uç-nokta değişkenleri.
# Anahtarlar `env_family()` üzerinden çözülüyor ve o fonksiyonun önekleri
# `manager.get_provider`'ın sevk tablosuyla AYNI olmak zorunda.
_PROVIDER_ENV_ALLOWLIST = {
    # Claude Code. Abonelikle (claude login) çalışırken hiçbiri gerekmiyor; ama
    # ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN ile giriş yapmış kurulumlar var ve
    # bunları elemek onların CLI'ını sessizce auth hatasına düşürürdü.
    # BASE_URL/CUSTOM_HEADERS kurumsal gateway arkasındaki kurulumlar için.
    "claude": (
        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
        "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
        "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    ),
    # Codex. CODEX_HOME bu depoda zaten okunuyor (codex_session._configured_codex_mcp_names)
    # → config.toml'un yerini o belirliyor; düşerse MCP kayıtları görünmez olur.
    "codex": (
        "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID",
        "CODEX_HOME",
    ),
    # Antigravity/Gemini CLI. GOOGLE_APPLICATION_CREDENTIALS bir DOSYA YOLU;
    # sırrın kendisi değil ve dosyayı aynı kullanıcı zaten okuyabiliyor.
    "agy": (
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION", "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_APPLICATION_CREDENTIALS", "GEMINI_CONFIG_DIR",
    ),
    # Kimi Code. KIMI_CODE_HOME bu depoda okunuyor (kimi_provider.py).
    "kimi": ("KIMI_CODE_HOME", "KIMI_API_KEY", "MOONSHOT_API_KEY"),
    "cursor": ("CURSOR_API_KEY", "CURSOR_CONFIG_DIR"),
    # Copilot CLI kimliğini gh oturumundan ya da bu token'lardan alıyor.
    "copilot": ("GITHUB_TOKEN", "GH_TOKEN", "GH_CONFIG_DIR", "GH_HOST"),
    # ⚠️ OpenCode ÇOK SAĞLAYICILI: kullanıcı onu istediği modelin sağlayıcısıyla
    # kullanabiliyor, yani "kendi" kimlik değişkeni tek bir vendor'a ait değil.
    # Vendor anahtarları bilerek verilmiyor (verilseydi bu düzeltmenin amacı
    # OpenCode için tamamen kalkardı); kimlik `opencode auth login` ile kurulan
    # disk oturumundan gelmeli.
    "opencode": ("OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT", "OPENCODE_DISABLE_AUTOUPDATE"),
    # Unity MCP'yi başlatan `uvx` torunu. Her açılışta PyPI'dan indirdiği için
    # önbellek/python dizinleri işletimsel olarak gerekli.
    # ⚠️ UV_INDEX_URL / UV_DEFAULT_INDEX BİLEREK YOK: kimlik bilgisi gömülü bir
    # URL olabiliyor (https://user:token@...), yani sır sınıfına giriyor.
    "uvx": (
        "UV_CACHE_DIR", "UV_NO_CACHE", "UV_OFFLINE", "UV_PYTHON",
        "UV_PYTHON_INSTALL_DIR", "UV_TOOL_DIR", "UV_TOOL_BIN_DIR", "UV_NATIVE_TLS",
    ),
}

# binary_name öneki → aile. Sıra önemli DEĞİL (önekler ayrık) ama içerik
# `manager.get_provider`'ın if/elif zinciriyle birebir aynı olmak zorunda:
# ayrışırlarsa bir sağlayıcı sessizce kendi kimlik değişkenini kaybeder.
_FAMILY_PREFIXES = (
    # Tire YOK: buraya hem model adı ("cursor-gpt-5.2") hem çıplak CLI adı
    # ("cursor", `oneshot_cli.probe_named_models`) geliyor. Tireli desen çıplak
    # adı kaçırıyordu ve bilinmeyen ad "claude"a düştüğü için Cursor'un süreci
    # ANTHROPIC_API_KEY'i almaya devam ediyordu — sızıntı kapatılmış görünürken
    # tek çağrı yerinde açık kalıyordu (ölçüldü 2026-07-28, testle sabitlendi).
    ("cursor", "cursor"),
    ("copilot", "copilot"),
    ("opencode:", "opencode"),
    ("gpt-", "codex"),
    ("kimi-", "kimi"),
    ("gemini", "agy"),
    ("agy-", "agy"),
)


def env_family(binary_name: Optional[str]) -> Optional[str]:
    """`binary_name` → izin listesi ailesi.

    Bilinmeyen ad "claude" döner çünkü `manager.get_provider` de bilinmeyen adı
    ClaudeCodeProvider'a düşürüyor ("claude-* ve diğerleri"). İki tablonun
    ayrışması, çalışan bir sağlayıcının kimlik değişkenini sessizce kaybetmesi
    demek olurdu — bu depodaki arızaların ortak şekli tam olarak "birbiriyle
    uyuşması gereken iki yer uyuşmuyor".
    """
    if not binary_name:
        return None
    for prefix, family in _FAMILY_PREFIXES:
        if binary_name.startswith(prefix):
            return family
    return "claude"


def build_spawn_env(family: Optional[str] = None,
                    overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Alt süreç ortamını izin listesinden kurar. ASLA `None` dönmez.

    `None` dönmek subprocess'e "ebeveyn ortamını AYNEN devral" demek, yani
    sızıntıyı hiç kapatmayan dal olurdu — OmniSharp tarafında tam olarak bu dal
    gözden kaçmıştı (dış denetim, 2026-07-27).

    Var olmayan bir ad UYDURULMUYOR: boş dizeyle tanımlı bir değişken tanımsız
    olmakla aynı şey değil (örn. `HTTPS_PROXY=""` gören bir HTTP istemcisi boş
    proxy'yi kullanmayı deneyip bağlantıyı düşürebiliyor).

    Bunun SİMETRİĞİ de kasıtlı: ebeveynde VAR olan boş bir değer (`COLORTERM=""`)
    çocuğa aynen geçer, elenmez. Sebep aynı ayrımın diğer yönü — elemek, çocuğa
    ebeveynden farklı bir dünya göstermek olurdu ve "tanımlı ama boş" ile
    "hiç tanımlı değil" arasında ayrım yapan bir CLI'ı sessizce kırardı. Bu
    filtre yalnız hangi ADLARIN geçeceğine karar verir, değerlerine karışmaz;
    boş değer geçişi de bu fonksiyondan önceki `{**os.environ}` davranışıyla
    aynıdır, yani bir regresyon değil korunmuş davranıştır. (Dış denetim
    2026-07-28'de üstteki paragrafı "boşlar eleniyor" iddiası sanıp bunu bulgu
    olarak yazdı; iddia hiç yapılmamıştı — bu paragraf o yanlış okumayı kapatır.)

    `overrides` en son uygulanır ve izin listesini EZER: çağrı yerinin bilerek
    dayattığı değerler (NO_COLOR, ya da Unity MCP'nin argv yerine ortamla
    geçirdiği paylaşımlı sır) buradan geçer.
    """
    names = _BASE_ENV_ALLOWLIST + _PROVIDER_ENV_ALLOWLIST.get(family or "", ())
    env = {name: os.environ[name] for name in names if name in os.environ}
    if overrides:
        env.update(overrides)
    return env


def _cli_value_to_text(value: Any) -> str:
    """CLI JSON event'lerindeki metin-benzeri değerleri güvenle string'e çevirir.

    OpenCode hata event'leri bazen ``{"name": ..., "data": {"message": ...}}``
    şeklinde yapılandırılmış nesne döndürür. Bu değer doğrudan ``str + dict`` ile
    biriktirilirse bridge çöker ve asıl hata görünmez.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [_cli_value_to_text(item).strip() for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        # Önce kullanıcıya anlamlı mesaj taşıma ihtimali yüksek alanları ara.
        for key in ("message", "detail", "content", "text"):
            text = _cli_value_to_text(value.get(key)).strip()
            if text:
                name = _cli_value_to_text(value.get("name")).strip()
                return f"{name}: {text}" if name and name not in text else text
        for key in ("data", "error", "cause"):
            text = _cli_value_to_text(value.get(key)).strip()
            if text:
                name = _cli_value_to_text(value.get("name")).strip()
                return f"{name}: {text}" if name and name not in text else text
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


class BaseCLIProvider(AIProvider):
    """
    Claude Code, Codex ve agy CLI'larını UnityAI MCP Server üzerinden çalıştırır.
    """

    # Race condition önlemi: settings.json yazma + subprocess spawn atomik olmalı
    _AGY_LOCK = asyncio.Lock()

    # Cursor/Copilot/OpenCode gibi one-shot CLI'larda uzun MCP çağrıları dakikalarca
    # stdout üretmeyebilir. Yalnız GERÇEK hareketsizliği sınırla; toplam çalışma
    # süresini ayrıca geniş bir güvenlik tavanıyla koru.
    _CLI_POLL_SECONDS = 15.0
    _CLI_IDLE_TIMEOUT_SECONDS = 15 * 60
    _CLI_MAX_RUNTIME_SECONDS = 60 * 60
    # asyncio subprocess StreamReader varsayılanı 64 KiB'dir. JSONL kullanan
    # CLI'lar MCP ekran görüntüsü gibi binary/base64 sonuçlarını tek event satırında
    # döndürebilir (Unity screenshot canlı örneği: ~214 KiB). Tüm CLI stdout/stderr
    # akışlarına kontrollü, fakat gerçek MCP sonuçlarını taşıyabilecek ortak tavan ver.
    _CLI_STREAM_LIMIT_BYTES = 32 * 1024 * 1024

    # model ID → agy settings.json "model" değeri (DISPLAY-NAME formatı).
    # ⚠️ `--model` FLAG'İ KULLANILMAZ — canlı doğrulandı (2026-07-24): agy komut
    # satırında --model görünce "kullanıcı bu flag'i soruyor" sanıp built-in
    # antigravity-guide skill'ine düşüyor (derail) → kullanıcının gerçek mesajını
    # yanıtlamıyor, kendinden/CLI flag'lerinden bahsediyor. Aynı derail --mode,
    # --print-timeout, --dangerously-skip-permissions'ta da var. Model seçimi bu
    # yüzden SADECE settings.json "model" key'iyle yapılır (bkz. _set_agy_model);
    # display-name settings.json'da hem modeli seçer hem kimliğini belirler.
    # 1.1.5'te OLMAYAN modeller (3.5-flash-lite, 3-flash, 3.1-flash-lite, 2.5-*) çıkarıldı.
    _AGY_MODEL_MAP = {
        # Gemini (effort = display-name son-eki (High/Medium/Low))
        "gemini-3.6-flash":              "Gemini 3.6 Flash (High)",
        "gemini-3.6-flash-medium":       "Gemini 3.6 Flash (Medium)",
        "gemini-3.6-flash-low":          "Gemini 3.6 Flash (Low)",
        "gemini-3.5-flash":              "Gemini 3.5 Flash (High)",
        "gemini-3.5-flash-medium":       "Gemini 3.5 Flash (Medium)",
        "gemini-3.5-flash-low":          "Gemini 3.5 Flash (Low)",
        "gemini-3.1-pro-preview":        "Gemini 3.1 Pro (High)",
        "gemini-3.1-pro-low":            "Gemini 3.1 Pro (Low)",
        # Antigravity CLI üzerinden Claude ve GPT-OSS
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
        self._pending_agy_model = "Gemini 3.6 Flash (High)"
        self._active_process = None
        self._cancel_requested = False

    async def cancel_active_process(self) -> bool:
        """Bu provider'ın çalışan ephemeral CLI sürecini gerçekten sonlandırır."""
        self._cancel_requested = True
        process = self._active_process
        if process is None or process.returncode is not None:
            return False
        logger.info(
            f"[CLIProvider:{self.binary_name}] kullanıcı durdurdu — PID={process.pid} sonlandırılıyor"
        )
        try:
            process.kill()
        except ProcessLookupError:
            return False
        try:
            await asyncio.wait_for(process.wait(), timeout=3.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            pass
        return True

    @classmethod
    def _cli_timeout_reason(cls, *, elapsed: float, idle: float) -> Optional[str]:
        """Aktif bir CLI sürecinin durdurulma nedenini döndürür.

        ``elapsed`` tek başına 5 dakikayı geçti diye süreç öldürülmez; stdout veya
        stderr aktivitesi varsa ``idle`` düşük kalır ve uzun MCP turu devam eder.
        """
        if elapsed > cls._CLI_MAX_RUNTIME_SECONDS:
            return "max_runtime"
        if idle > cls._CLI_IDLE_TIMEOUT_SECONDS:
            return "idle_timeout"
        return None

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
        resolved = shutil.which(cmd[0])
        if not resolved and sys.platform != "win32":
            from .oneshot_cli import resolve_posix_cli
            resolved = resolve_posix_cli(cmd[0])
        resolved = resolved or cmd[0]
        rest = list(cmd[1:])
        if sys.platform == "win32" and resolved.lower().endswith((".cmd", ".bat")):
            return ["cmd", "/c", resolved, *rest]
        return [resolved, *rest]

    @staticmethod
    def _cli_installed(name: str) -> bool:
        """CLI binary'si PATH'te (Windows'ta PATHEXT ile .cmd/.exe dahil) bulunabiliyor mu?"""
        if os.path.isabs(name):
            return os.path.exists(name)
        if shutil.which(name) is not None:
            return True
        if sys.platform != "win32":
            from .oneshot_cli import resolve_posix_cli
            return resolve_posix_cli(name) is not None
        return False

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
        # LOCAL_APP_TOKEN buraya BİLEREK yazılmıyor: bu dosya modelin
        # okuyabildiği yerde duruyor ve token backend'de tek yetki kanıtı.
        # Çocuk süreç sırrı 0600 dosyadan okuyor (bkz. local_token_file).
        unityai_env = {"UNITYAI_URL": backend_url}

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
        # Sır artık URL'de DEĞİL, `headers` alanında. Bu dosyayı claude ve kimi
        # okuyor; ikisinin de `headers` alanını gönderdiği 2026-07-27'de canlı
        # ölçüldü. Sır yoksa mcp_url() None döner → kayıt hiç yazılmaz.
        unity_mcp_url = unity_mcp_manager.mcp_url()
        if unity_mcp_url:
            config["mcpServers"]["unityMCP"] = {
                "type": "http",
                "url": unity_mcp_url,
                "headers": unity_mcp_manager.api_headers(),
            }
            logger.info("[CLIProvider] Unity MCP aktif, .mcp.json'a eklendi.")

        config_path = os.path.join(workspace, ".mcp.json")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        # Dosyayı yazan nokta girdisini de yazar. Bu dosya `headers` içinde
        # unityMCP `X-API-Key`'ini düz metin taşıyor ve kullanıcının deposunda
        # duruyor (bkz. workspace_config).
        from .workspace_config import ensure_gitignored
        ensure_gitignored(workspace, [".mcp.json"])

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
        process = None
        stderr_task = None
        _pty_master_fd = None
        self._cancel_requested = False
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
            # İZİN LİSTESİ — `{**os.environ}` DEĞİL. Eskiden ebeveynin ortamının
            # tamamı geçiyordu ve ölçüldü (2026-07-28): seçilen sağlayıcı hangisi
            # olursa olsun çocuk BÜTÜN vendor anahtarlarını, veritabanı şifreleme
            # anahtarını ve backend bearer'ını görüyordu. Aile, kullanıcının
            # seçtiği modele göre belirleniyor: Claude kendi anahtarını alır,
            # Cursor almaz (bkz. _PROVIDER_ENV_ALLOWLIST).
            _env = build_spawn_env(
                family=env_family(self.binary_name),
                overrides={"NO_COLOR": "1", "TERM": "xterm-256color",
                           "COLUMNS": "220", "LINES": "50"},
            )

            # CLI binary bu PC'de kurulu mu? Değilse korkunç traceback yerine temiz uyarı ver.
            if not self._cli_installed(cmd[0]):
                _labels = {"agy": "Antigravity (agy)", "claude": "Claude Code", "codex": "Codex",
                           "kimi": "Kimi Code (kimi)",
                           "cursor-agent-not-found": "Cursor CLI (agent)",
                           "copilot-not-found": "GitHub Copilot CLI",
                           "opencode-not-found": "OpenCode"}
                _label = _labels.get(os.path.basename(cmd[0]).lower(), cmd[0])
                logger.warning(f"[CLIProvider:{self.binary_name}] CLI bulunamadı (PATH'te yok): {cmd[0]}")
                yield {"type": "error", "content": f"⚠️ {_label} CLI bu bilgisayarda kurulu değil (PATH'te bulunamadı). Lütfen kurun veya farklı bir model seçin."}
                return

            # cmd[0]'i tam yola çöz + Windows .cmd/.bat ise cmd.exe ile sar (WinError 2 fix).
            spawn_cmd = self._resolve_exec(cmd)

            logger.info(f"[CLIProvider:{self.binary_name}][CMD] {' '.join(cmd)}")
            logger.info(f"[CLIProvider:{self.binary_name}][CWD] {workspace}")
            logger.info(f"[CLIProvider:{self.binary_name}][ENV] LOCAL_APP_TOKEN={'set' if _env.get('LOCAL_APP_TOKEN') else 'unset'} UNITYAI_URL={_env.get('UNITYAI_URL', _env.get('ANTIGRAVITY_URL', 'unset'))}")

            if _is_agy:
                async with BaseCLIProvider._AGY_LOCK:
                    self._set_agy_model(self._pending_agy_model, workspace)
                    # agy --print ARTIK MCP yükler (2026-07-14, agy 1.1.2 canlı doğrulandı):
                    # config göç-sonrası yola (~/.gemini/config/mcp_config.json) yazıldığı için
                    # agy unityMCP + meshy + unityai tool'larını görüyor (bkz. _register_mcp 1b).
                    # Yine de DOSYA YAZMA/SİLME/SHELL için agy'nin kendi write araçları
                    # (write_to_file vb.) _AGY_DISABLED_TOOLS ile kapalı → agy bunları 'unityai'
                    # CLI'ı ile run_command üzerinden yapmak zorunda → onay kartı çıkar.
                    unityai_cli = self._launcher_path("unityai")
                    self._ensure_exec(unityai_cli)
                    mcp_hint = (
                        "IMPORTANT: You MUST respond in Turkish (Türkçe) at all times.\n\n"
                        "AVAILABLE MCP TOOLS — call these DIRECTLY when the task needs them:\n"
                        "- unityMCP: Unity editor operations (manage_gameobject, manage_scene,\n"
                        "  manage_fbx, manage_animation, manage_material, refresh_unity, read_console,\n"
                        "  run_tests, find_gameobjects, etc.). Use directly for Unity queries/actions.\n"
                        "- meshy: 3D asset generation (meshy_text_to_3d, meshy_image_to_3d, meshy_rig,\n"
                        "  meshy_animate, meshy_retexture, meshy_check_balance, etc.). Use directly.\n"
                        "  Meshy calls cost credits — state the cost and get user confirmation first.\n"
                        "Do NOT route unityMCP/meshy through the unityai CLI — call them as MCP tools.\n\n"
                        "RESUMING A LONG TASK: You remember previous turns. If earlier you started a\n"
                        "long async job (e.g. meshy_text_to_3d returns a task id and generation takes\n"
                        "minutes) and it looks unfinished/interrupted, do NOT restart it — call the\n"
                        "status tool (meshy_get_task_status with the task id from your history) and\n"
                        "continue from where you left off (download / refine / place in scene).\n\n"
                        "EFFICIENCY — answer directly, do NOT flail:\n"
                        "- Respond to the user's actual request. Do NOT go on filesystem expeditions.\n"
                        "- Do NOT call list_dir / grep_search / view_file / invoke_subagent / schedule\n"
                        "  unless the task genuinely requires it. No self-scheduling, no timers, no\n"
                        "  probing the .system_generated / brain / transcript folders. Just do the task.\n\n"
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
                        "REPLY STYLE — match the reply length to the task:\n"
                        "- For file WRITE / DELETE / shell actions: reply with ONE short Turkish\n"
                        "  sentence stating what you did (e.g. 'TestScripts.cs oluşturuldu.'). NEVER\n"
                        "  paste the file's full content/code block — the IDE approval card already\n"
                        "  shows the code and diff. NEVER explain approval mechanics ('onayınızı\n"
                        "  bekliyor', 'onay verdikten sonra', 'komutu çalıştırdım'). Don't repeat.\n"
                        "- For QUESTIONS, reading/analysis, or reports (e.g. 'read the GDD and tell me\n"
                        "  the rules', 'check MCP access', 'what does X do'): give a COMPLETE, substantive\n"
                        "  Turkish answer — actually report the findings, rules, values, or console output\n"
                        "  you gathered. Do NOT collapse it into a passive one-liner like 'öğrenildi',\n"
                        "  'incelendi' or 'test edildi'. Be genuinely informative, not terse.\n"
                        "- LANGUAGE: ALWAYS reply in the language the user writes in (Turkish user →\n"
                        "  Turkish reply), including resumed conversations. Never drift to English.\n\n"
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
                        limit=self._CLI_STREAM_LIMIT_BYTES,
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
                    limit=self._CLI_STREAM_LIMIT_BYTES,
                )
                if _stdin_prompt is not None:
                    process.stdin.write(_stdin_prompt.encode("utf-8"))
                    await process.stdin.drain()
                    process.stdin.close()
            self._active_process = process
            _stdout_reader = process.stdout
            logger.info(f"[CLIProvider:{self.binary_name}] PID={process.pid} başlatıldı")

            _loop = asyncio.get_event_loop()
            _start = _loop.time()
            _last_activity = _start
            _termination_reason = None
            stderr_buffer = []

            async def _drain_stderr():
                nonlocal _last_activity
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    _last_activity = _loop.time()
                    decoded = line.decode("utf-8", errors="ignore").rstrip()
                    stderr_buffer.append(decoded)
                    logger.warning(f"[CLIProvider:{self.binary_name}][STDERR] {decoded}")

            stderr_task = asyncio.create_task(_drain_stderr())

            full_text = ""
            line_count = 0
            # Yeni CLI'lar (cursor/copilot/opencode) için parser durumu:
            _sess_meta_sent = False          # resume anahtarı bir kez yield edilir
            _copilot_streamed = set()        # delta'sı akıtılan messageId'ler (dedup)
            _is_cursor = self.binary_name.startswith("cursor-")

            # agy CANLI-İZLEME: --print modunda uzun meshy işlerinde stdout SESSİZ kalır ama
            # agy conversation .db'ye step (meshy status-poll'leri) yazmaya devam eder.
            # Liveness'i STDOUT yerine DB BÜYÜMESİNDEN ölç → sahte timeout yok + yeni tool
            # aktivitesini chate akıt (Fable gibi görünürlük). Yalnız agy için.
            import time as _time
            if _is_agy:
                from .agy_session import get_max_step_idx, newest_conv_uuid, poll_agy_activity
                _agy_uuid = getattr(self, "_resume_uuid", None)
                _agy_last_idx = get_max_step_idx(_agy_uuid) if _agy_uuid else -1
                _agy_last_activity = _start
                _agy_wall_start = _time.time()
                _AGY_IDLE_LIMIT = 300     # 5dk HİÇ db büyümesi yok → gerçek hang
                _AGY_MAX_TOTAL = 1800     # 30dk mutlak tavan (Fable ~20dk meshy'yi kapsar)

            while True:
                try:
                    line = await asyncio.wait_for(
                        _stdout_reader.readline(),
                        timeout=self._CLI_POLL_SECONDS,
                    )
                except asyncio.TimeoutError:
                    _now = _loop.time()
                    if process.returncode is not None:
                        logger.error(f"[CLIProvider:{self.binary_name}] Process bitti rc={process.returncode}")
                        break

                    if _is_agy:
                        # agy stdout SESSİZ olabilir ama DB'ye step yazıyorsa CANLI'dır.
                        # Aktif turun db'sini bul (resume-uuid; yoksa ilk turda beliren yeni db),
                        # yeni tool aktivitesini oku → chate akıt + idle sayacını SIFIRLA.
                        if _agy_uuid is None:
                            _agy_uuid = newest_conv_uuid(min_mtime=_agy_wall_start - 2.0)
                            if _agy_uuid:
                                _agy_last_idx = -1  # yeni db → bu turun tüm aktivitesini akıt
                        if _agy_uuid:
                            _acts, _agy_last_idx = poll_agy_activity(_agy_uuid, _agy_last_idx)
                            if _acts:
                                _agy_last_activity = _now  # db büyüdü → agy canlı
                                for _a in _acts:
                                    yield {"type": "thinking", "text": f"⚙ {_a}"}
                        _idle = _now - _agy_last_activity
                        if _idle > _AGY_IDLE_LIMIT or (_now - _start) > _AGY_MAX_TOTAL:
                            logger.error(
                                f"[CLIProvider:agy] hang (idle={_idle:.0f}s / toplam={_now-_start:.0f}s) — kill")
                            process.kill()
                            break
                        continue

                    # Diğer provider'lar (claude/codex/...): onay veya uzun MCP işi
                    # beklerken sessiz kalabilir. Toplam 300 saniyede öldürmek yerine
                    # son gerçek stdout/stderr aktivitesini esas al.
                    _idle = _now - _last_activity
                    _elapsed = _now - _start
                    logger.warning(
                        f"[CLIProvider:{self.binary_name}][WAIT] idle={_idle:.0f}s "
                        f"toplam={_elapsed:.0f}s (onay/işlem bekleniyor olabilir) | "
                        f"pid={process.pid}")
                    _termination_reason = self._cli_timeout_reason(
                        elapsed=_elapsed,
                        idle=_idle,
                    )
                    if _termination_reason:
                        logger.error(
                            f"[CLIProvider:{self.binary_name}] "
                            f"{_termination_reason} (idle={_idle:.0f}s / "
                            f"toplam={_elapsed:.0f}s) — kill")
                        process.kill()
                        break
                    continue

                if not line:
                    logger.info(f"[CLIProvider:{self.binary_name}] stdout EOF (toplam {line_count} satır)")
                    break

                _last_activity = _loop.time()
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
                    self.binary_name.startswith("gpt-") or
                    self.binary_name.startswith("cursor-") or
                    self.binary_name.startswith("copilot-") or
                    self.binary_name.startswith("opencode:") or
                    self.binary_name.startswith("kimi-")
                )
                if _is_json_provider:
                    try:
                        ev = _json.loads(raw)
                        ev_type = ev.get("type", "")

                        # ── Kimi Code stream-json: OpenAI-mesaj şekilli NDJSON (role tabanlı,
                        #    "type" YOK). Diğer parser dallarına düşmeden burada ele alınır. ──
                        #    NOT (canlı doğrulanmadı): content'in delta mı yoksa kümülatif mi
                        #    geldiği bir Kimi hesabıyla doğrulanmalı; delta varsayıyoruz +
                        #    tam-tekrar koruması var.
                        if self.binary_name.startswith("kimi-"):
                            if not _sess_meta_sent:
                                _ksid = (ev.get("session_id") or ev.get("sessionId")
                                         or (ev.get("data") or {}).get("session_id"))
                                if _ksid:
                                    _sess_meta_sent = True
                                    yield {"type": "session_meta", "session_id": str(_ksid)}
                            _krole = ev.get("role", "")
                            if _krole == "assistant":
                                _kc = ev.get("content", "")
                                if isinstance(_kc, str) and _kc and _kc != full_text:
                                    full_text += _kc
                                    yield {"type": "delta", "text": _kc}
                                for _ktc in (ev.get("tool_calls") or []):
                                    if not isinstance(_ktc, dict):
                                        continue
                                    _kfn = _ktc.get("function") or {}
                                    _ktn = _kfn.get("name", "")
                                    if not _ktn:
                                        continue
                                    _khint = f"🔧 `{_ktn}`"
                                    try:
                                        _kargs = _json.loads(_kfn.get("arguments") or "{}")
                                        if isinstance(_kargs, dict):
                                            if "path" in _kargs:
                                                _khint += f" → `{_kargs['path']}`"
                                            elif "command" in _kargs:
                                                _khint += f" → `{str(_kargs['command'])[:80]}`"
                                            elif "action" in _kargs:
                                                _khint += f" → `{_kargs['action']}`"
                                    except Exception:
                                        pass
                                    yield {"type": "thinking", "text": _khint}
                            elif _krole == "tool":
                                _kres = str(ev.get("content", ""))[:200].strip()
                                if _kres:
                                    yield {"type": "thinking", "text": f"↩ {_kres}"}
                            continue

                        # ── Resume anahtarı yakalama (cursor: session_id her event'te;
                        #    opencode: sessionID her event'te; copilot: result.sessionId) ──
                        if not _sess_meta_sent:
                            _sid = ev.get("session_id") or ev.get("sessionID") or ev.get("sessionId")
                            if _sid:
                                _sess_meta_sent = True
                                yield {"type": "session_meta", "session_id": str(_sid)}

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
                                    # Cursor --stream-partial-output: parçalı delta'ların ardından
                                    # AYNI metnin tam halini tekrar yollar → biriken metinle birebir
                                    # aynıysa mükerrer basma.
                                    if _is_cursor and t and t == full_text:
                                        continue
                                    if t:
                                        full_text += t
                                        yield {"type": "delta", "text": t}
                        elif ev_type == "tool":
                            content = ev.get("content", "")
                            result_text = content[:200] if isinstance(content, str) else ""
                            if result_text:
                                yield {"type": "thinking", "text": f"↩ {result_text}"}
                        elif ev_type == "result":
                            result = _cli_value_to_text(ev.get("result", ""))
                            if result and not full_text:
                                full_text = result

                        # ── Cursor stream-json: thinking ayrı top-level event ──
                        elif ev_type == "thinking":
                            if ev.get("subtype") == "delta":
                                t = ev.get("text", "")
                                if t:
                                    yield {"type": "thinking", "text": t}

                        # ── Copilot JSONL (assistant.* / tool.*) ────────────
                        elif ev_type == "assistant.message_delta":
                            _d = ev.get("data", {})
                            t = _d.get("deltaContent", "")
                            if t:
                                _copilot_streamed.add(_d.get("messageId", ""))
                                full_text += t
                                yield {"type": "delta", "text": t}
                        elif ev_type == "assistant.reasoning_delta":
                            t = ev.get("data", {}).get("deltaContent", "")
                            if t:
                                yield {"type": "thinking", "text": t}
                        elif ev_type == "assistant.message":
                            _d = ev.get("data", {})
                            t = _d.get("content", "")
                            # delta'ları zaten akıttıysak tam metni tekrar basma
                            if t and _d.get("messageId", "") not in _copilot_streamed:
                                full_text += t
                                yield {"type": "delta", "text": t}
                            for _tr in (_d.get("toolRequests") or []):
                                _tn = _tr.get("name", _tr.get("toolName", "")) if isinstance(_tr, dict) else ""
                                if _tn:
                                    yield {"type": "thinking", "text": f"🔧 `{_tn}`"}
                        elif ev_type.startswith("tool."):
                            _d = ev.get("data", {})
                            _tn = _d.get("toolName", _d.get("name", ""))
                            if ev_type.endswith(("started", "requested")) and _tn:
                                yield {"type": "thinking", "text": f"🔧 `{_tn}`"}
                            elif ev_type.endswith(("completed", "finished")):
                                _out = str(_d.get("output", _d.get("result", "")))[:200]
                                if _out:
                                    yield {"type": "thinking", "text": f"↩ {_out}"}

                        # ── OpenCode --format json (text / tool_use / step_*) ──
                        elif ev_type == "text":
                            t = (ev.get("part") or {}).get("text", "")
                            if t:
                                full_text += t
                                yield {"type": "delta", "text": t}
                        elif ev_type == "tool_use":
                            _part = ev.get("part") or {}
                            _tn = _part.get("tool", "")
                            _st = _part.get("state") or {}
                            hint = f"🔧 `{_tn}`" if _tn else ""
                            _title = _st.get("title", "")
                            if _title:
                                hint += f" → `{_title[:120]}`"
                            if hint:
                                yield {"type": "thinking", "text": hint}
                            _out = str(_st.get("output", ""))[:200].strip()
                            if _out:
                                yield {"type": "thinking", "text": f"↩ {_out}"}
                        elif ev_type in ("step_start", "step_finish"):
                            pass  # akış iskeleti; step_finish token sayılarını taşır (gerekirse logla)

                        # ── Yapılandırılmış CLI hatası ─────────────────────
                        elif ev_type == "error":
                            _err = _cli_value_to_text(
                                ev.get("content", ev.get("text", ev.get("error", "")))
                            ).strip()
                            if _err:
                                _event = {
                                    "type": "error",
                                    "content": f"❌ CLI hatası: {_err}",
                                }
                                # OpenCode top-level error verdiyse aynı disk session'ını
                                # tekrar resume etmek çoğunlukla aynı hatayı döndürür.
                                # Ancak provider yoğunluğu/rate-limit kaynaklı genel
                                # upstream hatası session bozulması değildir; bağlamı koru.
                                if self.binary_name.startswith("opencode:"):
                                    if re.search(
                                        r"upstream request failed|service unavailable|"
                                        r"temporarily unavailable",
                                        _err,
                                        re.I,
                                    ):
                                        _event.update({
                                            "reason": "provider_upstream",
                                            "retryable": True,
                                        })
                                    else:
                                        _event.update({
                                            "reset_session": True,
                                            "reason": "structured_error",
                                        })
                                yield _event

                        # ── agy / Gemini CLI JSONL (hot-swap) ───────────────
                        elif ev_type == "content":
                            t = _cli_value_to_text(
                                ev.get("content", ev.get("text", ""))
                            )
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
                _pty_master_fd = None

            logger.info(
                f"[CLIProvider:{self.binary_name}][DONE] "
                f"rc={process.returncode} | lines={line_count} | chars={len(full_text)} | "
                f"stderr={len(stderr_buffer)} | süre={asyncio.get_event_loop().time()-_start:.1f}s"
            )

            if self._cancel_requested:
                yield {
                    "type": "error",
                    "content": "🛑 İşlem kullanıcı tarafından durduruldu.",
                    "reset_session": True,
                    "reason": "user_stop",
                }
            elif _termination_reason:
                if _termination_reason == "idle_timeout":
                    _msg = (
                        "⏳ CLI uzun süre hiçbir çıktı veya ilerleme üretmediği için "
                        f"{int(self._CLI_IDLE_TIMEOUT_SECONDS // 60)} dakika sonra durduruldu. "
                        "Sonraki mesaj temiz bir oturumda sohbet geçmişiyle devam edecek."
                    )
                else:
                    _msg = (
                        "⏳ CLI güvenlik amacıyla "
                        f"{int(self._CLI_MAX_RUNTIME_SECONDS // 60)} dakikalık toplam çalışma "
                        "tavanında durduruldu. Sonraki mesaj temiz bir oturumda devam edecek."
                    )
                yield {
                    "type": "error",
                    "content": _msg,
                    "reset_session": True,
                    "reason": _termination_reason,
                }
            elif process.returncode not in (0, 1, None):
                stderr_full = "\n".join(stderr_buffer)
                logger.error(f"[CLIProvider:{self.binary_name}][FAILED] rc={process.returncode}\nSTDERR:\n{stderr_full}")
                yield {
                    "type": "error",
                    "content": f"❌ CLI hata (rc={process.returncode}): {stderr_full[:500] or '(boş)'}",
                    "reset_session": True,
                    "reason": "process_exit",
                }
            elif line_count == 0 and not _is_agy:
                # NOT: agy --print stdout'u non-TTY'de SESSİZCE kaybolur (repo bug #76) —
                # bu agy için NORMALDİR (yanıt conversation .db'sinden okunur, bkz.
                # agent_runner._run_agy_session). Bu yüzden agy'de boş stdout'u hata SAYMA;
                # diğer CLI'larda (claude/codex) boş stdout gerçek başarısızlıktır.
                stderr_full = "\n".join(stderr_buffer)
                logger.error(f"[CLIProvider:{self.binary_name}][NO_OUTPUT] Stdout boş!\nSTDERR:\n{stderr_full}")
                yield {"type": "error", "content": f"⚠️ Çıktı yok. Hata: {stderr_full[:500]}"}
            elif not full_text.strip() and self.binary_name.startswith(("cursor-", "copilot-", "opencode:")):
                # Yeni CLI'lar rc=1 ile ölürken stdout'a yalnız init event'leri basmış
                # olabilir (örn. copilot "Model ... is not available" hatası stderr'de,
                # rc=1) → yukarıdaki iki dal da yakalamaz, kullanıcı boş kart görürdü.
                _err_lines = [l for l in stderr_buffer if "error" in l.lower()] or stderr_buffer
                if _err_lines:
                    _msg = "\n".join(_err_lines)[:400]
                    logger.error(f"[CLIProvider:{self.binary_name}][EMPTY_TEXT] {_msg}")
                    _hint = ""
                    if "not available" in _msg.lower() and self.binary_name.startswith("copilot-"):
                        _hint = "\n💡 Bu model Copilot planında kullanılamıyor olabilir — 'Copilot Auto' modelini deneyin."
                    yield {"type": "error", "content": f"⚠️ CLI yanıt üretmedi: {_msg}{_hint}"}

            yield {"type": "final", "text": self._clean_response(full_text)}

        except asyncio.CancelledError:
            # İstemci SSE bağlantısını AbortController ile kapattığında generator
            # iptal edilir. Alt CLI arkada kalmamalı; cleanup finally'de yapılır.
            raise
        except Exception as e:
            logger.exception(f"[CLIProvider:{self.binary_name}] Exception in analyze_code")
            yield {"type": "error", "content": f"❌ CLI Bridge Hatası: {str(e)}"}
        finally:
            if process is not None and process.returncode is None:
                try:
                    process.kill()
                    await asyncio.wait_for(process.wait(), timeout=3.0)
                except (ProcessLookupError, asyncio.TimeoutError):
                    pass
            if stderr_task is not None and not stderr_task.done():
                stderr_task.cancel()
                await asyncio.gather(stderr_task, return_exceptions=True)
            if _pty_master_fd is not None:
                try:
                    os.close(_pty_master_fd)
                except OSError:
                    pass
            if self._active_process is process:
                self._active_process = None

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
