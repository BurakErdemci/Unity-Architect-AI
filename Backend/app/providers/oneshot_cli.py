"""Cursor / Copilot / OpenCode — one-shot CLI ortak altyapısı.

Bu üç CLI, Claude (SDK session) ve Codex (app-server) gibi CANLI bir süreç
tutmaz; her tur ephemeral bir subprocess'tir. Bağlam sürekliliği CLI'ların
KENDİ resmi resume mekanizmasıyla sağlanır (agy'nin aksine üçünde de resmi
ve çalışır durumda — 2026-07-13 canlı doğrulandı):

  • cursor  : `agent create-chat` ile chatId baştan üretilir; her tur
              `--resume <chatId>`. (stream-json çıktı, Claude formatına çok yakın)
  • copilot : İLK turda --session-id=<bizim ürettiğimiz uuid>, sonraki
              turlarda --resume=<uuid>. (JSONL çıktı)
  • opencode: İlk turun JSON event'lerindeki sessionID yakalanır; sonraki
              turlarda `-s <sessionID>`. (JSON event çıktı)

Windows'ta npm/ps1 shim'leri cmd.exe sarmalaması gerektirir ve cmd.exe çok
satırlı argv'yi bozar (claude/codex'te stdin fallback ile çözmüştük). Burada
shim'i tamamen ATLAYIP gerçek entry point'i doğrudan spawn ederiz:
  • cursor  : <LOCALAPPDATA>/cursor-agent/versions/<en yeni>/node.exe + index.js
  • copilot : node + <APPDATA>/npm/node_modules/@github/copilot/npm-loader.js
  • opencode: <APPDATA>/npm/node_modules/opencode-ai/bin/opencode.exe (native!)
macOS/Linux'ta bunlar POSIX binary/script olduğundan shutil.which yeterli.
"""
import os
import sys
import glob
import shutil
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CLI_KEYS = ("cursor", "copilot", "opencode")


# ─────────────────────────────────────────────────────────────────
# Sohbet başına resume durumu (agy_session ile aynı kalıp)
# ─────────────────────────────────────────────────────────────────
class OneShotSession:
    def __init__(self, cli: str, conversation_id: int):
        self.cli = cli
        self.conversation_id = conversation_id
        self.session_id: Optional[str] = None  # CLI'ın resume anahtarı
        self.ctx_injected: bool = False        # transcript ilk turda enjekte edildi mi
        self.auto_approve: bool = False


_SESSIONS: Dict[Tuple[str, int], OneShotSession] = {}


def get_session(cli: str, conversation_id: int) -> OneShotSession:
    key = (cli, conversation_id)
    s = _SESSIONS.get(key)
    if s is None:
        s = OneShotSession(cli, conversation_id)
        _SESSIONS[key] = s
    return s


async def close_session(cli: str, conversation_id: int) -> None:
    _SESSIONS.pop((cli, conversation_id), None)


async def close_all_sessions() -> None:
    _SESSIONS.clear()


# ─────────────────────────────────────────────────────────────────
# Binary çözümleme (shim'siz doğrudan spawn)
# ─────────────────────────────────────────────────────────────────
def _npm_global_root() -> str:
    """Windows'ta npm global kök klasörü (APPDATA/npm)."""
    return os.path.join(os.environ.get("APPDATA", ""), "npm")


def _latest_cursor_version_dir() -> Optional[str]:
    """<LOCALAPPDATA>/cursor-agent/versions/ altındaki en yeni sürüm klasörü.
    Klasör adı YYYY.MM.DD-hash formatında → ada göre sıralama kronolojiktir."""
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "cursor-agent", "versions")
    try:
        dirs = [d for d in glob.glob(os.path.join(base, "*")) if os.path.isdir(d)]
    except Exception:
        return None
    if not dirs:
        return None
    return max(dirs, key=os.path.basename)


def resolve_cursor_cmd() -> Optional[List[str]]:
    """Cursor agent'ı çalıştıracak komut listesi (arg'lar hariç) veya None."""
    if sys.platform == "win32":
        vdir = _latest_cursor_version_dir()
        if vdir:
            node = os.path.join(vdir, "node.exe")
            entry = os.path.join(vdir, "index.js")
            if os.path.exists(node) and os.path.exists(entry):
                return [node, entry]
    # POSIX (mac/linux) veya fallback: PATH'teki agent
    for name in ("cursor-agent", "agent"):
        p = shutil.which(name)
        if p and not p.lower().endswith(".ps1"):
            return [p]
    return None


