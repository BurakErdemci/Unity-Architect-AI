"""OmniSharp-Roslyn binary'sini ve gömülü .NET SDK'sını indirir (git'e girmeyecek
kadar büyük — video bins deseni). Build öncesi bir kez koşulur; varsa, sürüm tutuyorsa
VE hedef ağaç sağlamsa atlar."""
import glob
import io
import os
import shutil
import sys
import tarfile
import time
import urllib.request
import uuid
import zipfile

# `scripts/` bir paket değil ve bu dosya iki farklı şekilde yükleniyor: doğrudan
# script olarak (o zaman sys.path[0] zaten burası) ve testlerde
# `spec_from_file_location` ile (o zaman burası sys.path'te HİÇ yok). İkinci yolda
# çıplak `import pinned_assets` ImportError veriyor, o yüzden dizin elle ekleniyor.
# `append` (insert değil): stdlib'i gölgeleme riski almadan sona yazıyor.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.append(_SCRIPTS_DIR)
import pinned_assets  # noqa: E402  (sys.path yukarıda hazırlanıyor)

# Windows konsolu (cp1252) Türkçe karakterlerde patlamasın — build sırasında
# npm bunu bir cp1252 pipe'a yazabiliyor. stdout'u utf-8'e sabitle.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PLATFORMS = ("win-x64", "osx-arm64", "linux-x64")

VERSION = "v1.39.15"
# TÜM platformlarda net6.0 varyantı + gömülü .NET SDK kullanılıyor: tek mekanizma.
# Windows'ta eskiden net472 varyantı vardı ve "runtime GEREKMEZ" diye not düşülmüştü;
# bu .NET Framework için doğru ama MSBuild için yanlıştı — ölçüldü 2026-07-27:
# hiçbir OmniSharp v1.39.15 asset'i MSBuild paketlemiyor (win-x64 net472 ve mono
# zip'leri açılıp bakıldı: yalnız Microsoft.Build.Locator.dll var, .msbuild klasörü yok).
# Yani her platformda sistemde ya da gömülü olarak bir .NET SDK şart.


def omnisharp_key(platform: str) -> str:
    return f"omnisharp/{platform}"


def dotnet_key(platform: str) -> str:
    return f"dotnet-sdk/{platform}"


# ⚠️ URL'ler burada KURULMUYOR, `pinned_assets.json`'dan türetiliyor. Eskiden adres
# burada bir f-string'di ve özet başka dosyadaydı; o an "birbiriyle uyuşması gereken
# iki yer" doğuyor — bu depoda 2026-07-27/28'de bulunan arızaların HEPSİ tam olarak
# o şekildeydi. Şimdi bir asset'in adresini değiştirmenin tek yolu, özetiyle aynı
# satıra dokunmak. `asset()` bilinmeyen anahtarda patlıyor, yani bir platformu
# kütüğe eklemeyi unutmak import anında görülüyor, build'in ortasında değil.
ASSETS = {p: pinned_assets.asset(omnisharp_key(p))["url"] for p in PLATFORMS}

# Gömülü .NET **SDK** (runtime DEĞİL). OmniSharp proje yüklemek için MSBuild'i
# SDK'dan çözüyor; yalnız runtime gömüldüğünde `hostfxr_resolve_sdk2` başarısız
# oluyor ve — kritik — OmniSharp `initialize` isteğine NE result NE error frame'i
# gönderiyor, süreci de kapatmıyor. İstemcinin future'ı hiç tamamlanmıyor, istek
# timeout dolana kadar asılıyor. Ölçüldü 2026-07-27 (macOS arm64):
#   runtime-only  → 25 sn boyunca initialize yanıtı yok, "Failed to find all
#                   versions of .NET Core MSBuild" yalnız window/logMessage'ta
#   gerçek SDK    → initialize yanıtı 3.0 sn'de geldi
# .NET 10 = LTS (EOL 2028-11). OmniSharp net6.0 hedefli → DOTNET_ROLL_FORWARD=Major.
DOTNET_VERSION = "10.0.100"
DOTNET_ASSETS = {p: pinned_assets.asset(dotnet_key(p))["url"] for p in PLATFORMS}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "third_party", "omnisharp")


def default_platform() -> str:
    """Argsız çağrıda çalışılan OS'e göre doğru asset — prebuild hook'u bunu kullanır."""
    if sys.platform == "darwin":
        return "osx-arm64"
    if sys.platform.startswith("win"):
        return "win-x64"
    return "linux-x64"


def omnisharp_marker(platform: str) -> str:
    """Çıkarılmış OmniSharp ağacının sağlamlık kanıtı: host binary'nin kendisi."""
    return "OmniSharp.exe" if platform.startswith("win") else "OmniSharp"


