#!/usr/bin/env node
/**
 * Calls the platform script that downloads the Vosk speech models into
 * `Backend/vendor/models/vosk/`.
 *
 * WHY IT EXISTS: exactly the lesson `fetch-video-bins.js` was written for. Fetch
 * scripts, a packaging rule and a .gitignore entry can all be in place while
 * NOTHING calls them — that is how `vendor/bin` shipped empty for a month. The
 * models are wired into `electron-builder.yml` (`extraResources`), so if this
 * step never runs the installer simply carries no models and every dictation
 * request answers 503 stt_model_missing.
 *
 * ⚠️ `pwsh` IS NOT ASSUMED. PowerShell 7 is not installed on Burak's Windows
 * machine (measured 30 Aug 2026: "pwsh is not recognized"), so `pwsh` is tried
 * first and Windows' own `powershell` second.
 *
 * BEST EFFORT, DELIBERATE: a failed download does NOT break the build. The
 * reasoning is written in the platform scripts' own headers and is not repeated
 * here; the only addition is refusing to be silent about what will be missing.
 */
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const crypto = require('node:crypto');

const repoRoot = path.resolve(__dirname, '..', '..', '..');
const vendorDir = path.join(repoRoot, 'Backend', 'vendor');
const MODELS_DIR = path.join(vendorDir, 'models', 'vosk');
const STAMP = path.join(MODELS_DIR, '.fetched');

// Ledger key → the zip's top-level directory name. The directory name is the
// pinned identity and `app/providers/stt_vosk.py` resolves models by it, so the
// two must not drift; a rename upstream shows up here as a re-download, not as a
// silently wrong model.
const MODELS = [
  ['vosk-model/small-tr', 'vosk-model-small-tr-0.3'],
  ['vosk-model/small-en-us', 'vosk-model-small-en-us-0.15'],
];

function run(cmd, args) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', cwd: repoRoot });
  return r.error ? null : r.status;
}

// The stamp is built from the PINNED DIGESTS, not from a version number: if a
// publisher republishes the same name the version would make stale bytes look
// current.
function expectedStamp() {
  try {
    const ledger = JSON.parse(
      fs.readFileSync(path.join(repoRoot, 'scripts', 'pinned_assets.json'), 'utf8'));
    return MODELS.map(([key]) => ledger.assets[key]?.digest || '?').join(' ');
  } catch {
    return null;   // ledger unreadable → no skip decision can be made → fetch
  }
}

// ── The stamp has TWO parts answering two different questions ───────────────
//
// Part one records WHICH pin was installed. Part two records the bytes that were
// actually installed, and it is there because of the audit finding on
// fetch-video-bins.js (30 Aug 2026): a stamp that only validates its own text
// lets a tampered payload sit next to a matching stamp, and the wrapper then
// skips the very script that would have verified it.
//
// The archive digest cannot be reused for the check: the ledger pins the ZIP,
// while what lands on disk is the extracted tree. So the stamp records the tree
// that DID pass verification and compares it against today's bytes. Cost on this
// tree (~130 MB, 27 files): a sha256 pass per build, well under a second on SSD.
function treeDigest(dir) {
  const h = crypto.createHash('sha256');
  const walk = (d, rel) => {
    for (const name of fs.readdirSync(d).sort()) {
      const p = path.join(d, name);
      const r = rel ? `${rel}/${name}` : name;
      if (fs.statSync(p).isDirectory()) walk(p, r);
      else { h.update(r); h.update(fs.readFileSync(p)); }
    }
  };
  walk(dir, '');
  return h.digest('hex');
}

function installedLines() {
  return MODELS.map(([, dir]) => `${dir} sha256:${treeDigest(path.join(MODELS_DIR, dir))}`);
}

function alreadyCurrent(stamp) {
  if (!stamp) return false;
  if (!MODELS.every(([, d]) => fs.existsSync(path.join(MODELS_DIR, d)))) return false;
  try {
    const lines = fs.readFileSync(STAMP, 'utf8').trim().split(/\r?\n/);
    if (lines[0].trim() !== stamp) return false;
    const recorded = lines.slice(1).map(s => s.trim()).filter(Boolean).sort();
    if (recorded.length !== MODELS.length) return false;   // old format → fetch
    const now = installedLines().sort();
    return recorded.every((s, i) => s === now[i]);
  } catch {
    return false;
  }
}

function writeStamp(stamp) {
  try {
    if (stamp) fs.writeFileSync(STAMP, [stamp, ...installedLines(), ''].join('\n'));
  } catch { /* an unwritable stamp only costs one extra fetch next build */ }
}

function fetchModels() {
  if (process.platform === 'win32') {
    const script = path.join(vendorDir, 'fetch_vosk_models.ps1');
    if (!fs.existsSync(script)) return warn(`not found: ${script}`);
    for (const shell of ['pwsh', 'powershell']) {
      const code = run(shell, ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script]);
      if (code === 0) return 0;
      if (code !== null) return warn(`${shell} exit code ${code}`);
      // code === null → shell absent, try the next one
    }
    return warn('neither pwsh nor powershell could be started');
  }

  const script = path.join(vendorDir, 'fetch_vosk_models.sh');
  if (!fs.existsSync(script)) return warn(`not found: ${script}`);
  const code = run('bash', [script]);
  if (code === 0) return 0;
  return warn(code === null ? 'bash could not be started' : `bash exit code ${code}`);
}

function warn(reason) {
  console.error(
    `[fetch-vosk-models] WARNING: the Vosk models could not be fetched (${reason}).\n` +
    '  The package will be built WITHOUT them; voice dictation answers 503\n' +
    '  stt_model_missing and the mic button reports the model as unavailable.'
  );
  return 0;
}

function main() {
  const stamp = expectedStamp();
  if (alreadyCurrent(stamp)) {
    console.log('[fetch-vosk-models] models already at the pinned version — skipped.');
    return 0;
  }
  const code = fetchModels();
  if (code === 0 && MODELS.every(([, d]) => fs.existsSync(path.join(MODELS_DIR, d)))) {
    writeStamp(stamp);
  }
  return code;
}

process.exit(main());
