"""Ürünün KULLANICININ projesine yazdığı yerel araç dosyalarını `.gitignore`'a alır.

Neden var (2026-07-29 ölçümü, K3): ürün dört ayrı noktada kullanıcının Unity
projesine config dosyası yazıyor (`.mcp.json`, `opencode.json`,
`.cursor/mcp.json`, `.cursor/cli.json`) ve bunlar unityMCP'nin `X-API-Key`'ini
**düz metin** taşıyor. Kullanıcının gerçek projesinde (GitHub remote'u olan
`MatchDayOfficial`) ölçüldü: iki dosya gitignore'daydı ama satırları kullanıcı
kendi eliyle yazmıştı (`git blame` → 24 Tem commit'i), `.cursor/mcp.json` ise
İZLENİYORDU. Ürün hiçbir yere gitignore girdisi eklemiyordu, yani yeni bir
kullanıcıda koruma sıfır.

Bu modül `providers` altında: `agentic` → `providers` yönü zaten kurulu
(`agent_runner` düzinelerce yerde `providers.*` import ediyor). Ters yön
(`providers` → `agentic`) bu depoda bir kez döngüye sebep oldu — burada YENİ bir
ters import açılmıyor, modülün hiçbir proje-içi bağımlılığı yok.

Sözleşme: **bu modülün hiçbir fonksiyonu çağıranın yoluna istisna fırlatmaz.**
gitignore yazamamak bir kolaylık kaybıdır; sohbetin ya da oturum açılışının
kırılması değil. Bu yüzden her giriş noktası geniş bir `except` ile bitiyor.
"""

import logging
import os
import subprocess
import tempfile
from typing import Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

# Etiketli blok: kullanıcı `git diff`'inde ne olduğunu görsün ve tek parça
# silebilsin. Sessizce araya satır sıkıştırmak, kullanıcının kendi dosyasını
# ürünün habersizce düzenlemesi demek olurdu.
BLOCK_BEGIN = "# >>> Unity Architect AI — yerel araç dosyaları (ürün tarafından eklendi) >>>"
BLOCK_END = "# <<< Unity Architect AI <<<"
_BLOCK_NOTE = (
    "# Bu satırları Unity Architect AI ekledi — istemiyorsanız bu bloğu\n"
    "# (iki etiket dahil) silebilirsiniz, uygulama çalışmaya devam eder.\n"
    "# Sebebi: aşağıdaki dosyalar yerel MCP anahtarını DÜZ METİN taşır ve\n"
    "# depoya girerlerse anahtar da girer.\n"
)

# git alt sürecinin bekleme sınırı. Ağ yok, yerel disk işi: 5 sn cömert. Sınır
# olmadan, bozuk bir depoda (kilitli index, ağ dosya sistemi) oturum açılışı
# git'i beklerken asılı kalırdı.
_GIT_TIMEOUT_S = 5


# ───────────────────────────── yol güvenliği ──────────────────────────────