def dotnet_markers(platform: str) -> list[str]:
    """SDK ağacının sağlamlık kanıtı. `sdk/` ÖZELLİKLE aranıyor: runtime paketi de
    `dotnet` host'unu ve `shared/` klasörünü getiriyor, yani host'un varlığı SDK
    olduğunu KANITLAMAZ — 27 Tem 2026'daki 120 sn asılma arızasının tam sebebi buydu."""
    return ["dotnet.exe" if platform.startswith("win") else "dotnet", "sdk"]


def _stamp_value(version: str, asset_key: str) -> str:
    """Damgaya sürüm numarasının YANINDA sabitlenmiş özetin bir öneki de giriyor.

    Sebebi: sürüm numarası kimliğin tamamı değil. Yayıncı aynı etiketi yeniden
    yayınlarsa (OmniSharp release asset'leri değiştirilebiliyor, .NET build'leri
    yeniden basılabiliyor) eski kurulum "10.0.100" damgasıyla hâlâ güncel görünür,
    `_intact()` True döner, indirme atlanır ve doğrulama HİÇ KOŞMAZ. Yani en çok
    ihtiyaç duyulan durumda kontrol devre dışı kalırdı. Özet kütükte değişince
    damga da değişiyor ve kurulum bayat sayılıyor.

    Önek 12 hex (48 bit) — bu bir güvenlik sınırı değil, yalnız "değişti mi"
    işareti; gerçek doğrulamayı `verify_bytes` tam özetle yapıyor. Kısa tutulmasının
    sebebi damganın elle okunabilir kalması."""
    digest = pinned_assets.asset(asset_key)["digest"].partition(":")[2]
    return f"{version}+{digest[:12]}"


def _contained(root: str, path: str) -> bool:
    """`path`, bağlar ÇÖZÜLDÜKTEN sonra hâlâ `root`'un altında mı.

    Neden `islink` yetmiyor: `islink` tek bir bileşene bakar. Kapı yaprakta
    kurulduğunda (`dest/OmniSharp` bir bağ mı) **yolun kendisi** bağ olabiliyor —
    `dest` dizini dışarıyı gösterirse içindeki dosyalar gerçek dosyadır, `islink`
    False döner ve kapı hiç ateşlenmez. Ölçüldü 2026-07-28 denetiminde: üst dizin
    bağıyla `_intact()` True döndü, `_resolve_binary()` dışarıdaki binary'yi
    döndürdü, `_embedded_dotnet_root()` ise hiç kontrol içermiyordu.

    `realpath` iki tarafta da uygulanıyor: kurulum ağacının tamamı meşru olarak
    bir bağın altında olabilir (macOS'ta `/tmp` → `/private/tmp`, ya da taşınmış
    bir home dizini). Reddedilen şey kökün ALTINDAN DIŞARI çıkan yol."""
    r = os.path.realpath(root)
    p = os.path.realpath(path)
    return p == r or p.startswith(r + os.sep)


def _intact(dest: str, stamp_value: str, markers: list[str]) -> bool:
    """Damga tek başına yetmez: damga doğru ama ağaç eksik/bozuk olabilir (yarıda
    kesilmiş çıkarma, elle silinmiş klasör). Bu sınıf hata bu repoda iki ayrı
    denetimde çıktı — damgaya ek olarak hedefin İÇİNE bakılıyor."""
    # Hedefin KENDİSİ bağ olamaz. Bizim kurulumumuz `os.replace` ile gerçek dizin
    # bırakır; burada bağ görmek beklenmedik bir durum ve "sağlam değil" doğru
    # cevap. Bu satır olmadan aşağıdaki kapsama kontrolü de aldatılabilir: `dest`
    # bağsa `realpath(dest)` saldırganın ağacına çözülür ve içindekiler o köke
    # göre "kapsanmış" görünür.
    if os.path.islink(dest):
        return False
    stamp = os.path.join(dest, ".version")
    if not os.path.exists(stamp):
        return False
    try:
        with open(stamp, encoding="utf-8") as f:
            if f.read().strip() != stamp_value:
                return False
    except OSError:
        return False
    for m in markers:
        p = os.path.join(dest, m)
        # ⚠️ `islink` ÖNCE: `os.path.exists` bağ takip ediyor. Dışarıyı gösteren
        # bir bağ "sağlam kurulum" sayılıyordu ve zinciri şuraya götürüyordu:
        # indirme atlanır → `_resolve_binary()` o bağı döndürür → ürün onu
        # ÇALIŞTIRIR. Yani tek seferlik bir yazma, kalıcı kod çalıştırmaya
        # dönüşüyordu. Dış denetimde ölçüldü (2026-07-28, ikinci model ailesi):
        # `_intact()` dışarıdaki bir binary için True döndü.
        # Bizim çıkarmamız gerçek dosya üretir, bağ üretmez — bağ görmek zaten
        # beklenmedik bir durumdur ve "sağlam değil" doğru cevaptır.
        if os.path.islink(p):
            return False
        # Bağ olmayan ama yine de dışarı çıkan bir yol kalmasın: işaretin kendisi
        # gerçek dosya olsa bile ara bir bileşen bağ olabilir.
        if not _contained(dest, p):
            return False
        if not os.path.exists(p):
            return False
        # `sdk` bir klasör: var ama boşsa MSBuild yine çözülemez.
        if os.path.isdir(p) and not os.listdir(p):
            return False
    return True


