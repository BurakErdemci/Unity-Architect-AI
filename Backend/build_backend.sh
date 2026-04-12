#!/bin/bash
# Unity Architect AI — Backend PyInstaller build scripti
# Kullanım: cd Backend && ./build_backend.sh
# Önce: pip install pyinstaller

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Backend build başlıyor ==="

# venv'den pyinstaller çalıştır
PYINSTALLER="venv/bin/pyinstaller"
if [[ ! -f "$PYINSTALLER" ]]; then
  echo "PyInstaller bulunamadı. Yükleniyor..."
  venv/bin/pip install pyinstaller
fi

# Eski build'i temizle
rm -rf dist/backend build/backend

echo "--- PyInstaller çalıştırılıyor ---"
"$PYINSTALLER" backend.spec

echo ""
echo "=== Build tamamlandı: dist/backend/ ==="
echo "Binary: dist/backend/backend"
