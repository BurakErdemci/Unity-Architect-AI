"""OmniSharp-Roslyn binary'sini ve gömülü .NET SDK'sını indirir (git'e girmeyecek
kadar büyük — video bins deseni). Build öncesi bir kez koşulur; varsa, sürüm tutuyorsa
VE hedef ağaç sağlamsa atlar."""
import io
import os
import shutil
import sys
import tarfile
import urllib.request
import zipfile

# Windows konsolu (cp1252) Türkçe karakterlerde patlamasın — build sırasında
# npm bunu bir cp1252 pipe'a yazabiliyor. stdout'u utf-8'e sabitle.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VERSION = "v1.39.15"
# TÜM platformlarda net6.0 varyantı + gömülü .NET SDK kullanılıyor: tek mekanizma.
# Windows'ta eskiden net472 varyantı vardı ve "runtime GEREKMEZ" diye not düşülmüştü;
# bu .NET Framework için doğru ama MSBuild için yanlıştı — ölçüldü 2026-07-27:
# hiçbir OmniSharp v1.39.15 asset'i MSBuild paketlemiyor (win-x64 net472 ve mono
# zip'leri açılıp bakıldı: yalnız Microsoft.Build.Locator.dll var, .msbuild klasörü yok).
# Yani her platformda sistemde ya da gömülü olarak bir .NET SDK şart.
ASSETS = {
    "win-x64": f"https://github.com/OmniSharp/omnisharp-roslyn/releases/download/{VERSION}/omnisharp-win-x64-net6.0.zip",
    "osx-arm64": f"https://github.com/OmniSharp/omnisharp-roslyn/releases/download/{VERSION}/omnisharp-osx-arm64-net6.0.zip",
    "linux-x64": f"https://github.com/OmniSharp/omnisharp-roslyn/releases/download/{VERSION}/omnisharp-linux-x64-net6.0.zip",
}

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
DOTNET_ASSETS = {
    "osx-arm64": f"https://builds.dotnet.microsoft.com/dotnet/Sdk/{DOTNET_VERSION}/dotnet-sdk-{DOTNET_VERSION}-osx-arm64.tar.gz",
    "linux-x64": f"https://builds.dotnet.microsoft.com/dotnet/Sdk/{DOTNET_VERSION}/dotnet-sdk-{DOTNET_VERSION}-linux-x64.tar.gz",
    "win-x64": f"https://builds.dotnet.microsoft.com/dotnet/Sdk/{DOTNET_VERSION}/dotnet-sdk-{DOTNET_VERSION}-win-x64.zip",
}
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


def _intact(dest: str, stamp_value: str, markers: list[str]) -> bool:
    """Damga tek başına yetmez: damga doğru ama ağaç eksik/bozuk olabilir (yarıda
    kesilmiş çıkarma, elle silinmiş klasör). Bu sınıf hata bu repoda iki ayrı
    denetimde çıktı — damgaya ek olarak hedefin İÇİNE bakılıyor."""
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
        if not os.path.exists(p):
            return False
        # `sdk` bir klasör: var ama boşsa MSBuild yine çözülemez.
        if os.path.isdir(p) and not os.listdir(p):
            return False
    return True


def _download(url: str) -> bytes:
    print(f"[fetch_omnisharp] indiriliyor: {url}")
    return urllib.request.urlopen(url, timeout=900).read()


def _extract(data: bytes, url: str, staging: str) -> None:
    """tar.gz exec bitlerini KORUR, zip KORUMAZ — çağıran zip'ten sonra chmod atmalı."""
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(staging)
        return
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        try:
            tf.extractall(staging, filter="data")
        except TypeError:      # Python < 3.11.4: filter parametresi yok
            tf.extractall(staging)


def _install(data: bytes, url: str, dest: str, stamp_value: str, exec_names: list[str]) -> None:
    """Staging'e çıkar, sonra hedefi TAKAS et. Doğrudan hedefe çıkarmak, yarıda
    kesilen bir indirmede yarım ağaç + eski dosya karışımı bırakıyor; damga en
    sona yazıldığı için de o karışım bir sonraki koşuda 'sağlam' görünüyordu."""
    staging = dest + ".staging"
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)
    _extract(data, url, staging)
    for name in exec_names:
        p = os.path.join(staging, name)
        if os.path.exists(p):
            os.chmod(p, 0o755)     # zip exec bitini taşımaz; tar'da da garantiye al
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.replace(staging, dest)
    with open(os.path.join(dest, ".version"), "w", encoding="utf-8") as f:
        f.write(stamp_value)


def fetch(platform: str) -> None:
    dest = os.path.join(DEST, platform)
    marker = omnisharp_marker(platform)
    if _intact(dest, VERSION, [marker]):
        print(f"[fetch_omnisharp] {platform} zaten {VERSION} — atlandı.")
        return
    url = ASSETS[platform]
    _install(_download(url), url, dest, VERSION, [marker])
    print(f"[fetch_omnisharp] tamam: {dest}")


def fetch_dotnet(platform: str) -> None:
    """Gömülü .NET SDK'sını third_party/omnisharp/dotnet-<plat>/ altına indirir.
    electron-builder omnisharp klasörünü olduğu gibi kopyaladığı için pakete otomatik
    girer; omnisharp_manager spawn'da DOTNET_ROOT'u buraya yönlendirir."""
    if platform not in DOTNET_ASSETS:
        return
    dest = os.path.join(DEST, f"dotnet-{platform}")
    markers = dotnet_markers(platform)
    if _intact(dest, DOTNET_VERSION, markers):
        print(f"[fetch_omnisharp] dotnet-{platform} zaten {DOTNET_VERSION} — atlandı.")
        return
    url = DOTNET_ASSETS[platform]
    print(f"[fetch_omnisharp] .NET SDK indiriliyor (~200-290 MB, sürebilir)")
    _install(_download(url), url, dest, DOTNET_VERSION, [markers[0]])
    print(f"[fetch_omnisharp] dotnet tamam: {dest}")


if __name__ == "__main__":
    plat = sys.argv[1] if len(sys.argv) > 1 else default_platform()
    fetch(plat)
    fetch_dotnet(plat)
