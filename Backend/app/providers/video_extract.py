"""Video → kareler (data-URI) + transkript. Kendi ffmpeg/yt-dlp sarmalayıcımız;
harici repo/skill YOK. Kareler mevcut görsel hattına (self.images) katılır.

stdlib-only: kare dedup için PIL yerine ffmpeg'in ürettiği 16x16 gri ham baytları
karşılaştırırız (bkz. _frame_signature)."""
import os
import re
import sys
import glob
import uuid
import base64
import shutil
import logging
import subprocess
from urllib.parse import urlparse
from typing import List, Optional

from providers.video_bin import ffmpeg_path, ytdlp_path, missing_binaries

# `spawn_env` app KÖKÜNDE duruyor, `providers` paketinin içinde değil (bkz. o
# dosyanın başındaki gerekçe). Üretimde `Backend/app` zaten sys.path'te (main.py
# ve testler koyuyor), yani aşağıdaki ekleme orada işlemsizdir; modülün kendi
# yolunu bilmesi, onu paket ağacının nasıl kurulduğundan bağımsız kılıyor —
# `unity_ai_mcp/unity_mcp_manager.py:389` aynı deseni aynı sebeple kullanıyor.
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
from spawn_env import build_spawn_env  # noqa: E402  (yukarıdaki yol kurulumundan sonra)

logger = logging.getLogger(__name__)

# Windows: ffmpeg/yt-dlp konsol penceresi flash'ını engelle (non-Windows'ta 0 = etkisiz).
# _frame_signature kare-başına ffmpeg çağırdığı için bu olmadan onlarca pencere yanıp sönerdi.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_TMP_SUBDIR = os.path.join(".gamachine_tmp", "video")
_FRAME_CAP = 60