def _download(url: str) -> bytes:
    print(f"[fetch_omnisharp] indiriliyor: {url}")
    return urllib.request.urlopen(url, timeout=900).read()


# `filter="data"` desteğinin kesin işareti. `hasattr` ile ölçüldü (2026-07-28):
# 3.9.6 → False, 3.13.13 → True; `data_filter` ile `filter` parametresi aynı
# yamada (PEP 706) geldiği için ikisi birebir örtüşüyor.
_TAR_FILTER_SUPPORTED = hasattr(tarfile, "data_filter")


def _extract(data: bytes, url: str, staging: str) -> None:
    """tar.gz exec bitlerini KORUR, zip KORUMAZ — çağıran zip'ten sonra chmod atmalı.

    ⚠️ Filtresiz `extractall` KULLANILMIYOR ve eski Python'a sessizce düşülmüyor.
    Burada eskiden `except TypeError: tf.extractall(staging)` vardı; dış denetimde
    gerçek 3.9.6 ile ölçüldü (2026-07-28) ve o dalın HİÇBİR içerme kontrolü
    yapmadığı görüldü: `../ESCAPED.txt` hedefin dışına yazıldı, sembolik bağ +
    üstüne yazma iki aşamada dışarı çıktı, dizin ve FIFO de öyle. Filtreli dalda
    hepsi `OutsideDestinationError` / `AbsoluteLinkError` ile reddediliyor.

    Yedek dal teorik de değildi: `Frontend/frontend/package.json` prebuild'i
    `python … || python3 …` diyor ve Homebrew Python'ı olmayan bir makinede
    `python3` stok macOS'un 3.9.6'sı oluyor.

    Desteklenmeyen sürümde ÇIKARMA YERİNE HATA veriliyor. Bu bir build script'i:
    gürültülü başarısızlık, sessizce korumasız çıkarmaktan iyidir.

    Yetenek tespiti `try/except TypeError` ile YAPILMIYOR: o kalıp çağrının
    tamamını sarıyordu, yani filtreleme sırasında derinlerde doğan herhangi bir
    TypeError çağrıyı sessizce filtresiz olarak baştan çalıştırıyordu — üstelik
    ilk geçişte yazılmış dosyaların üstüne (aynı denetimde enjeksiyonla gösterildi)."""
    if url.endswith(".zip"):
        # zipfile üye adından sürücü harfini, baştaki ayraçları ve `..` bileşenlerini
        # DÜŞÜRÜYOR, ayrıca bağ meta verisini hiç uygulamıyor (sembolik bağ üyesi
        # sıradan dosya olarak yazılıyor). Üç yorumlayıcıda ölçüldü: hedefin dışına
        # yazım yok. Yani zip yolunda ek bir kapıya gerek kalmıyor.
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(staging)
        return
    if not _TAR_FILTER_SUPPORTED:
        raise RuntimeError(
            f"Bu Python ({sys.version.split()[0]}) tar çıkarmada 'filter' desteklemiyor, "
            "ve filtresiz çıkarma arşivin hedef klasör dışına yazmasına izin veriyor. "
            "Python 3.12+ (ya da 3.11.4+) ile çalıştırın."
        )
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        tf.extractall(staging, filter="data")


# Ölmüş bir koşunun kalıntısı bu yaştan sonra çöp sayılıyor. Üst sınır ölçülebilir:
# tek indirme `urlopen(timeout=900)` ile sınırlı, çıkarma da onunla aynı mertebede —
# yani CANLI bir koşunun staging'i pratikte dakikalar yaşında. 6 saat, o üst sınırın
# çok üstünde bir emniyet payı; daha kısa bir eşik çok yavaş bir ağda hâlâ çalışan
# komşu koşunun ağacını silme riski taşırdı ki bu tam da düzeltilen arıza olurdu.
_STALE_LEFTOVER_SECONDS = 6 * 3600


