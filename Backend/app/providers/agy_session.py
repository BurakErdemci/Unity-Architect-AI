"""agy (Antigravity CLI) disk-resume session durumu + conversation-db okuyucu.

agy'nin Codex/Claude gibi CANLI bir programatik server'ı YOK (2026-06-26, agy 1.0.12
üzerinde canlı doğrulandı): ne ACP/app-server subcommand'ı, ne JSON-RPC/stdio modu,
ne de aboneliğle çalışan bir SDK var (google-antigravity SDK yalnızca GEMINI_API_KEY
ile çalışıyor → abonelik-auth kısıtımızı ihlal ediyor). Tek kalıcı-bağlam yolu:
agy'nin KENDİ disk-resume'u (--conversation=<UUID>).

Bu modül sohbet başına agy conversation UUID'sini ve son okunan adım index'ini tutar:
  • Tur 1'de --conversation VERİLMEZ → agy yeni bir UUID yaratır. UUID'i, tur sonrası
    ~/.gemini/antigravity-cli/conversations/ içinde BELİREN yeni .db dosyasının
    adından yakalarız (dosya adı = UUID). (--conversation=<önceden-ürettiğimiz-uuid>
    ÇALIŞMAZ: var olmayan ID sessizce yok sayılır.)
  • Sonraki turlarda --conversation=<UUID> beslenir → agy bağlamı diskten yükler,
    biz geçmişi prompt'a BASMAYIZ.

agy --print STDOUT'u non-TTY'de sessizce kaybolur (repo bug #76). Bu yüzden asistanın
YANIT METNİNİ conversations/<UUID>.db (SQLite) içinden okuruz: `steps` tablosunda
step_type==15 = asistan mesajı; metin step_payload protobuf blob'unun içinde.
"""
import os
import glob
import shutil
import sqlite3
import logging
from typing import Dict, Optional, Tuple, Set, List

logger = logging.getLogger(__name__)

_CONV_DIR = os.path.expanduser(os.path.join("~", ".gemini", "antigravity-cli", "conversations"))
_ASSISTANT_STEP_TYPE = 15  # canlı doğrulandı: steps.step_type==15 → asistan mesajı


class AgySession:
    """Sohbet başına agy disk-resume koordinasyon durumu (agy ephemeral process
    olduğu için canlı subprocess TUTULMAZ — gerçek 'session' agy'nin disk db'sidir)."""

    def __init__(self, conversation_id: int):
        self.conversation_id = conversation_id
        self.agy_uuid: Optional[str] = None   # agy'nin yarattığı conversation UUID (resume anahtarı)
        self.last_step_idx: int = -1          # db'den okunan son step idx (incremental)
        self.ctx_injected: bool = False       # proje bağlamı ilk turda enjekte edildi mi
        self.auto_approve: bool = False


_SESSIONS: Dict[int, AgySession] = {}


def get_session(conversation_id: int) -> AgySession:
    s = _SESSIONS.get(conversation_id)
    if s is None:
        s = AgySession(conversation_id)
        _SESSIONS[conversation_id] = s
    return s


async def close_session(conversation_id: int) -> None:
    _SESSIONS.pop(conversation_id, None)


async def close_all_sessions() -> None:
    _SESSIONS.clear()


# ── UUID yakalama (yeni .db dosya adı = UUID) ──────────────────────────────
def snapshot_db_names() -> Set[str]:
    try:
        return {os.path.basename(p) for p in glob.glob(os.path.join(_CONV_DIR, "*.db"))}
    except Exception:
        return set()


def detect_new_uuid(before: Set[str]) -> Optional[str]:
    """Tur sonrası BELİREN yeni .db dosyasından UUID döndürür. Birden fazla yeni
    dosya varsa en güncel mtime'lı seçilir (agy spawn'ı _AGY_LOCK ile serialize)."""
    try:
        after = glob.glob(os.path.join(_CONV_DIR, "*.db"))
    except Exception:
        return None
    new = [p for p in after if os.path.basename(p) not in before]
    if not new:
        return None
    newest = max(new, key=os.path.getmtime)
    name = os.path.basename(newest)
    return name[:-3] if name.lower().endswith(".db") else name


# ── protobuf wire ayrıştırıcı (asistan metni step_payload içinde) ───────────
def _read_varint(buf: bytes, i: int) -> Tuple[Optional[int], int]:
    shift = 0
    result = 0
    while i < len(buf):
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, i
        shift += 7
        if shift > 63:
            return None, i
    return None, i