class VideoPipelineError(RuntimeError):
    """Carries WHICH STAGE of the pipeline failed and WHY.

    Why a plain `RuntimeError` was not enough: `_prepare_videos` turned every
    exception into the single text "a video could not be processed", so a
    missing binary and a dead link looked the same to the user — while their
    fixes are entirely different. `code` is the machine-readable name the
    frontend reads; `stage` is the diagnostic step that goes to the log.
    """

    def __init__(self, code: str, message: str, stage: str, detail: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.detail = detail or message

    @property
    def client_detail(self) -> str:
        """The detail that may leave the backend — stage and error kind only.

        `detail` carries whatever the failing step raised, which for a
        subprocess is the whole argv: the resolved binary path, the Windows home
        directory (so the account name), the workspace path, the per-turn temp
        path, and the target URL WITH its query string — an access token in a
        share link lands in the renderer and in the chat history.

        The route layer already refuses to send raw exception text to the client
        for the same reason (`/chat-stream`'s error branch); an audit found this
        new channel going around that decision, so the raw text stays in the log
        and only this reaches the user.
        """
        kind = self.detail.split(":", 1)[0].strip() if ":" in self.detail else ""
        # Only an exception class name is kept — anything else can carry a path.
        if not kind.isidentifier():
            kind = ""
        return f"aşama: {self.stage}" + (f" · {kind}" if kind else "")


class ExtractResult:
    def __init__(self, frame_data_uris: List[str], transcript: str, meta: dict):
        self.frame_data_uris = frame_data_uris
        self.transcript = transcript
        self.meta = meta


# ── Saf yardımcılar (subprocess'siz, kolay test edilir) ─────────────────────
def budget_fps(duration_s: float):
    """(fps, cap) — süreye göre hedef kare yoğunluğu (claude-video mantığının sadeleştirmesi)."""
    d = max(1.0, float(duration_s or 1.0))
    if d <= 30:
        return (1.0, _FRAME_CAP)
    if d <= 180:
        return (0.5, _FRAME_CAP)
    if d <= 600:
        return (0.2, _FRAME_CAP)
    return (max(0.01, min(0.05, _FRAME_CAP / d)), _FRAME_CAP)


def parse_vtt(vtt_text: str) -> str:
    """WebVTT → düz, zaman-damgalı transkript. Boş/duplike/tag'li satırlar temizlenir."""
    if not vtt_text:
        return ""
    out, last, cur_ts = [], None, None
    for ln in vtt_text.splitlines():
        s = ln.strip()
        if not s or s == "WEBVTT" or s.startswith(("NOTE", "Kind:", "Language:")):
            continue
        m = re.match(r"(\d{2}:\d{2}:\d{2})[.,]\d{3}\s*-->", s)
        if m:
            cur_ts = m.group(1)
            continue
        if "-->" in s:
            continue
        txt = re.sub(r"<[^>]+>", "", s).strip()
        if txt and txt != last:
            out.append(f"[{cur_ts}] {txt}" if cur_ts else txt)
            last = txt
    return "\n".join(out)


def _mad(a: bytes, b: bytes) -> float:
    """Ortalama-mutlak-fark (0-255). Uzunluk uymazsa 'çok farklı' say."""
    if not a or not b or len(a) != len(b):
        return 255.0
    return sum(abs(a[i] - b[i]) for i in range(len(a))) / len(a)


def dedup_indices(signatures: List[bytes], threshold: float = 2.0) -> List[int]:
    """Ardışık neredeyse-aynı imzaları eler; TUTULACAK index listesi döner."""
    kept, prev = [], None
    for i, sig in enumerate(signatures):
        if prev is None or _mad(prev, sig) >= threshold:
            kept.append(i)
            prev = sig
    return kept


def frames_to_data_uris(paths: List[str]) -> List[str]:
    """JPEG dosyalarını 'data:image/jpeg;base64,...' listesine çevirir (okunamayan atlanır)."""
    uris = []
    for p in paths:
        try:
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            uris.append(f"data:image/jpeg;base64,{b64}")
        except Exception as e:
            logger.warning(f"[video_extract] kare okunamadı ({p}): {e}")
    return uris


def build_video_block(meta: dict, transcript: str) -> str:
    """Ajana 'bunlar bir videonun kronolojik kareleri' diyen bağlam bloğu."""
    name = meta.get("name") or "video"
    n = meta.get("frame_count", 0)
    dur = meta.get("duration_s")
    dropped = meta.get("dropped", 0)
    head = (f"\n\n[VİDEO] Kullanıcı bir video ekledi ('{name}'"
            + (f", ~{int(dur)} sn" if dur else "")
            + f"). Aşağıda bu videodan çıkarılmış {n} kare GÖRSEL olarak kronolojik "
            "sırada ekli — bunları tek tek resim değil, bir video dizisi gibi yorumla.")
    if dropped:
        head += f" (Not: {dropped} benzer kare token tasarrufu için atlandı.)"
    if transcript:
        head += f"\n\n[VİDEO TRANSKRİPTİ]\n{transcript}"
    return head + "\n"


# ── Mesajdan video URL'si otomatik yakalama (ayrı UI yok) ───────────────────
_VIDEO_HOSTS = (
    "youtube.com", "youtu.be", "vimeo.com", "loom.com", "tiktok.com",
    "twitter.com", "x.com", "instagram.com", "dailymotion.com",
    "twitch.tv", "streamable.com", "facebook.com", "reddit.com", "bilibili.com",
)
_URL_RE = re.compile(r"https?://[^\s<>\"')]+")


def detect_video_urls(text: str, cap: int = 4) -> List[str]:
    """Mesaj metnindeki BİLİNEN video-host URL'lerini bulur (kullanıcı linki doğrudan
    chate yapıştırınca çekilsin diye). Rastgele/bilinmeyen host'lar yok sayılır →
    gereksiz indirme denemesi olmaz. Dedup + en fazla `cap` URL."""
    if not text:
        return []
    seen, out = set(), []
    for raw in _URL_RE.findall(text):
        url = raw.rstrip(".,);]'\"")
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            continue
        if host.startswith("www."):
            host = host[4:]
        if any(host == h or host.endswith("." + h) for h in _VIDEO_HOSTS):
            if url not in seen:
                seen.add(url)
                out.append(url)
                if len(out) >= cap:
                    break
    return out


# ── Orkestrasyon (ffmpeg / yt-dlp subprocess) ───────────────────────────────
def _attach_root(workspace: Optional[str]) -> str:
    base = workspace if (workspace and os.path.isdir(workspace)) else "."
    return os.path.join(base, _TMP_SUBDIR)


def _run(cmd: list, timeout: int, check: bool = True):
    """ffmpeg / yt-dlp'yi SÜZÜLMÜŞ bir ortamla başlatır.

    Neden env= zorunlu (dış denetim, 2026-07-29): burası `env=` almadan
    çalışıyordu, yani her ffmpeg karesi ve her yt-dlp indirmesi backend'in
    ortamının TAMAMINI devralıyordu — `LOCAL_APP_TOKEN` (backend'in tek yetki
    kanıtı), `API_KEY_ENCRYPTION_KEY` (DB'deki kullanıcı anahtarlarının
    şifreleme anahtarı) ve export edilmiş vendor anahtarları dahil.
    Kapı testindeki eski muafiyetin gerekçesi "sabit argv, vendor anahtarı
    TÜKETMİYOR" idi; bu yanlış türden bir gerekçe — bir ikilinin anahtarı
    tüketmemesi onu ALMASINI engellemiyor, ve yt-dlp ağa çıkan üçüncü taraf
    bir araç (uzaktaki siteye bakan kodu biz yazmıyoruz).

    Neden aile YOK (`build_spawn_env()` çıplak, `family=` verilmiyor): aile
    katmanı bir sağlayıcının KENDİ kimlik değişkenlerini geçirmek için var
    (ANTHROPIC_API_KEY, OPENAI_API_KEY…). ffmpeg/yt-dlp'nin böyle bir kimliği
    yok; onlara bir aile vermek tam da kapattığımız sızıntıyı geri açardı.
    Taban katman (`_BASE_ENV_ALLOWLIST`) bu iki ikilinin okuduğu işletimsel
    adların hepsini zaten taşıyor ve her biri gerekli:
      · PATH        — yt-dlp video+ses akışlarını BİRLEŞTİRMEK için ffmpeg'i
                      PATH'ten arıyor; ayrıca frozen olmayan kurulumda
                      ikililerin kendisi de PATH'ten çözülüyor (video_bin).
      · HOME/XDG_*  — yt-dlp'nin config ve cache dizini (~/.config/yt-dlp,
                      ~/.cache/yt-dlp); Windows'ta USERPROFILE/APPDATA.
      · TMPDIR/TMP/TEMP — yt-dlp parça dosyalarını, PyInstaller ile paketlenmiş
                      ikili de kendini oraya açıyor; düşerse indirme kırılır.
      · HTTP(S)_PROXY / ALL_PROXY / NO_PROXY (+ küçük harfli biçimleri)
                    — kurumsal ağda yt-dlp'nin ağa çıkabildiği TEK yol.
      · SSL_CERT_FILE / SSL_CERT_DIR / REQUESTS_CA_BUNDLE / CURL_CA_BUNDLE
                    — TLS'i kesen ağlarda düşerse her indirme sertifika
                      hatasıyla ölür ve kullanıcının gördüğü mesaj sebebi gizler.
      · LANG/LC_*   — çıktı ve dosya adı kodlaması (`Duration:` ayrıştırması
                      ffmpeg'in stderr'inden okunuyor).
    Bilerek KESİLENLER: LOCAL_APP_TOKEN, API_KEY_ENCRYPTION_KEY ve tüm
    `*_API_KEY`/`*_TOKEN`/`*_SECRET` adları (bkz. spawn_env.py'deki kütük).
    Kırılma yönü ölçüldü: tests/test_video_extract_integration.py hem sızıntıyı
    hem de PATH/HOME'un GEÇTİĞİNİ aynı çağrıda ölçüyor.
    """
    return subprocess.run(cmd, capture_output=True, timeout=timeout, check=check,
                          creationflags=_NO_WINDOW, env=build_spawn_env())


def _probe_duration(video_path: str) -> float:
    """ffprobe'a gerek kalmadan 'ffmpeg -i' stderr'inden süreyi ayıklar."""
    try:
        r = _run([ffmpeg_path(), "-hide_banner", "-i", video_path], timeout=30, check=False)
        err = (r.stderr or b"").decode("utf-8", "ignore")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", err)
        if m:
            h, mi, s, cs = map(int, m.groups())
            return h * 3600 + mi * 60 + s + cs / 100.0
    except Exception:
        pass
    return 0.0


def _extract_frames(video_path: str, out_dir: str, fps: float, cap: int) -> List[str]:
    """fps-örnekleme + 640px ölçekle. Dedup sonrası cap'e ineceğimiz için cap*3 ham çeker."""
    out_pat = os.path.join(out_dir, "frame_%04d.jpg")
    _run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-i", video_path,
          "-vf", f"fps={fps},scale=640:-2", "-frames:v", str(cap * 3), "-q:v", "4", out_pat],
         timeout=300)
    return sorted(glob.glob(os.path.join(out_dir, "frame_*.jpg")))