def _prune_stale_leftovers(dest: str) -> None:
    """Süreç çıkarma sırasında ölürse yarım ağaç (dotnet'te ~290 MB) diskte kalıyor.
    Adlar koşuya özel olduğu için kalıntı bir sonraki kuruluma KARIŞAMAZ, ama birikir.
    Yaş kapısı şart: ad deseni eşleşen dizin, ŞU AN çalışan başka bir build'in
    staging'i de olabilir — yaşa bakmadan silmek eski sabit-ad arızasını geri getirir.
    glob.escape: depo yolu `[` `]` `?` içerebiliyor, desen olarak yorumlanmasın."""
    now = time.time()
    for pattern in (".staging-*", ".old-*"):
        for leftover in glob.glob(glob.escape(dest) + pattern):
            try:
                if now - os.path.getmtime(leftover) < _STALE_LEFTOVER_SECONDS:
                    continue
            except OSError:
                continue           # başka koşu az önce sildi — bizim işimiz değil
            shutil.rmtree(leftover, ignore_errors=True)


def _install(
    data: bytes,
    url: str,
    dest: str,
    stamp_value: str,
    exec_names: list[str],
    *,
    asset_key: str | None,
) -> None:
    """Baytları DOĞRULA, staging'e çıkar, sonra hedefi TAKAS et. Doğrudan hedefe
    çıkarmak, yarıda kesilen bir indirmede yarım ağaç + eski dosya karışımı
    bırakıyor; damga en
    sona yazıldığı için de o karışım bir sonraki koşuda 'sağlam' görünüyordu.

    Staging yolu KOŞUYA ÖZEL (pid + rastgele belirteç). Sabit `dest + ".staging"`
    iki arıza üretiyordu: (1) aynı checkout'ta eşzamanlı iki build birbirinin
    staging'ini `rmtree` ile siliyordu, (2) ölmüş bir koşunun yarım ağacı yerinde
    duruyordu. pid tek başına yetmiyor — testler ve prebuild hook'u aynı süreçte
    art arda kuruluyor —, o yüzden uuid de var. (Aynı desen bu depoda zaten
    `Frontend/frontend/scripts/copy-monaco.js` içinde kullanılıyor.)

    Takas sırası: eski hedef SİLİNMİYOR, yana alınıyor (rename) ve ancak yeni ağaç
    yerine oturduktan sonra siliniyor. Eski sıra (`rmtree(dest)` → `os.replace`)
    arada ne eski ne yeni ağacın olduğu bir pencere bırakıyordu; orada ölen bir
    süreç `.version` damgasıyla birlikte çalışan kurulumu da götürüyordu. Yeni
    sırada o pencere iki `rename` syscall'ı arasına iniyor ve orada ölünürse hedef
    YOK olur, YARIM olmaz — `_intact()` yoku zaten reddedip yeniden indiriyor.

    Damga takastan ÖNCE staging'in içine yazılıyor: ağacın hâlâ en son yazılan
    dosyası o, ama hedefe geçişi tek bir atomik rename yapıyor. Böylece hedefte
    "damga var, ağaç yarım" durumu hiç oluşamıyor. `_intact()` staging'e hiç
    bakmadığı için damganın orada erken var olması bir şey iddia etmiyor.

    `asset_key` verilirse baytlar sabitlenmiş özetle karşılaştırılır ve uyuşmazlıkta
    `IntegrityError` atılır. Bu kontrol İLK satırda, çıkarmadan da diskte herhangi
    bir dizin yaratmadan önce: bozuk bir arşivi açıp sonra pişman olmak yerine hiç
    açmıyoruz — arşiv çıkarmanın kendisi bir saldırı yüzeyi (bu dosyada zaten iki
    ayrı kaçış arızası düzeltildi) ve doğrulama o yüzeye hiç varmadan bitmeli.
    Uyuşmazlıkta build KIRILIYOR, sessizce atlanmıyor: bu asset'ler ürünün çalışması
    için zorunlu, "doğrulayamadım ama devam ettim" hiçbir şey doğrulamamakla aynı.

    `asset_key=None` yalnız kütükte karşılığı OLMAYAN baytlar için — pratikte
    testlerin enjekte ettiği sentetik arşivler. Üretimdeki iki çağıranın da anahtar
    geçirdiği testle bağlanmış durumda; yoksa bu varsayılan kontrolü sessizce
    kapatmanın kolay yolu olurdu."""
    if asset_key is not None:
        pinned_assets.verify_bytes(data, asset_key)
    token = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
    staging = f"{dest}.staging-{token}"
    previous = f"{dest}.old-{token}"
    os.makedirs(os.path.dirname(dest), exist_ok=True)   # staging dest'in KARDEŞİ
    _prune_stale_leftovers(dest)
    try:
        os.makedirs(staging, exist_ok=True)
        _extract(data, url, staging)
        for name in exec_names:
            p = os.path.join(staging, name)
            # `islink` kapısı: `os.chmod` bağ TAKİP EDİYOR (follow_symlinks varsayılan
            # True) ve `os.path.exists` de öyle. Arşivde tam olarak `OmniSharp` ya da
            # `dotnet` ADINDA bir sembolik bağ varsa, chmod hedefin DIŞINDAKİ dosyanın
            # modunu değiştiriyordu — dış denetimde ölçüldü (2026-07-28): kurban dosya
            # 0600'den 0755'e döndü. Artık filtreli çıkarma böyle bir bağı zaten
            # reddediyor, ama bu kapı ondan bağımsız: zip yolunda filtre yok, ve tek
            # bir savunmaya dayanmak bu deponun daha önce ödediği bir bedel.
            # `follow_symlinks=False` tercih edilmedi: Linux'ta chmod için
            # NotImplementedError atıyor, yani taşınabilir değil.
            if os.path.islink(p):
                raise RuntimeError(f"arşivde beklenmedik sembolik bağ: {name}")
            if os.path.exists(p):
                os.chmod(p, 0o755)     # zip exec bitini taşımaz; tar'da da garantiye al
        # Damga yazımı da bağ takip ediyordu: arşivde `.version` ADINDA bir bağ
        # varsa yazma hedefin dışına gidiyordu (dış denetim, 2026-07-28). Filtreli
        # çıkarma dışarı gösteren bağı zaten reddediyor, ama zip yolunda filtre yok
        # ve tek savunmaya dayanmak bu deponun daha önce ödediği bir bedel.
        stamp_path = os.path.join(staging, ".version")
        if os.path.islink(stamp_path):
            raise RuntimeError("arşivde beklenmedik sembolik bağ: .version")
        with open(stamp_path, "w", encoding="utf-8") as f:
            f.write(stamp_value)
        moved_aside = False
        if os.path.exists(dest):
            os.rename(dest, previous)
            moved_aside = True
        try:
            os.replace(staging, dest)
        except OSError:
            if moved_aside:
                os.rename(previous, dest)      # takas tutmadı → eski ağaç geri
            raise
    finally:
        # Başarıda staging artık yok (rename edildi); hata yolunda YALNIZ KENDİ
        # dizinlerimizi siliyoruz — komşu koşunun kalıntısına dokunmuyoruz.
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(previous, ignore_errors=True)


