"""OmniSharp-Roslyn binary'sini indirir (git'e girmeyecek kadar büyük — video
bins deseni). Build öncesi bir kez koşulur; varsa ve sürüm tutuyorsa atlar."""
import io
import os
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
ASSETS = {
    # Windows: net472 build → .NET Framework 4.8 Win10/11'de hazır, runtime GEREKMEZ.
    "win-x64": f"https://github.com/OmniSharp/omnisharp-roslyn/releases/download/{VERSION}/omnisharp-win-x64.zip",
    # macOS (Apple Silicon): net6.0 build. Runtime GÖMÜLÜR (aşağıda fetch_dotnet) —
    # kullanıcı HİÇBİR ŞEY kurmaz (0-kurulum prensibi). Roll-forward ile .NET 10'da koşar.
    "osx-arm64": f"https://github.com/OmniSharp/omnisharp-roslyn/releases/download/{VERSION}/omnisharp-osx-arm64-net6.0.zip",
    # Linux (net6.0) — dev/CI için; ürün dağıtımı Win+Mac.
    "linux-x64": f"https://github.com/OmniSharp/omnisharp-roslyn/releases/download/{VERSION}/omnisharp-linux-x64-net6.0.zip",
}

# Gömülü .NET runtime (yalnız mac/linux — Windows net472 kullanır, gerekmez).
# .NET 10 = LTS (EOL 2028-11); OmniSharp net6.0 hedefli ama DOTNET_ROLL_FORWARD=Major
# ile 10'da çalıştığı canlı LSP initialize testiyle doğrulandı (2026-07-16, macOS arm64).
DOTNET_VERSION = "10.0.10"
DOTNET_ASSETS = {
    "osx-arm64": f"https://builds.dotnet.microsoft.com/dotnet/Runtime/{DOTNET_VERSION}/dotnet-runtime-{DOTNET_VERSION}-osx-arm64.tar.gz",
    "linux-x64": f"https://builds.dotnet.microsoft.com/dotnet/Runtime/{DOTNET_VERSION}/dotnet-runtime-{DOTNET_VERSION}-linux-x64.tar.gz",
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


def fetch(platform: str) -> None:
    dest = os.path.join(DEST, platform)
    stamp = os.path.join(dest, ".version")
    if os.path.exists(stamp) and open(stamp, encoding="utf-8").read().strip() == VERSION:
        print(f"[fetch_omnisharp] {platform} zaten {VERSION} — atlandı.")
        return
    url = ASSETS[platform]
    print(f"[fetch_omnisharp] indiriliyor: {url}")
    data = urllib.request.urlopen(url, timeout=300).read()
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest)
    # zipfile.extractall exec bitini KORUMAZ → macOS/Linux'ta OmniSharp host
    # binary'si spawn edilemez (PermissionError). Windows'ta gereksiz/zararsız.
    if not sys.platform.startswith("win"):
        host = os.path.join(dest, "OmniSharp")
        if os.path.exists(host):
            os.chmod(host, 0o755)
    with open(stamp, "w", encoding="utf-8") as f:
        f.write(VERSION)
    print(f"[fetch_omnisharp] tamam: {dest}")


def fetch_dotnet(platform: str) -> None:
    """Gömülü .NET runtime'ı third_party/omnisharp/dotnet-<plat>/ altına indirir.
    electron-builder omnisharp klasörünü olduğu gibi kopyaladığı için pakete otomatik
    girer; omnisharp_manager spawn'da DOTNET_ROOT'u buraya yönlendirir."""
    if platform not in DOTNET_ASSETS:
        return  # win-x64: net472, runtime gerekmez
    dest = os.path.join(DEST, f"dotnet-{platform}")
    stamp = os.path.join(dest, ".version")
    if os.path.exists(stamp) and open(stamp, encoding="utf-8").read().strip() == DOTNET_VERSION:
        print(f"[fetch_omnisharp] dotnet-{platform} zaten {DOTNET_VERSION} — atlandı.")
        return
    url = DOTNET_ASSETS[platform]
    print(f"[fetch_omnisharp] .NET runtime indiriliyor: {url}")
    data = urllib.request.urlopen(url, timeout=300).read()
    os.makedirs(dest, exist_ok=True)
    # tar.gz seçildi: tarfile exec bitlerini KORUR (zip'in aksine) → dotnet host çalışır kalır.
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        tf.extractall(dest)
    host = os.path.join(dest, "dotnet")
    if os.path.exists(host):
        os.chmod(host, 0o755)  # savunma amaçlı — tarfile korur ama garantiye al
    with open(stamp, "w", encoding="utf-8") as f:
        f.write(DOTNET_VERSION)
    print(f"[fetch_omnisharp] dotnet tamam: {dest}")


if __name__ == "__main__":
    plat = sys.argv[1] if len(sys.argv) > 1 else default_platform()
    fetch(plat)
    fetch_dotnet(plat)
