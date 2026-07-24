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
import json
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
        self.active_provider = None            # Durdur için çalışan subprocess sahibi


_SESSIONS: Dict[int, AgySession] = {}


def get_session(conversation_id: int) -> AgySession:
    s = _SESSIONS.get(conversation_id)
    if s is None:
        s = AgySession(conversation_id)
        _SESSIONS[conversation_id] = s
    return s


async def close_session(conversation_id: int) -> None:
    session = _SESSIONS.pop(conversation_id, None)
    provider = getattr(session, "active_provider", None) if session else None
    if provider is not None:
        await provider.cancel_active_process()


async def close_all_sessions() -> None:
    for conversation_id in list(_SESSIONS):
        await close_session(conversation_id)


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


# ── tool aktivite özeti (stdout boşsa "ne yaptı" göstermek için) ────────────
def _extract_tool_activity(payload: bytes) -> Optional[str]:
    """Bir step'ten (type 15 tool-aksiyonu veya 38 tool-sonucu) insan-okunur tool
    özetini çıkarır. Gözlenen yapı (agy 1.1.2): field 20 → alt-7 → alt-3 =
    {"toolAction":"...","toolSummary":"...","AbsolutePath":...} JSON. Yoksa None."""
    if not payload:
        return None
    try:
        for fno, wire, val in _parse_fields(payload):
            if fno != 20 or wire != 2 or not isinstance(val, (bytes, bytearray)):
                continue
            for sf, sw, sv in _parse_fields(val):
                if sf != 7 or sw != 2 or not isinstance(sv, (bytes, bytearray)):
                    continue
                for ssf, ssw, ssv in _parse_fields(sv):
                    if ssf != 3 or ssw != 2 or not isinstance(ssv, (bytes, bytearray)):
                        continue
                    try:
                        obj = json.loads(ssv.decode("utf-8", "replace"))
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        s = obj.get("toolSummary") or obj.get("toolAction")
                        if s and isinstance(s, str) and s.strip():
                            return s.strip()
    except Exception:
        return None
    return None


def newest_conv_uuid(min_mtime: float = 0.0) -> Optional[str]:
    """conv dir'deki en son değiştirilen .db'nin UUID'i (mtime >= min_mtime). agy'nin
    O AN yazdığı aktif turun db'sini (ilk turda resume-uuid yokken) bulmak için."""
    try:
        dbs = glob.glob(os.path.join(_CONV_DIR, "*.db"))
    except Exception:
        return None
    if min_mtime:
        try:
            dbs = [p for p in dbs if os.path.getmtime(p) >= min_mtime]
        except Exception:
            pass
    if not dbs:
        return None
    try:
        newest = max(dbs, key=os.path.getmtime)
    except Exception:
        return None
    name = os.path.basename(newest)
    return name[:-3] if name.lower().endswith(".db") else name


def poll_agy_activity(uuid: str, since_idx: int = -1, limit: int = 12) -> Tuple[List[str], int]:
    """CANLI liveness+progress için: since_idx sonrası tool aktivite özetlerini VE gördüğü
    en yüksek idx'i döndürür → (aktiviteler, yeni_max_idx). agy --print uzun meshy işinde
    stdout üretmez ama db'ye step yazar; bu fonksiyon o büyümeyi hem canlılık sinyali hem
    ilerleme göstergesi olarak okur. Yeni step yoksa ([], since_idx) döner."""
    if not uuid:
        return [], since_idx
    db_path = os.path.join(_CONV_DIR, f"{uuid}.db")
    if not os.path.exists(db_path):
        return [], since_idx
    tmp = db_path + ".uaipoll"
    src = tmp
    try:
        shutil.copy2(db_path, tmp)
        for _ext in ("-wal", "-shm"):
            if os.path.exists(db_path + _ext):
                try:
                    shutil.copy2(db_path + _ext, tmp + _ext)
                except Exception:
                    pass
    except Exception:
        src = db_path
    acts: List[str] = []
    new_idx = since_idx
    con = None
    try:
        con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT idx, step_payload FROM steps WHERE idx > ? ORDER BY idx", (since_idx,)
        ).fetchall()
        for idx, payload in rows:
            if idx > new_idx:
                new_idx = idx
            if not payload:
                continue
            a = _extract_tool_activity(payload if isinstance(payload, (bytes, bytearray)) else bytes(payload or b""))
            if a and (not acts or acts[-1] != a):
                acts.append(a)
    except Exception:
        pass
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass
        if src == tmp:
            for _ext in ("", "-wal", "-shm"):
                try:
                    os.remove(tmp + _ext)
                except Exception:
                    pass
    return acts[-limit:], new_idx


def get_max_step_idx(uuid: str, fallback: int = -1) -> int:
    """Turun .db'sindeki en yüksek step idx'ini döndürür (resume'da 'bir sonraki turun
    başlangıç noktası' için). Okunamıyorsa fallback döner."""
    if not uuid:
        return fallback
    db_path = os.path.join(_CONV_DIR, f"{uuid}.db")
    if not os.path.exists(db_path):
        return fallback
    tmp = db_path + ".uaimax"
    src = tmp
    try:
        shutil.copy2(db_path, tmp)
    except Exception:
        src = db_path
    con = None
    try:
        con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        row = con.execute("SELECT MAX(idx) FROM steps").fetchone()
        return int(row[0]) if row and row[0] is not None else fallback
    except Exception:
        return fallback
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


def read_agy_tool_activity(uuid: str, since_idx: int = -1, limit: int = 12) -> List[str]:
    """Turun .db'sinden tool aktivite özetlerini (sırayla, ardışık-tekrarsız) döndürür.
    since_idx sonrası step'ler okunur (resume'da eski turların aktivitesini eleme).
    stdout boş kalıp final prose yoksa 'agy ne yaptı' göstermek için kullanılır."""
    if not uuid:
        return []
    db_path = os.path.join(_CONV_DIR, f"{uuid}.db")
    if not os.path.exists(db_path):
        return []
    tmp = db_path + ".uaitool"
    src = tmp
    try:
        shutil.copy2(db_path, tmp)
    except Exception:
        src = db_path
    acts: List[str] = []
    con = None
    try:
        con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT step_payload FROM steps WHERE idx > ? ORDER BY idx", (since_idx,)
        ).fetchall()
        for (payload,) in rows:
            if not payload:
                continue
            a = _extract_tool_activity(payload if isinstance(payload, (bytes, bytearray)) else bytes(payload or b""))
            if a and (not acts or acts[-1] != a):
                acts.append(a)
    except Exception as e:
        logger.warning(f"[agy_session] tool activity okuma hatası ({uuid}): {e}")
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
    return acts[-limit:]
