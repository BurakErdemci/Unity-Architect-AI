#!/usr/bin/env bash
# Vosk speech models (TR + EN) → Backend/vendor/models/vosk/<upstream zip top-level dir>
# Windows counterpart: fetch_vosk_models.ps1. The models are platform-independent, so
# unlike the video binaries there is no per-OS subdirectory.
#
# These are NOT embedded by backend.spec: they are data, not code, and PyInstaller would
# push them under _internal/. electron-builder ships them instead
# (extraResources: ../../Backend/vendor/models/vosk → resources/vosk), which is the path
# the frozen backend resolves as <exe dir>/../vosk.
#
# PINNED: address and expected digest live in scripts/pinned_assets.json
# ('vosk-model/small-tr', 'vosk-model/small-en-us'). Verification runs on the DOWNLOADED
# archive BEFORE extraction — the digest of an extracted tree cannot be compared with the
# ledger value, and a hostile archive has already done its work once unpacked.
#
# BEST EFFORT, DELIBERATE: a model that cannot be fetched does not break the build; the
# app starts without it and /transcribe answers 503 stt_model_missing for that language.
# That is why there is no `set -e` here: the script must run to the end and report
# everything that stayed missing in one place.
#
# Usage: bash Backend/vendor/fetch_vosk_models.sh
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$here/../.." && pwd)"
pinned="$repo_root/scripts/pinned_assets.py"
root="$here/models/vosk"
mkdir -p "$root"

# key | zip top-level directory | path of final.mdl inside it.
# The directory name IS the pinned identity: app/providers/stt_vosk.py looks the model up
# by exactly this name. TR 0.3 is FLAT, EN 0.15 keeps final.mdl under am/. The marker is
# needed because "the directory exists" is not evidence that extraction finished.
MODELS="
vosk-model/small-tr|vosk-model-small-tr-0.3|final.mdl
vosk-model/small-en-us|vosk-model-small-en-us-0.15|am/final.mdl
"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

missing=""

# note_missing <report-label> <target-dir>
# Writes the report AND removes any half-extracted tree at the target. Both in ONE
# function on purpose: kept apart they drift, and that drift is the failure measured on
# the video-bins script (the summary said MISSING while the listing showed the file).
# Removal matters because electron-builder packages whatever it finds under models/vosk.
note_missing() {
  missing="${missing}  - $1"$'\n'
  if [ -e "$2" ] && ! rm -rf "$2"; then
    echo "WARNING: leftover copy COULD NOT be removed: $2 — it may be packaged unverified"
  fi
}

# Fail-closed: if we cannot verify, we do not download at all.
# In these two branches existing files are LEFT ALONE, deliberately: a verification
# failure is EVIDENCE (our bytes do not match the pin), a missing python3 is the ABSENCE
# of evidence. What sits in the directory passed verification on an earlier run; deleting
# it today would turn a temporary environment gap into the destruction of a good
# artifact. The debt paid in return is honesty: "not verified today" is said out loud.
if ! command -v python3 >/dev/null 2>&1; then
  echo "WARNING: python3 is missing — integrity cannot be verified, NO model is installed"
  echo "         (anything already in $root STAYS and was NOT verified in this run)"
  exit 0
fi
if [ ! -f "$pinned" ]; then
  echo "WARNING: verification tool not found ($pinned) — NO model is installed"
  echo "         (anything already in $root STAYS and was NOT verified in this run)"
  exit 0
fi

# ── Exit code CLASSES of the ledger CLI ───────────────────────────────
# The contract is written in scripts/pinned_assets.py's docstring and that is its only
# source:
#   0 = ok
#   1 = INTEGRITY failure — downloaded bytes do not match the pin. NEVER retried.
#   2 = usage / ENVIRONMENT error — wrong argument, unsupported Python version.
#   3 = OPERATIONAL failure — key absent from the ledger, file unreadable, ledger broken.
#
# Separating the classes is MANDATORY. Collapsing them to "non-zero → key missing" was
# measured as a real misdiagnosis in this repo (2026-07-28): Python 3.9 fails at module
# import (code 2) and the script told the operator the key was not in the ledger.
pinned_fail_label=""

report_pinned_failure() {
  local rc="$1" key="$2" stage="$3"
  case "$rc" in
    1)
      pinned_fail_label="integrity mismatch"
      echo "WARNING: $key NOT VERIFIED ($stage) — the download succeeded but the bytes do"
      echo "         not match the pinned digest. NOT installed and NOT retried: 'try a"
      echo "         few times' only hands an attacker a few more chances."
      ;;
    2)
      pinned_fail_label="environment error"
      echo "WARNING: $key ENVIRONMENT ERROR ($stage) — Python version or call shape is wrong."
      echo "         This is NOT an integrity failure: no asset was verified and no digest"
      echo "         mismatch was found (stock macOS python3 3.9.6 is not enough; 3.10+)."
      ;;
    3)
      pinned_fail_label="operational error"
      echo "WARNING: $key OPERATIONAL ERROR ($stage) — key absent from the ledger, file"
      echo "         unreadable, or the ledger could not be parsed ($pinned). Fixable, and"
      echo "         UNRELATED to integrity. ('typo' and 'not added yet' look identical.)"
      ;;
    *)
      pinned_fail_label="unexpected exit code $rc"
      echo "WARNING: $key — UNEXPECTED EXIT CODE $rc ($stage)."
      echo "         $pinned only defines 0/1/2/3; an unknown code means the contract"
      echo "         changed. It is NOT forced into a known class: misclassifying costs"
      echo "         more than not classifying."
      ;;
  esac
}