def resolve_copilot_cmd() -> Optional[List[str]]:
    """GitHub Copilot CLI komutu veya None."""
    if sys.platform == "win32":
        loader = os.path.join(_npm_global_root(), "node_modules", "@github", "copilot", "npm-loader.js")
        node = shutil.which("node")
        if node and os.path.exists(loader):
            return [node, loader]
    p = shutil.which("copilot")
    if p and not p.lower().endswith(".ps1"):
        return [p]
    return None


def resolve_opencode_cmd() -> Optional[List[str]]:
    """OpenCode komutu veya None. Windows'ta npm paketi NATIVE exe taşır."""
    if sys.platform == "win32":
        exe = os.path.join(_npm_global_root(), "node_modules", "opencode-ai", "bin", "opencode.exe")
        if os.path.exists(exe):
            return [exe]
    p = shutil.which("opencode")
    if p and not p.lower().endswith(".ps1"):
        return [p]
    return None


_RESOLVERS = {
    "cursor": resolve_cursor_cmd,
    "copilot": resolve_copilot_cmd,
    "opencode": resolve_opencode_cmd,
}


def resolve_cli_cmd(cli: str) -> Optional[List[str]]:
    fn = _RESOLVERS.get(cli)
    return fn() if fn else None


def cli_installed(cli: str) -> bool:
    return resolve_cli_cmd(cli) is not None


# ─────────────────────────────────────────────────────────────────
# Model kimliği eşlemesi
#   Bizim ID                     → CLI --model değeri
#   cursor-composer-2.5          → composer-2.5
#   copilot-claude-sonnet-5      → claude-sonnet-5
#   opencode:opencode/big-pickle → opencode/big-pickle
# ─────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────
# Plan yetenekleri (öğrenilmiş): adlı modeller bu planda çalışıyor mu?
# Kaynaklar: (a) /cli-models içindeki tek seferlik ucuz probe,
#            (b) agent_runner'daki canlı Auto-fallback (turda plan hatası).
# Dosya: ~/.unity_architect_ai/cli_plan_caps.json
#   {"cursor": {"named_models": false, "checked_at": 1234567890}, ...}
# ─────────────────────────────────────────────────────────────────
_CAPS_PATH = os.path.expanduser(os.path.join("~", ".unity_architect_ai", "cli_plan_caps.json"))
_CAPS_TTL = 7 * 24 * 3600  # planlar değişebilir → haftada bir yeniden öğren


def get_plan_caps() -> dict:
    try:
        import json as _json
        with open(_CAPS_PATH, "r", encoding="utf-8") as f:
            return _json.load(f) or {}
    except Exception:
        return {}


def get_named_models_cap(cli: str) -> Optional[bool]:
    """True/False = biliniyor; None = bilinmiyor veya bayat (yeniden öğren)."""
    import time
    entry = get_plan_caps().get(cli)
    if not isinstance(entry, dict) or "named_models" not in entry:
        return None
    if time.time() - entry.get("checked_at", 0) > _CAPS_TTL:
        return None
    return bool(entry["named_models"])


def set_named_models_cap(cli: str, available: bool) -> None:
    try:
        import json as _json, time
        caps = get_plan_caps()
        caps[cli] = {"named_models": bool(available), "checked_at": time.time()}
        os.makedirs(os.path.dirname(_CAPS_PATH), exist_ok=True)
        with open(_CAPS_PATH, "w", encoding="utf-8") as f:
            _json.dump(caps, f, indent=2)
        logger.info(f"[plan-caps] {cli}.named_models={available}")
    except Exception as e:
        logger.warning(f"[plan-caps] yazılamadı: {e}")


# Plan kısıtı hata kalıbı (cursor/copilot canlı yakalandı)
import re as _re
PLAN_ERROR_RE = _re.compile(
    r"(named models unavailable|free plans can only use auto|"
    r"is not available|switch to auto|upgrade plans)", _re.I)