def fetch(platform: str) -> None:
    dest = os.path.join(DEST, platform)
    marker = omnisharp_marker(platform)
    key = omnisharp_key(platform)
    stamp = _stamp_value(VERSION, key)
    if _intact(dest, stamp, [marker]):
        print(f"[fetch_omnisharp] {platform} zaten {VERSION} — atlandı.")
        return
    url = ASSETS[platform]
    _install(_download(url), url, dest, stamp, [marker], asset_key=key)
    print(f"[fetch_omnisharp] tamam: {dest}")


def fetch_dotnet(platform: str) -> None:
    """Gömülü .NET SDK'sını third_party/omnisharp/dotnet-<plat>/ altına indirir.
    electron-builder omnisharp klasörünü olduğu gibi kopyaladığı için pakete otomatik
    girer; omnisharp_manager spawn'da DOTNET_ROOT'u buraya yönlendirir."""
    if platform not in DOTNET_ASSETS:
        return
    dest = os.path.join(DEST, f"dotnet-{platform}")
    markers = dotnet_markers(platform)
    key = dotnet_key(platform)
    stamp = _stamp_value(DOTNET_VERSION, key)
    if _intact(dest, stamp, markers):
        print(f"[fetch_omnisharp] dotnet-{platform} zaten {DOTNET_VERSION} — atlandı.")
        return
    url = DOTNET_ASSETS[platform]
    print(f"[fetch_omnisharp] .NET SDK indiriliyor (~200-290 MB, sürebilir)")
    _install(_download(url), url, dest, stamp, [markers[0]], asset_key=key)
    print(f"[fetch_omnisharp] dotnet tamam: {dest}")


if __name__ == "__main__":
    plat = sys.argv[1] if len(sys.argv) > 1 else default_platform()
    fetch(plat)
    fetch_dotnet(plat)