# ENVIRONMENT gate (exit code 2), BEFORE any download and in ONE place: code 2 is
# key-independent and would repeat verbatim per model, which reads as several faults.
# `keys` is used because it touches no network and the version gate fires at import.
python3 "$pinned" keys >/dev/null; preflight_rc=$?
if [ "$preflight_rc" -eq 2 ]; then
  echo "WARNING: ENVIRONMENT ERROR — python3 cannot run the ledger tool (exit code 2)."
  echo "         This is NOT an integrity failure; no asset was verified."
  echo "         NO model is installed, the target directory is LEFT ALONE."
  exit 0
fi

# --retry is for NETWORK errors only. A digest mismatch is NEVER retried
# (see pinned_assets.IntegrityError).
download_once() { curl -fL --retry 3 --retry-delay 2 -o "$2" "$1"; }

for row in $MODELS; do
  key="${row%%|*}"
  rest="${row#*|}"
  dir="${rest%%|*}"
  marker="${rest#*|}"
  target="$root/$dir"

  # Idempotence lives here as well as in the JS wrapper, because this script is also run
  # by hand and in CI where the wrapper is not involved. The marker is final.mdl, not the
  # directory: an interrupted extraction leaves a directory behind.
  if [ -f "$target/$marker" ]; then
    echo "$key: already present ($dir) — skipped."
    continue
  fi

  pinned_fail_label=""
  url="$(python3 "$pinned" url "$key")"; rc=$?
  if [ "$rc" -ne 0 ]; then
    report_pinned_failure "$rc" "$key" "address lookup"
    note_missing "$dir ($pinned_fail_label)" "$target"
    continue
  fi

  zip="$tmp/$dir.zip"
  echo "$key downloading: $url"
  if ! download_once "$url" "$zip"; then
    echo "WARNING: $key DOWNLOAD FAILED (network/HTTP) — skipping"
    rm -f "$zip"
    note_missing "$dir (network/HTTP)" "$target"
    continue
  fi

  # BEFORE extraction. See the header for why.
  python3 "$pinned" verify "$key" "$zip"; rc=$?
  if [ "$rc" -ne 0 ]; then
    report_pinned_failure "$rc" "$key" "integrity check"
    rm -f "$zip"
    note_missing "$dir ($pinned_fail_label)" "$target"
    continue
  fi

  # Extracted into a scratch dir first, then moved: a half-written tree must never sit
  # under models/vosk even for a moment, because electron-builder packages what it finds.
  ext="$tmp/${dir}_ext"
  if ! (mkdir -p "$ext" && unzip -o -q "$zip" -d "$ext"); then
    echo "WARNING: $key could not be extracted — skipping"
    rm -f "$zip"; rm -rf "$ext"
    note_missing "$dir (extraction)" "$target"
    continue
  fi
  # The archive is ~40 MB and has no further use once verified and extracted.
  rm -f "$zip"
  if [ ! -f "$ext/$dir/$marker" ]; then
    echo "WARNING: $key: $dir/$marker not found in the archive — skipping"
    rm -rf "$ext"
    note_missing "$dir (archive layout)" "$target"
    continue
  fi
  rm -rf "$target"
  if ! mv "$ext/$dir" "$target"; then
    echo "WARNING: $key could not be moved into place — skipping"
    rm -rf "$ext"
    note_missing "$dir (move)" "$target"
    continue
  fi
  rm -rf "$ext"
  echo "$key: extracted → $target"
done

echo "Done ($root):"; du -sh "$root"/* 2>/dev/null || true

if [ -n "$missing" ]; then
  echo ""
  echo "!!! MISSING MODELS — the package will be built without them:"
  printf '%s' "$missing"
  echo "    /transcribe answers 503 stt_model_missing for those languages."
  echo "    The reason is in parentheses and in the WARNING lines above. The classes differ:"
  echo "      network/HTTP       → the address did not answer; retryable."
  echo "      integrity mismatch → bytes do not match the pin; NEVER retried."
  echo "      environment error  → Python version/call shape; no byte was verified."
  echo "      operational error  → key/file/ledger problem; fixable."
fi

# Zero is returned even when models are missing: this step's contract is "collect what you
# can, report the rest loudly". The decision to break belongs to the build, not here.
exit 0