def _resolve_gitignore(workspace: str) -> Optional[tuple]:
    """(ws_real, gitignore_path) döndürür; güvenli değilse None.

    Symlink'le config ezme bu depoda ÖLÇÜLMÜŞ bir sınıf (K4: altı yazım
    noktasının altısı da workspace dışındaki kurbanı ezdi). Burada aynı sınıfı
    yeni bir noktada açmamak için hem workspace hem de `.gitignore` `realpath`
    ile çözülüyor ve hedefin gerçek konumu workspace'in İÇİNDE olmak zorunda.
    `realpath` iki tarafa da uygulanıyor: yalnız hedefe uygulamak, workspace'in
    kendisi bir bağ olduğunda (macOS'ta `/tmp` → `/private/tmp`) meşru
    kurulumları yanlışlıkla reddederdi.
    """
    if not workspace:
        return None
    ws_real = os.path.realpath(workspace)
    if not os.path.isdir(ws_real):
        return None
    path = os.path.join(ws_real, ".gitignore")
    target_real = os.path.realpath(path)
    if os.path.dirname(target_real) != ws_real:
        logger.warning(
            "[gitignore] %s workspace dışına (%s) işaret ediyor — yazılmadı.",
            path, target_real,
        )
        return None
    return ws_real, path


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _atomic_write(path: str, content: str, ws_real: str) -> None:
    """Geçici dosya + `os.replace`. Yarı yazılmış bir `.gitignore` bırakmaz.

    Geçici dosya BİLEREK workspace'in içinde: `os.replace` ancak aynı dosya
    sisteminde atomik. Hata durumunda temizleniyor, yoksa kullanıcının
    `git status`'unda artık bir `.gitignore.*.tmp` kalırdı.
    """
    fd, tmp = tempfile.mkstemp(dir=ws_real, prefix=".gitignore.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(tmp, 0o644)   # mkstemp 0600 verir; `.gitignore` sır değil
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ──────────────────────────── kapsama tespiti ─────────────────────────────


def _git_covered(ws_real: str, entries: List[str]) -> Optional[Set[str]]:
    """git'e göre zaten yok sayılan girdiler; ölçülemezse None.

    `--no-index` ŞART ve ölçümle seçildi (2026-07-29, git 2.50.1): onsuz
    `check-ignore`, TAKİP EDİLEN bir dosya için desen eşleşse bile rc=1 ("yok
    sayılmıyor") döner. O davranışla, zaten gitignore'da yazan ama takip edilen
    bir dosya her oturumda "eksik" görünür ve bloğa tekrar tekrar eklenirdi.
    `--no-index` saf desen sorusunu sorar; takip durumu ayrıca `_tracked()` ile
    ölçülüp kullanıcıya uyarı olarak veriliyor.

    Tek alt süreçte tüm girdiler sorulur (`--stdin`): rc=0 "en az biri", rc=1
    "hiçbiri" demek — ikisi de geçerli cevap. Başka her şey (repo değil → 128,
    git yok, zaman aşımı) ölçülemedi sayılır ve çağıran literal karşılaştırmaya
    düşer.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", ws_real, "check-ignore", "--no-index", "--stdin"],
            # `input` BYTES ve `text` YOK — ölçüldü (30 Tem 2026, Windows):
            # `text=True` ile stdin `io.TextIOWrapper(newline=None)` üzerinden
            # yazılıyor ve her `\n` platform ayracına çevriliyor (`\r\n`). git
            # `\r`'yi YOL ADININ PARÇASI sayıyor → hiçbir girdi eşleşmiyor →
            # fonksiyon her zaman boş küme dönüyordu. Yani git katmanı Windows'ta
            # sessizce ÖLÜ: ürün literal karşılaştırmaya düşüyor, `*.json` gibi
            # geniş desenler tanınmıyor ve kullanıcının `.gitignore`'una zaten
            # kapsanan girdiler için gereksiz blok ekleniyordu.
            # İki varyantlı ölçüm: tek fark `input=b"..."` iken rc 1 → 0 ve
            # stdout `.mcp.json` döndü.
            input=("\n".join(entries) + "\n").encode("utf-8"),
            capture_output=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode not in (0, 1):
        return None
    cikti = proc.stdout.decode("utf-8", "replace")
    return {line.strip() for line in cikti.splitlines() if line.strip()}


def _tracked(ws_real: str, entries: List[str]) -> List[str]:
    """git'in HÂLÂ takip ettiği girdiler. Ölçülemezse boş liste."""
    try:
        proc = subprocess.run(
            ["git", "-C", ws_real, "ls-files", "--"] + entries,
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _literal_present(text: str, entry: str) -> bool:
    """Satır bazlı birebir karşılaştırma — git yolunun yedeği.

    Geniş desenleri (`*.json`) GÖREMEZ; onu yalnız git yakalar. Buradaki iş
    ikili: (a) git'siz dizinlerde tek koruma, (b) git yolunda ikinci emniyet —
    bloğumuz zaten yazılıysa ikinci kez yazılmasını engeller.
    """
    want = entry.strip().lstrip("/").rstrip("/")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lstrip("/").rstrip("/") == want:
            return True
    return False


def _compose(existing: str, missing: List[str]) -> str:
    """Eksik girdileri etiketli bloğa yerleştirilmiş hâlde döndürür.

    Blok dosyanın **başına** konuyor (kullanıcı kararı, 29 Tem 2026): sona
    eklenirse uzun bir `.gitignore`'da görünmez ve kullanıcı `git diff`'te
    açıklayamadığı bir değişiklik görür. Başta durunca ilk bakışta "bunu ürün
    ekledi, istemezsem silerim" diyebiliyor.

    Blok zaten varsa İÇİNE eklenir; ikinci bir blok açmak kullanıcıya aynı
    etiketten birden fazla gösterirdi ve "tek parça sil" vaadini bozardı.
    """
    added = "".join(f"{e}\n" for e in missing)
    if BLOCK_BEGIN in existing and BLOCK_END in existing:
        cut = existing.index(BLOCK_END)
        return existing[:cut] + added + existing[cut:]
    block = BLOCK_BEGIN + "\n" + _BLOCK_NOTE + added + BLOCK_END + "\n"
    if existing and not existing.startswith("\n"):
        block += "\n"   # bloğumuzla kullanıcının ilk satırı arasına nefes payı
    return block + existing


# ───────────────────────────── genel arayüz ───────────────────────────────


def ensure_gitignored(workspace: str, entries: Iterable[str]) -> None:
    """`entries`'i workspace'in `.gitignore`'ına idempotent şekilde ekler.

    Zaten yok sayılan (geniş desen dahil) hiçbir girdi için dosyaya DOKUNULMAZ.
    Kural: dosyayı yazan nokta, girdisini de yazsın — tek bir kuruluma bağlamak
    diğer yazım noktalarını kapsam dışı bırakır, ki bugünkü boşluk
    (`.cursor/mcp.json` izleniyordu) tam olarak öyle oluştu.
    """
    try:
        # Satır sonu içeren bir girdi `--stdin` protokolünü ve dosya biçimini
        # birden bozardı; ürün sabitleri için imkânsız ama sessiz bozulma yerine
        # sessiz atlama tercih ediliyor.
        wanted = [e.strip() for e in entries
                  if e and e.strip() and "\n" not in e and "\0" not in e]
        if not wanted:
            return
        resolved = _resolve_gitignore(workspace)
        if resolved is None:
            return
        ws_real, path = resolved

        existing = _read_text(path)
        covered = _git_covered(ws_real, wanted)
        missing = [
            e for e in wanted
            if not (covered is not None and e in covered)
            and not _literal_present(existing, e)
        ]
        if not missing:
            return

        _atomic_write(path, _compose(existing, missing), ws_real)
        logger.info("[gitignore] %s: %s eklendi.", path, ", ".join(missing))

        # gitignore ZATEN takip edilen bir dosyayı geri almaz. Ürün bunu
        # kendiliğinden düzeltmiyor: kullanıcının deposunda sessizce index
        # değiştirmek (`git rm --cached`) kabul edilemez — o karar onun.
        still_tracked = _tracked(ws_real, missing)
        if still_tracked:
            logger.warning(
                "[gitignore] %s git tarafından ZATEN takip ediliyor; gitignore "
                "bunu geri almaz. Sırrın depoya girmemesi için: "
                "git rm --cached %s",
                ", ".join(still_tracked), " ".join(still_tracked),
            )
    except Exception as e:
        # Bilerek geniş: gitignore yazamamak oturum açılışını kırmamalı.
        # Sohbet, gitignore'suz da doğru çalışır; tersi doğru değil.
        logger.warning("[gitignore] %s için girdi yazılamadı: %s", workspace, e)


def remove_gitignore_block(workspace: str) -> None:
    """Ürünün eklediği etiketli bloğu kaldırır; kullanıcının satırlarına dokunmaz.

    Temizlik ucu zorunlu: bir şey yaratan her adımın onu silen bir adımı olmalı,
    yoksa kullanıcı ürünü kaldırdığında deposunda sahibi belirsiz satırlar kalır.
    """
    try:
        resolved = _resolve_gitignore(workspace)
        if resolved is None:
            return
        ws_real, path = resolved
        existing = _read_text(path)
        if BLOCK_BEGIN not in existing:
            return

        out, inside = [], False
        for line in existing.splitlines(keepends=True):
            stripped = line.strip()
            if stripped == BLOCK_BEGIN:
                inside = True
                continue
            if inside:
                if stripped == BLOCK_END:
                    inside = False
                continue
            out.append(line)
        # Blok yanındaki nefes payıyla birlikte gitsin; aksi hâlde her
        # ekle/kaldır turunda dosyada bir boş satır birikirdi. Blok BAŞTA
        # olduğu için asıl birikme noktası baştaki boşluk — sondaki de
        # temizleniyor, çünkü blok eski bir dosyada sonda kalmış olabilir.
        while out and not out[0].strip():
            out.pop(0)
        while out and not out[-1].strip():
            out.pop()
        cleaned = "".join(out)
        if cleaned and not cleaned.endswith("\n"):
            cleaned += "\n"
        _atomic_write(path, cleaned, ws_real)
        logger.info("[gitignore] %s: ürün bloğu kaldırıldı.", path)
    except Exception as e:
        logger.warning("[gitignore] %s bloğu kaldırılamadı: %s", workspace, e)
