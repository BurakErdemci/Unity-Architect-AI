"""OmniSharp-Roslyn binary'sini indirir (git'e girmeyecek kadar büyük — video
bins deseni). Build öncesi bir kez koşulur; varsa ve sürüm tutuyorsa atlar."""
import io
import os
import sys
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
    # macOS (Apple Silicon): net6.0 build → son kullanıcının Mac'inde .NET 6 runtime
    # GEREKİR (Windows'un aksine preinstalled değil). Mac release notunda çözülür.
    "osx-arm64": f"https://github.com/OmniSharp/omnisharp-roslyn/releases/download/{VERSION}/omnisharp-osx-arm64-net6.0.zip",
    # Linux (net6.0) — dev/CI için; ürün dağıtımı Win+Mac.
    "linux-x64": f"https://github.com/OmniSharp/omnisharp-roslyn/releases/download/{VERSION}/omnisharp-linux-x64-net6.0.zip",
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
    with open(stamp, "w", encoding="utf-8") as f:
        f.write(VERSION)
    print(f"[fetch_omnisharp] tamam: {dest}")


if __name__ == "__main__":
    fetch(sys.argv[1] if len(sys.argv) > 1 else default_platform())