def _frame_signature(frame_path: str) -> bytes:
    """ffmpeg ile 16x16 gri ham bayt (256B) imza — PIL'siz dedup."""
    try:
        r = _run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-i", frame_path,
                  "-vf", "scale=16:16,format=gray", "-f", "rawvideo", "-"], timeout=20)
        return (r.stdout or b"")[:256]
    except Exception:
        return b""


def _download_url(url: str, out_dir: str):
    """yt-dlp: ≤720p video + altyazı (varsa). (video_path, transcript, name) döner.
    GÜVENLİK: url kullanıcıdan gelir → önce http/https şeması doğrulanır, sonra '--' ile
    yt-dlp seçenek-ayrıştırması bitirilir. Bu, '-'/'--exec' gibi bir 'URL'nin flag olarak
    sızıp komut çalıştırmasını (argv flag-smuggling / RCE) engeller."""
    p = urlparse(url or "")
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("desteklenmeyen video URL'si (yalnız http/https)")
    logger.info(f"[video_extract] aşama=indirme başlıyor ({p.netloc})")
    out_tmpl = os.path.join(out_dir, "dl.%(ext)s")
    # 1) VİDEO (kritik yol). Altyazı flag'i YOK — böylece altyazı hatası (429/yok/ağ)
    #    videoyu DÜŞÜRMEZ. Format yatay VE dikey (Shorts) için sağlam: 1080'i her iki
    #    yönde dener, sonra best'e düşer. ('mp4[height<=720]' dikey Shorts'ta -height 1280-
    #    ve ayrı-stream'li modern YouTube'da eşleşmeyip exit-1 veriyordu.) Birleştirme
    #    container'ını yt-dlp seçer (ffmpeg webm/mkv de okur).
    _run([ytdlp_path(), "--no-playlist", "--no-warnings",
          "-f", "bestvideo[height<=1080]+bestaudio/bestvideo[width<=1080]+bestaudio/best[height<=1080]/best",
          "-o", out_tmpl, "--", url], timeout=600)
    vids = [q for q in glob.glob(os.path.join(out_dir, "dl.*")) if not q.endswith(".vtt")]
    if not vids:
        raise RuntimeError("video indirilemedi (yt-dlp çıktısı yok)")
    # 2) ALTYAZI (best-effort, AYRI çağrı). check=False + try/except: 429/eksik/ağ
    #    hatası yutulur → transkript alınamasa bile kareler yine döner.
    transcript = ""
    try:
        logger.info("[video_extract] aşama=altyazı başlıyor")
        _run([ytdlp_path(), "--no-playlist", "--no-warnings", "--skip-download",
              "--write-auto-subs", "--write-subs", "--sub-langs", "en.*,tr.*",
              "--convert-subs", "vtt", "-o", out_tmpl, "--", url], timeout=120, check=False)
        subs = glob.glob(os.path.join(out_dir, "dl*.vtt"))
        if subs:
            with open(subs[0], encoding="utf-8", errors="ignore") as f:
                transcript = parse_vtt(f.read())
    except Exception as e:
        # Deliberately swallowed (frames are useful without a transcript) but no
        # longer SILENT: which stage fell over is now readable from the log.
        logger.warning(f"[video_extract] aşama=altyazı başarısız (kareler yine de sürecek): {e}")
    return vids[0], transcript, os.path.basename(url) or "url-video"


