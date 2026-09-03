// @vitest-environment node
//
// Regression test for the `stale-artifact-not-reverified` finding class.
//
// Measured 3 Sep 2026: when the stamp could not vouch for the installed bytes,
// the wrapper called the platform fetcher anyway -- but the fetcher treats an
// existing `final.mdl` as "already installed" and returns without touching the
// tree. The wrapper then wrote a fresh stamp over the tampered bytes, so a tree
// nothing had verified was recorded as verified. The fix evicts the trees and
// the stamp BEFORE fetching.
//
// The fixture spawns a real child process (powershell on Windows), which is what
// makes this file slow; measured ~1.5 s per run on this machine. Faking the spawn
// would not exercise the marker-skip branch, which is the whole finding.

import { spawnSync } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

const REAL_SCRIPT = path.resolve(__dirname, '..', 'scripts', 'fetch-vosk-models.js')
const MODEL_DIRS = ['vosk-model-small-tr-0.3', 'vosk-model-small-en-us-0.15']

// Fake fetchers that reproduce the real ones' marker-skip branch: an existing
// `final.mdl` means "installed", so nothing is rewritten.
const FAKE_PS1 = `$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot 'models\\vosk'
New-Item -ItemType Directory -Force -Path $root | Out-Null
foreach ($dir in @(${MODEL_DIRS.map((d) => `'${d}'`).join(', ')})) {
    $target = Join-Path $root $dir
    if (Test-Path (Join-Path $target 'final.mdl')) { continue }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Set-Content -Path (Join-Path $target 'final.mdl') -Value 'clean-model' -NoNewline -Encoding ascii
    New-Item -ItemType Directory -Force -Path (Join-Path $target 'am') | Out-Null
    Set-Content -Path (Join-Path $target 'am\\final.mdl') -Value 'clean-model' -NoNewline -Encoding ascii
    Set-Content -Path (Join-Path $target 'README') -Value 'clean-readme' -NoNewline -Encoding ascii
}
exit 0
`

const FAKE_SH = `#!/usr/bin/env bash
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$here/models/vosk"
mkdir -p "$root"
for dir in ${MODEL_DIRS.join(' ')}; do
  target="$root/$dir"
  if [ -f "$target/final.mdl" ]; then continue; fi
  mkdir -p "$target"
  printf 'clean-model' > "$target/final.mdl"
  mkdir -p "$target/am"; printf 'clean-model' > "$target/am/final.mdl"
  printf 'clean-readme' > "$target/README"
done
exit 0
`

// Copied from the script under test on purpose: the assertion is that the stamp
// does not record the tampered tree, which only means anything if the digest is
// computed exactly the way the script computes it.
function treeDigest(dir: string): string {
  const h = crypto.createHash('sha256')
  const walk = (d: string, rel: string) => {
    for (const name of fs.readdirSync(d).sort()) {
      const p = path.join(d, name)
      const r = rel ? `${rel}/${name}` : name
      if (fs.statSync(p).isDirectory()) walk(p, r)
      else {
        h.update(r)
        h.update(fs.readFileSync(p))
      }
    }
  }
  walk(dir, '')
  return h.digest('hex')
}

let tmp: string | null = null

function makeFixture(): { root: string; script: string; modelsDir: string; stamp: string } {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vosk-stamp-'))
  tmp = root

  // The copy must sit at exactly this depth: the script derives `repoRoot` from
  // `__dirname` with three `..` hops.
  const scriptDir = path.join(root, 'Frontend', 'frontend', 'scripts')
  fs.mkdirSync(scriptDir, { recursive: true })
  const script = path.join(scriptDir, 'fetch-vosk-models.js')
  fs.copyFileSync(REAL_SCRIPT, script)

  fs.mkdirSync(path.join(root, 'scripts'), { recursive: true })
  fs.writeFileSync(
    path.join(root, 'scripts', 'pinned_assets.json'),
    JSON.stringify({
      assets: {
        'vosk-model/small-tr': { digest: 'sha256:aaa' },
        'vosk-model/small-en-us': { digest: 'sha256:bbb' },
      },
    }),
  )

  const vendor = path.join(root, 'Backend', 'vendor')
  fs.mkdirSync(vendor, { recursive: true })
  fs.writeFileSync(path.join(vendor, 'fetch_vosk_models.ps1'), FAKE_PS1)
  fs.writeFileSync(path.join(vendor, 'fetch_vosk_models.sh'), FAKE_SH, { mode: 0o755 })

  const modelsDir = path.join(vendor, 'models', 'vosk')
  return { root, script, modelsDir, stamp: path.join(modelsDir, '.fetched') }
}

