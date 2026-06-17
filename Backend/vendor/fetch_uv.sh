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
# Kullanım:  bash Backend/vendor/fetch_uv.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$SCRIPT_DIR/uv"
mkdir -p "$DEST"

fetch_arch() {
  local uv_triple="$1"   # astral-sh/uv release asset triple
  local out_subdir="$2"  # vendor/uv/<out_subdir>
  local url="https://github.com/astral-sh/uv/releases/latest/download/uv-${uv_triple}.tar.gz"
  local tmp; tmp="$(mktemp -d)"
  echo "uv indiriliyor ($out_subdir): $url"
  curl -fsSL "$url" -o "$tmp/uv.tar.gz"
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

fetch_arch "aarch64-apple-darwin" "darwin-arm64"
fetch_arch "x86_64-apple-darwin"  "darwin-x64"

echo ""
echo "=== uv araç zinciri hazır: $DEST ==="
