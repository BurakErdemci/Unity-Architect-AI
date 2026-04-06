#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Repo hygiene check running in: $ROOT_DIR"

echo
echo "[1/4] Searching for cache/build artifacts..."
find . \( -name "__pycache__" -o -name "*.pyc" -o -name "*.pyo" -o -name "*.tsbuildinfo" \) \
  -not -path "./Backend/venv/*" \
  -not -path "./Frontend/frontend/node_modules/*"

echo
echo "[2/4] Searching for local databases..."
find . \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) \
  -not -path "./Backend/venv/*" \
  -not -path "./Frontend/frontend/node_modules/*"

echo
echo "[3/4] Searching for likely secret files..."
find . \( -name ".env" -o -name "*.env" \) \
  -not -path "./Backend/venv/*" \
  -not -path "./Frontend/frontend/node_modules/*"

echo
echo "[4/4] Grepping for likely secret markers..."
rg -n --hidden \
  --glob '!Backend/venv/**' \
  --glob '!Frontend/frontend/node_modules/**' \
  --glob '!.git/**' \
  '(api[_-]?key|access[_-]?token|secret[_-]?key|sk-[A-Za-z0-9_-]+)' \
  . || true

echo
echo "Repo hygiene check complete."