def extract(source: dict, workspace: Optional[str], tag: str) -> ExtractResult:
    """Video kaynağını kare data-URI'leri + transkripte çevirir. Kendi temp'ini temizler."""
    kind = (source or {}).get("kind")
    tmp_root = os.path.join(_attach_root(workspace), f"{tag}_{uuid.uuid4().hex[:8]}")
    os.makedirs(tmp_root, exist_ok=True)
    try:
        # Binary gate goes FIRST: diagnosing a missing ffmpeg/yt-dlp backwards
        # from the subprocess failure was near impossible (the error text is
        # generic, "the system cannot find the file specified"). Here the NAME of
        # what is missing is known and can be shown to the user.
        _missing = missing_binaries(need_ytdlp=(kind == "url"))
        if _missing:
            _ad = " ve ".join(_missing)
            raise VideoPipelineError(
                "video_binary_missing",
                f"Videoyu işlemek için gereken {_ad} programı bu bilgisayarda bulunamadı; "
                "video atlandı, sohbet metinle sürüyor.",
                stage="binary_resolve",
                detail=f"çözülemeyen binary: {', '.join(_missing)}")

        transcript = ""
        if kind == "path":
            video_path = source.get("path")
            if not video_path or not os.path.isfile(video_path):
                raise VideoPipelineError(
                    "video_download_failed",
                    "Eklenen video dosyası bulunamadı.",
                    stage="kaynak", detail=f"video bulunamadı: {video_path}")
            # GÜVENLİK: mutlak yola normalize et → ffmpeg '-i' argümanı '-' ile başlayıp
            # flag gibi yorumlanamaz (argv flag-smuggling savunması).
            video_path = os.path.abspath(video_path)
            name = source.get("name") or os.path.basename(video_path)
        elif kind == "url":
            try:
                video_path, transcript, name = _download_url(source.get("url") or "", tmp_root)
            except VideoPipelineError:
                raise
            except Exception as e:
                raise VideoPipelineError(
                    "video_download_failed",
                    "Videonun linki indirilemedi (link kapalı, bölgesel kısıtlı ya da "
                    "ağ engelli olabilir); video atlandı, sohbet metinle sürüyor.",
                    stage="indirme", detail=f"{type(e).__name__}: {e}") from e
        else:
            raise VideoPipelineError(
                "video_extract_failed", "Bu video kaynağı tanınmadı.",
                stage="kaynak", detail=f"bilinmeyen video kaynağı: {kind!r}")

        try:
            logger.info("[video_extract] aşama=süre ölçümü")
            duration = _probe_duration(video_path)
            fps, cap = budget_fps(duration)
            logger.info(f"[video_extract] aşama=kare çıkarma (süre≈{duration:.0f}s, fps={fps})")
            raw = _extract_frames(video_path, tmp_root, fps, cap)
        except Exception as e:
            raise VideoPipelineError(
                "video_extract_failed",
                "Videodan görüntü çıkarılamadı; video atlandı, sohbet metinle sürüyor.",
                stage="kare çıkarma", detail=f"{type(e).__name__}: {e}") from e
        if not raw:
            raise VideoPipelineError(
                "video_extract_failed",
                "Videodan hiç görüntü çıkmadı (dosya bozuk ya da desteklenmeyen bir "
                "biçimde olabilir); video atlandı, sohbet metinle sürüyor.",
                stage="kare çıkarma", detail="ffmpeg 0 kare üretti")
        sigs = [_frame_signature(p) for p in raw]
        keep = dedup_indices(sigs, threshold=2.0)
        kept = [raw[i] for i in keep][:cap]
        dropped = len(raw) - len(kept)
        uris = frames_to_data_uris(kept)
        if dropped:
            logger.info(f"[video_extract] {name}: {len(raw)} ham → {len(uris)} kare ({dropped} atlandı)")
        meta = {"name": name, "duration_s": duration,
                "frame_count": len(uris), "dropped": max(0, dropped)}
        return ExtractResult(uris, transcript, meta)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
