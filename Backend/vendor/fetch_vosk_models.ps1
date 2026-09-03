# Vosk speech models (TR + EN) → Backend/vendor/models/vosk/<upstream zip top-level dir>
#
# These are NOT embedded by backend.spec: they are data, not code, and PyInstaller
# would push them under _internal/. electron-builder ships them instead
# (extraResources: ../../Backend/vendor/models/vosk → resources/vosk), which is the
# path the frozen backend resolves as <exe dir>/../vosk. Keeping them out of the exe
# also keeps the PyInstaller archive ~130 MB smaller.
#
# PINNED: address and expected digest live in scripts/pinned_assets.json
# ('vosk-model/small-tr', 'vosk-model/small-en-us'); no address here is 'latest'.
# Verification happens on the DOWNLOADED archive, BEFORE extraction — the digest of an
# extracted tree cannot be compared with the ledger value, and a hostile archive has
# already done its work by the time it is unpacked.
#
# BEST EFFORT, DELIBERATE: a model that cannot be fetched does not break the build; the
# app starts without it and /transcribe answers 503 stt_model_missing for that language.
# A verification failure takes the SAME road: nothing is installed, the build still runs.
# Same reasoning as fetch_video_bins.ps1 — shipping an unverified model is worse than
# shipping no model. Unlike fetch_uv.ps1, where the same failure MUST break the build.
#
# Usage: pwsh Backend/vendor/fetch_vosk_models.ps1
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$root = Join-Path $PSScriptRoot 'models\vosk'
New-Item -ItemType Directory -Force -Path $root | Out-Null
$script:PinnedCli = Join-Path $PSScriptRoot '..\..\scripts\pinned_assets.py'

# Dir = the zip's own top-level directory name; it IS the pinned identity and the
# resolver (app/providers/stt_vosk.py) looks the model up by exactly this name.
# Marker = where final.mdl sits inside that tree. TR 0.3 is FLAT, EN 0.15 has am/.
# Both are needed: "the directory exists" is not evidence that extraction finished.
$models = @(
    [pscustomobject]@{ Key = 'vosk-model/small-tr';    Dir = 'vosk-model-small-tr-0.3';     Marker = 'final.mdl' },
    [pscustomobject]@{ Key = 'vosk-model/small-en-us'; Dir = 'vosk-model-small-en-us-0.15'; Marker = 'am\final.mdl' }
)

function Invoke-PinnedCli {
    # Calls the ledger CLI and hands back its exit code and output.
    # $ErrorActionPreference is pulled to 'Continue' in FUNCTION SCOPE: the file-level
    # 'Stop' would kill the whole script when python returns non-zero (PS 7.4+ defaults
    # $PSNativeCommandUseErrorActionPreference to $true). The wanted behaviour is "skip
    # that model, continue with the next", so the exit code is read by hand.
    param([string[]]$CliArgs)
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    $out = & python $script:PinnedCli @CliArgs 2>&1
    return [pscustomobject]@{
        Code   = $LASTEXITCODE
        Output = ($out | Out-String).Trim()
    }
}

# ── Exit code CLASSES of the ledger CLI ───────────────────────────────
# The contract is written in scripts/pinned_assets.py's docstring and that is its
# only source:
#   0 = ok
#   1 = INTEGRITY failure - downloaded bytes do not match the pin. NEVER retried.
#   2 = usage / ENVIRONMENT error - wrong argument, unsupported Python version.
#   3 = OPERATIONAL failure - key absent from the ledger, file unreadable, ledger broken.
#
# Separating the classes is MANDATORY. Collapsing them to "non-zero -> key missing"
# was measured as a real misdiagnosis in this repo (2026-07-28): a run stopped by the
# Python version gate (code 2) told the operator "this key is not in the ledger",
# sending them after a ledger problem that did not exist.
#
# No class breaks the build here: the contract is best effort. But the message differs
# per class, because the operator's next action differs.
$script:PinnedFailLabel = ''

