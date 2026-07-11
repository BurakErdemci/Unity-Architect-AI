#!/usr/bin/env bash
# Video araç zinciri (ffmpeg + yt-dlp) — mac/linux için Backend/vendor/bin/<os>/ altına indirir.
# Statik binary'ler seçilir (PyInstaller'a temiz gömülür). Windows için: fetch_video_bins.ps1.
# EN İYİ ÇABA: bir indirme başarısız olursa build kırılmasın diye hatalar yutulur (spec yoksa atlar).
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
case "$(uname -s)" in
  Darwin) os="mac" ;;
  Linux)  os="linux" ;;
  *) echo "desteklenmeyen OS: $(uname -s)"; exit 0 ;;
esac
dir="$here/bin/$os"
mkdir -p "$dir"

# ── yt-dlp (tek dosya) ────────────────────────────────────────────────
if [ "$os" = "mac" ]; then yt="yt-dlp_macos"; else yt="yt-dlp_linux"; fi
echo "yt-dlp indiriliyor ($yt)..."
if curl -fL "https://github.com/yt-dlp/yt-dlp/releases/latest/download/$yt" -o "$dir/yt-dlp"; then
  chmod +x "$dir/yt-dlp"
else
  echo "UYARI: yt-dlp indirilemedi (atlanıyor)"
fi

# ── ffmpeg (statik) ───────────────────────────────────────────────────
echo "ffmpeg indiriliyor..."
tmp="$(mktemp -d)"
if [ "$os" = "mac" ]; then
  # evermeet.cx statik ffmpeg (Intel; Apple Silicon'da Rosetta 2 ile çalışır — runner'da mevcut)
  if curl -fL "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip" -o "$tmp/ffmpeg.zip"; then
    unzip -o -q "$tmp/ffmpeg.zip" -d "$tmp" && cp "$tmp/ffmpeg" "$dir/ffmpeg" && chmod +x "$dir/ffmpeg"
  else
    echo "UYARI: ffmpeg (mac) indirilemedi (atlanıyor)"
  fi
else
  # linux statik (johnvansickle)
  if curl -fL "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" -o "$tmp/ff.tar.xz"; then
    tar -xf "$tmp/ff.tar.xz" -C "$tmp"
    f="$(find "$tmp" -name ffmpeg -type f | head -1)"
    [ -n "$f" ] && cp "$f" "$dir/ffmpeg" && chmod +x "$dir/ffmpeg"
  else
    echo "UYARI: ffmpeg (linux) indirilemedi (atlanıyor)"
  fi
fi
rm -rf "$tmp"

echo "Tamam ($dir):"; ls -la "$dir" 2>/dev/null || true