def _parse_fields(buf: bytes) -> List[Tuple[int, int, object]]:
    """Top-level protobuf alanlarını (field_no, wire_type, value) olarak döndürür.
    value: wire 2 → bytes; wire 0 → int; wire 1/5 → ham bytes."""
    out: List[Tuple[int, int, object]] = []
    i = 0
    n = len(buf)
    while i < n:
        tag, i = _read_varint(buf, i)
        if tag is None:
            break
        wire = tag & 0x07
        fno = tag >> 3
        if wire == 0:          # varint
            val, i = _read_varint(buf, i)
            out.append((fno, wire, val))
        elif wire == 2:        # length-delimited (string/bytes/embedded msg)
            ln, i = _read_varint(buf, i)
            if ln is None or ln < 0 or i + ln > n:
                break
            out.append((fno, wire, buf[i:i + ln]))
            i += ln
        elif wire == 1:        # 64-bit
            out.append((fno, wire, buf[i:i + 8]))
            i += 8
        elif wire == 5:        # 32-bit
            out.append((fno, wire, buf[i:i + 4]))
            i += 4
        else:                  # bilinmeyen wire tipi → güvenli çıkış
            break
    return out


def _looks_like_text(s: str) -> bool:
    if not s:
        return False
    printable = sum(1 for c in s if c == "\n" or c == "\t" or 0x20 <= ord(c) <= 0x10FFFF and c.isprintable())
    return printable / len(s) >= 0.85


def _clean_text_field(val: object) -> str:
    """val'i (bytes) temiz metin olarak döndürür ('' = uygun değil).
    Yalnızca okunabilirlik kontrolü — '4242' gibi saf-rakam yanıtlar geçerlidir;
    sadece çıplak bot-/user- id'lerini savunma amaçlı eler."""
    if not isinstance(val, (bytes, bytearray)):
        return ""
    try:
        s = val.decode("utf-8").strip()
    except Exception:
        return ""
    if not s or not _looks_like_text(s):
        return ""
    if s.lower().startswith(("bot-", "user-")):
        return ""
    return s


def _extract_assistant_text(payload: bytes) -> str:
    """step_payload protobuf blob'undan asistanın YANIT METNİNİ çıkarır.

    Gözlenen yapı (canlı doğrulandı, agy 1.0.12):
      • Gerçek asistan mesajı: top-level field 20 → alt-alan 1 (kopya: 8) = metin.
      • Tool-çağrısı adımı (yine step_type==15!): field 20'de alt-alan 1/8 YOKTUR
        (yalnızca 6=bot-id, 7=tool payload, 12). Bu adımlardan METİN ÇIKARMAYIZ —
        yoksa 'list_dir'/'view_file' gibi araç adları sohbet metnine sızar.
    Bu yüzden YALNIZCA field 20 → alt-alan 1/8'i kullanırız; yoksa boş döneriz
    (recursive tarama YOK — araç adlarını/mcp_hint'i sızdırıyordu)."""
    if not payload:
        return ""
    for fno, wire, val in _parse_fields(payload):
        if fno == 20 and wire == 2 and isinstance(val, (bytes, bytearray)):
            sub = _parse_fields(val)
            for want in (1, 8):
                for sfno, swire, sval in sub:
                    if sfno == want and swire == 2:
                        txt = _clean_text_field(sval)
                        if txt:
                            return txt
            return ""  # field 20 var ama metin alt-alanı yok → tool-call/non-prose adım
    return ""          # field 20 yok → asistan prose değil


def read_new_response(uuid: str, last_idx: int) -> Tuple[str, int]:
    """conversations/<uuid>.db içinden idx>last_idx olan step_type==15 (asistan)
    adımlarının metnini birleştirir. (metin, yeni_last_idx) döner.
    Yeni adım yoksa ("", last_idx) döner."""
    if not uuid:
        return "", last_idx
    db_path = os.path.join(_CONV_DIR, f"{uuid}.db")
    if not os.path.exists(db_path):
        return "", last_idx

    # agy db'yi açık/locked tutabilir → güvenli okuma için kopyala
    tmp = db_path + ".uaiscan"
    src = tmp
    try:
        shutil.copy2(db_path, tmp)
    except Exception:
        src = db_path  # son çare: doğrudan readonly oku

    text_parts: List[str] = []
    new_idx = last_idx
    con = None
    try:
        con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        cur = con.cursor()
        rows = cur.execute(
            "SELECT idx, step_type, step_payload FROM steps WHERE idx > ? ORDER BY idx",
            (last_idx,),
        ).fetchall()
        for idx, step_type, payload in rows:
            if idx > new_idx:
                new_idx = idx
            if step_type != _ASSISTANT_STEP_TYPE or not payload:
                continue
            txt = _extract_assistant_text(payload if isinstance(payload, (bytes, bytearray)) else bytes(payload or b""))
            if txt:
                text_parts.append(txt)
    except Exception as e:
        logger.warning(f"[agy_session] conversation db okuma hatası ({uuid}): {e}")
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass
        if src == tmp:
            try:
                os.remove(tmp)
            except Exception:
                pass

    return "\n\n".join(text_parts).strip(), new_idx