function Write-PinnedFailure {
    # Reports the class; NEVER throws (best-effort contract). Python's own output
    # ($Detail) is not swallowed: the real diagnosis is in there.
    param([int]$Code, [string]$Key, [string]$Stage, [string]$Detail)
    switch ($Code) {
        1 {
            $script:PinnedFailLabel = 'integrity mismatch'
            Write-Warning ("$Key NOT VERIFIED ($Stage) - the download succeeded but the " +
                "bytes do not match the pinned digest. NOT installed and NOT retried: " +
                "'try a few times' only hands an attacker a few more chances.")
        }
        2 {
            $script:PinnedFailLabel = 'environment error'
            Write-Warning ("$Key ENVIRONMENT ERROR ($Stage) - the Python version or the " +
                "call shape is wrong. This is NOT an integrity failure: no asset was " +
                "verified and no digest mismatch was found. Python 3.10+ is required.")
        }
        3 {
            $script:PinnedFailLabel = 'operational error'
            Write-Warning ("$Key OPERATIONAL ERROR ($Stage) - key absent from the ledger, " +
                "file unreadable, or the ledger could not be parsed. Fixable, and " +
                "UNRELATED to integrity. ('typo' and 'not added to the ledger yet' look " +
                "identical from outside; both must stay visible.)")
        }
        default {
            $script:PinnedFailLabel = "unexpected exit code $Code"
            Write-Warning ("$Key - UNEXPECTED EXIT CODE $Code ($Stage). The contract only " +
                "defines 0/1/2/3; an unknown code means the contract changed. It is NOT " +
                "forced into a known class: misclassifying costs more than not classifying.")
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($Detail)) { Write-Host $Detail }
}

$missing = @()

function Add-Missing {
    # Writes the report AND removes any half-extracted tree at the target. Both in ONE
    # function on purpose: kept apart they drift, and the drift is exactly the failure
    # measured on the video-bins script (summary said "MISSING" while the directory
    # listing showed the file).
    #
    # Why removal matters here: electron-builder copies whatever is under
    # models/vosk/**; a partially extracted model directory would be shipped and the
    # backend would load a truncated model instead of answering 503.
    param([string]$Label, [string]$Target)
    $script:missing += $Label
    if (Test-Path $Target) {
        Remove-Item $Target -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $Target) {
            Write-Warning "leftover copy COULD NOT be removed: $Target - it may be packaged unverified"
        }
    }
}

# Fail-closed: if we cannot verify, we do not download at all. Downloading without
# verification is precisely the risk this script exists to close.
#
# In these two branches existing files are LEFT ALONE, and the distinction is
# deliberate: a verification failure is EVIDENCE (the bytes we hold do not match the
# pin), whereas a missing python is the ABSENCE of evidence. What sits in the directory
# came from an earlier run of this script and passed verification that day; deleting it
# today would turn a temporary environment gap into the destruction of a good artifact.
# The debt paid in return is honesty: "not verified today" is said out loud.
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Warning 'python is missing - integrity cannot be verified, NO model is installed'
    Write-Warning "(anything already in $root STAYS and was NOT verified in this run)"
    exit 0
}
if (-not (Test-Path $script:PinnedCli)) {
    Write-Warning "verification tool not found ($($script:PinnedCli)) - NO model is installed"
    Write-Warning "(anything already in $root STAYS and was NOT verified in this run)"
    exit 0
}

# ENVIRONMENT gate (exit code 2), BEFORE any download and in ONE place.
# Code 2 ("this interpreter cannot run the module") is key-independent, so it would
# repeat verbatim for every model - printing the same warning twice pushes the operator
# to believe there are two separate faults. `keys` is used because it touches no network
# and the version gate already fires at module IMPORT time.
$pre = Invoke-PinnedCli @('keys')
if ($pre.Code -eq 2) {
    Write-Warning 'ENVIRONMENT ERROR - python cannot run the ledger tool (exit code 2).'
    Write-Warning 'This is NOT an integrity failure; no asset was verified.'
    Write-Warning "NO model is installed, the target directory is LEFT ALONE."
    Write-Host $pre.Output
    exit 0
}

$tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("vosk_models_" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
try {
    foreach ($m in $models) {
        $target = Join-Path $root $m.Dir
        $marker = Join-Path $target $m.Marker

        # Idempotence lives here as well as in the JS wrapper, because this script is
        # also run by hand and in CI where the wrapper is not involved. The marker is
        # final.mdl, not the directory: an interrupted extraction leaves a directory.
        if (Test-Path $marker) {
            Write-Host "$($m.Key): already present ($($m.Dir)) - skipped."
            continue
        }

        $script:PinnedFailLabel = ''
        $r = Invoke-PinnedCli @('url', $m.Key)
        if ($r.Code -ne 0) {
            Write-PinnedFailure -Code $r.Code -Key $m.Key -Stage 'address lookup' -Detail $r.Output
            Add-Missing "$($m.Dir) ($script:PinnedFailLabel)" $target
            continue
        }
        $url = $r.Output
        $zip = Join-Path $tmpDir ($m.Dir + '.zip')
        Write-Host "$($m.Key) downloading: $url"
        try {
            Invoke-WebRequest -Uri $url -OutFile $zip
        } catch {
            Write-Warning "$($m.Key) DOWNLOAD FAILED (network/HTTP) - skipping: $($_.Exception.Message)"
            Remove-Item $zip -Force -ErrorAction SilentlyContinue
            Add-Missing "$($m.Dir) (network/HTTP)" $target
            continue
        }

        # BEFORE extraction. See the header: an extracted tree cannot be compared with
        # the ledger, and unpacking a hostile archive is itself the damage.
        $v = Invoke-PinnedCli @('verify', $m.Key, $zip)
        if ($v.Code -ne 0) {
            Write-PinnedFailure -Code $v.Code -Key $m.Key -Stage 'integrity check' -Detail $v.Output
            Remove-Item $zip -Force -ErrorAction SilentlyContinue
            Add-Missing "$($m.Dir) ($script:PinnedFailLabel)" $target
            continue
        }

        # Extracted into a scratch dir first, then moved: a half-written tree must never
        # sit under models/vosk even for a moment, because electron-builder packages
        # whatever it finds there.
        $ext = Join-Path $tmpDir ($m.Dir + '_ext')
        try {
            Expand-Archive -Path $zip -DestinationPath $ext -Force
            $src = Join-Path $ext $m.Dir
            if (-not (Test-Path (Join-Path $src $m.Marker))) {
                Write-Warning "$($m.Key): $($m.Dir)\$($m.Marker) not found in the archive - skipping"
                Add-Missing "$($m.Dir) (archive layout)" $target
                continue
            }
            if (Test-Path $target) { Remove-Item $target -Recurse -Force }
            Move-Item $src $target
            Write-Host "$($m.Key): extracted → $target"
        } catch {
            Write-Warning "$($m.Key) could not be extracted/moved - skipping: $($_.Exception.Message)"
            Add-Missing "$($m.Dir) (extraction)" $target
        } finally {
            # The archive is ~40 MB and has no further use once verified and extracted.
            Remove-Item $zip -Force -ErrorAction SilentlyContinue
            Remove-Item $ext -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
} finally {
    # Cleanup is mandatory and in finally: however the script ends, no temp dir is left.
    Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Done ($root):"
# Write-Host, not a formatted pipeline: `Select-Object` with a calculated property
# emitted NOTHING when this script ran under `powershell -File` (measured 3 Sep 2026),
# so the summary was silently empty while both models were in fact installed. An empty
# summary is the same failure class this file guards against elsewhere - the report and
# the directory disagreeing.
foreach ($d in (Get-ChildItem $root -Directory)) {
    $f = Get-ChildItem $d.FullName -Recurse -File
    Write-Host ("  {0}  {1} files  {2:N1} MB" -f $d.Name, $f.Count,
        (($f | Measure-Object Length -Sum).Sum / 1MB))
}

if ($missing.Count -gt 0) {
    Write-Host ''
    Write-Host '!!! MISSING MODELS - the package will be built without them:'
    $missing | ForEach-Object { Write-Host "  - $_" }
    Write-Host '    /transcribe answers 503 stt_model_missing for those languages.'
    Write-Host '    The reason is in parentheses and in the WARNING lines above. The classes differ:'
    Write-Host '      network/HTTP       -> the address did not answer; retryable.'
    Write-Host '      integrity mismatch -> bytes do not match the pin; NEVER retried.'
    Write-Host '      environment error  -> Python version/call shape; no byte was verified.'
    Write-Host '      operational error  -> key/file/ledger problem; fixable.'
}

# Zero is returned even when models are missing: this step's contract is "collect what
# you can, report the rest loudly". The decision to break belongs to the build, not here.
exit 0