function runWrapper(root: string, script: string) {
  const r = spawnSync(process.execPath, [script], { cwd: root, encoding: 'utf8' })
  expect(r.status).toBe(0)
  return `${r.stdout ?? ''}${r.stderr ?? ''}`
}

afterEach(() => {
  if (tmp) fs.rmSync(tmp, { recursive: true, force: true })
  tmp = null
})

describe('fetch-vosk-models stale stamp handling', () => {
  it('evicts a tree the stamp cannot vouch for instead of re-stamping it', () => {
    const { root, script, modelsDir, stamp } = makeFixture()

    runWrapper(root, script)
    for (const dir of MODEL_DIRS) expect(fs.existsSync(path.join(modelsDir, dir))).toBe(true)
    expect(fs.existsSync(stamp)).toBe(true)

    const tampered = path.join(modelsDir, MODEL_DIRS[0], 'README')
    fs.writeFileSync(tampered, 'TAMPERED-PAYLOAD')
    // final.mdl is left in place: that marker is exactly what let the fetcher skip.
    expect(fs.existsSync(path.join(modelsDir, MODEL_DIRS[0], 'final.mdl'))).toBe(true)
    const tamperedDigest = treeDigest(path.join(modelsDir, MODEL_DIRS[0]))

    runWrapper(root, script)

    expect(fs.readFileSync(tampered, 'utf8')).toBe('clean-readme')
    expect(fs.readFileSync(stamp, 'utf8')).not.toContain(tamperedDigest)
  })

  it('does not stamp when the fetcher fails after creating empty directories', () => {
    // Class: stale-artifact-not-reverified, second form (verification round,
    // 3 Sep 2026). The wrapper used to turn a failing fetcher into "success" and
    // stamp whatever directories existed; a later run then skipped the fetch
    // and the app shipped two empty model folders.
    const fx = makeFixture()
    runWrapper(fx.root, fx.script)
    expect(fs.existsSync(fx.stamp)).toBe(true)
    fs.writeFileSync(path.join(fx.modelsDir, MODEL_DIRS[0], 'README'), 'TAMPERED-PAYLOAD')
    const failingPs1 = `$root = Join-Path $PSScriptRoot 'models\\vosk'
foreach ($dir in @(${MODEL_DIRS.map((d) => `'${d}'`).join(', ')})) { New-Item -ItemType Directory -Force -Path (Join-Path $root $dir) | Out-Null }
exit 1
`
    const failingSh = `#!/usr/bin/env bash
here="$(cd "$(dirname "$0")" && pwd)"
for dir in ${MODEL_DIRS.join(' ')}; do mkdir -p "$here/models/vosk/$dir"; done
exit 1
`
    fs.writeFileSync(path.join(fx.root, 'Backend', 'vendor', 'fetch_vosk_models.ps1'), failingPs1)
    fs.writeFileSync(path.join(fx.root, 'Backend', 'vendor', 'fetch_vosk_models.sh'), failingSh)
    runWrapper(fx.root, fx.script)
    for (const dir of MODEL_DIRS) {
      expect(fs.existsSync(path.join(fx.modelsDir, dir, 'final.mdl'))).toBe(false)
    }
    expect(fs.existsSync(fx.stamp)).toBe(false)
  })

  it('skips entirely when the stamp matches the installed bytes', () => {
    const { root, script, modelsDir, stamp } = makeFixture()

    runWrapper(root, script)
    // No sentinel file is possible here: any file added to the tree changes the
    // digest and therefore invalidates the stamp being tested. mtimes are the
    // available evidence -- eviction plus refetch cannot preserve them.
    const watched = MODEL_DIRS.map((d) => path.join(modelsDir, d, 'final.mdl'))
    const before = watched.map((p) => fs.statSync(p).mtimeMs)

    const out = runWrapper(root, script)

    expect(out).toContain('already at the pinned version')
    expect(watched.map((p) => fs.statSync(p).mtimeMs)).toEqual(before)
    expect(fs.readFileSync(path.join(modelsDir, MODEL_DIRS[0], 'README'), 'utf8')).toBe(
      'clean-readme',
    )
    expect(fs.existsSync(stamp)).toBe(true)
  })
})
