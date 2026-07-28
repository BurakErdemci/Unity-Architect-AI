#!/bin/bash
# Unity MCP için gerekli uv araç zincirini (uv + uvx) macOS'a indirir.
# Bu ikililer installer'a gömülür (electron-builder.yml → extraResources: uv),
# böylece kullanıcının Mac'inde uv kurulu olmasa da Unity MCP çalışır.
# Boyutları büyük olduğu için git'e konmaz (.gitignore); build öncesi bunu çalıştır.
#
# Windows'taki fetch_uv.ps1 tek arch (x64) indirir çünkü Windows tek hedef.
# macOS'ta hem Apple Silicon (arm64) hem Intel (x64) dmg basıldığı için İKİSİNİ de
# indirir ve arch alt-dizinlerine koyar: vendor/uv/darwin-arm64/, vendor/uv/darwin-x64/
# _get_uvx() çalışma anında doğru mimariyi seçer.
#
# Sürüm SABİT, `latest` değil: adres ve beklenen sha256 scripts/pinned_assets.json
# içinde (anahtarlar uv/darwin-arm64, uv/darwin-x64). `latest` kullanmak, her build'in
# o anda yayında olan farklı bir ikiliyi installer'a gömmesi demekti — ne tekrar
# üretilebilir bir çıktı ne de doğrulanacak bir beklenti kalıyordu.
# Sürüm yükseltmek için: `python3 scripts/pinned_assets.py refresh`, sonra diff'i incele.
#
# Kullanım:  bash Backend/vendor/fetch_uv.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$SCRIPT_DIR/uv"
# Betik Backend/vendor/ altında; repo kökü iki üstü.
PINNED="$(cd "$SCRIPT_DIR/../.." && pwd)/scripts/pinned_assets.py"
mkdir -p "$DEST"

fetch_arch() {
  local uv_triple="$1"   # astral-sh/uv release asset triple (arşiv içindeki dizin adı da bu)
  local out_subdir="$2"  # vendor/uv/<out_subdir>
  local key="$3"         # pinned_assets.json anahtarı
  local url
  # Çıkış kodu doğrudan `if !` ile okunuyor: bu depoda ölçüldü, pipe'tan sonraki
  # `$?` yanlış komutu ölçüyor ve hata sessizce yutuluyor.
  if ! url="$(python3 "$PINNED" url "$key")"; then
    echo "HATA: '$key' sabitlenmiş kütükten okunamadı ($PINNED)." >&2
    return 1
  fi
  local tmp; tmp="$(mktemp -d)"
  echo "uv indiriliyor ($out_subdir): $url"
  curl -fsSL "$url" -o "$tmp/uv.tar.gz"
  # Bütünlük kapısı ÇIKARMADAN ÖNCE ve İNDİRİLEN ARŞİV üzerinde: çıkarılmış dosyaya
  # bakmak, bozuk arşivi zaten açtıktan sonra kontrol etmek olurdu.
  # Uyuşmazlıkta build KIRILIR, atlanmaz: uv olmadan Unity MCP hiç çalışmıyor, yani
  # "uyarı verip devam et" son kullanıcıya sessizce bozuk bir installer göndermektir.
  if ! python3 "$PINNED" verify "$key" "$tmp/uv.tar.gz"; then
    rm -rf "$tmp"
    echo "HATA: $key bütünlük doğrulaması başarısız — build durduruldu." >&2
    return 1
  fi
  tar -xzf "$tmp/uv.tar.gz" -C "$tmp"
  local extracted="$tmp/uv-${uv_triple}"
  local target="$DEST/$out_subdir"
  rm -rf "$target"; mkdir -p "$target"
  cp "$extracted/uv" "$extracted/uvx" "$target/"
  chmod +x "$target/uv" "$target/uvx"
  rm -rf "$tmp"
  echo "Tamam → $target"
  ls -lh "$target"
}

fetch_arch "aarch64-apple-darwin" "darwin-arm64" "uv/darwin-arm64"
fetch_arch "x86_64-apple-darwin"  "darwin-x64"   "uv/darwin-x64"

echo ""
echo "=== uv araç zinciri hazır: $DEST ==="