# Codex plan kısıtı (ikisi de canlı yakalandı 2026-07-13):
#   "The 'gpt-5.6-sol' model is not supported when using Codex with a ChatGPT account."
#   "unexpected status 404 Not Found: Model not found gpt-5.6-luna-free-1p-..."
CODEX_PLAN_ERROR_RE = _re.compile(
    r"(model is not supported when using codex|model not found)", _re.I)

# Kota/limit tükenmesi (tüm CLI'lar) → kullanıcıya dostane "hakkın doluyor/doldu" mesajı
QUOTA_ERROR_RE = _re.compile(
    r"(usage limit|rate limit|quota|too many requests|\b429\b|"
    r"out of (free )?credits|limit reached|hakk?ınız)", _re.I)


def clear_plan_caps() -> None:
    """Öğrenilmiş plan kısıtlarını sıfırlar (kullanıcı ↻ Yenile'ye basınca —
    plan yükseltmesi sonrası kilitli modellerin anında yeniden denenebilmesi için)."""
    try:
        if os.path.exists(_CAPS_PATH):
            os.remove(_CAPS_PATH)
            logger.info("[plan-caps] sıfırlandı (kullanıcı yenilemesi)")
    except Exception as e:
        logger.warning(f"[plan-caps] sıfırlanamadı: {e}")


def get_blocked_models(cli: str) -> set:
    """Bu planda çalışmadığı ÖĞRENİLMİŞ model id'leri (bizim id formatımızda)."""
    import time
    entry = get_plan_caps().get(cli) or {}
    if time.time() - entry.get("checked_at", 0) > _CAPS_TTL:
        return set()
    return set(entry.get("blocked_models") or [])


def add_blocked_model(cli: str, our_model_id: str) -> None:
    try:
        import json as _json, time
        caps = get_plan_caps()
        entry = caps.get(cli) or {}
        blocked = set(entry.get("blocked_models") or [])
        blocked.add(our_model_id)
        entry["blocked_models"] = sorted(blocked)
        entry["checked_at"] = time.time()
        caps[cli] = entry
        os.makedirs(os.path.dirname(_CAPS_PATH), exist_ok=True)
        with open(_CAPS_PATH, "w", encoding="utf-8") as f:
            _json.dump(caps, f, indent=2)
        logger.info(f"[plan-caps] {cli} blocked_models += {our_model_id}")
    except Exception as e:
        logger.warning(f"[plan-caps] blocked_models yazılamadı: {e}")


async def probe_named_models(cli: str, timeout: float = 30.0) -> Optional[bool]:
    """Ucuz adlı-model probe'u: planın adlı modelleri destekleyip desteklemediğini
    tek seferlik öğrenir. True/False döner; belirsizse None (karar verme)."""
    import asyncio
    import subprocess as sp
    base = resolve_cli_cmd(cli)
    if not base:
        return None
    if cli == "cursor":
        cmd = [*base, "-p", "--model", "gpt-5.2", "--output-format", "json", "--trust", "Reply: 1"]
    elif cli == "copilot":
        cmd = [*base, "--model", "claude-haiku-4.5", "-s", "--no-color", "--no-auto-update", "-p", "Reply: 1"]
    else:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            creationflags=getattr(sp, "CREATE_NO_WINDOW", 0))
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        blob = (out.decode("utf-8", "ignore") + "\n" + err.decode("utf-8", "ignore"))
        if PLAN_ERROR_RE.search(blob):
            set_named_models_cap(cli, False)
            return False
        if proc.returncode == 0:
            set_named_models_cap(cli, True)
            return True
        return None  # başka tür hata (auth vb.) → plan hakkında hüküm verme
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return None
    except Exception:
        return None


def split_model_id(our_id: str) -> Tuple[Optional[str], str]:
    """(cli_key, cli_model) döndürür; eşleşme yoksa (None, our_id)."""
    if our_id.startswith("cursor-"):
        return "cursor", our_id[len("cursor-"):]
    if our_id.startswith("copilot-"):
        return "copilot", our_id[len("copilot-"):]
    if our_id.startswith("opencode:"):
        return "opencode", our_id.split(":", 1)[1]
    return None, our_id
