<#
.SYNOPSIS
  Detect upstream versions for every manifest in .\bucket and rewrite version/url/hash.

.DESCRIPTION
  Thin, opinionated wrapper around Scoop's own checkver.ps1 (the authoritative
  implementation): it reads each manifest's `checkver` block, compares against
  the upstream version, and when newer rewrites `version`, the autoupdate `url`
  and recomputes `hash`.

  Requires Scoop installed on the machine (checkver is part of Scoop itself).

.PARAMETER App
  Only check one manifest, e.g. nekoray (file bucket\nekoray.json).

.PARAMETER DryRun
  Report what would change, write nothing.

.PARAMETER Commit
  git add/commit the changed manifests.

.PARAMETER Push
  Implies -Commit, and pushes to origin.

.EXAMPLE
  pwsh -File scripts/update.ps1 -DryRun
.EXAMPLE
  pwsh -File scripts/update.ps1 -Commit -Push
#>
[CmdletBinding()]
param(
    [string] $App = '*',
    [switch] $DryRun,
    [switch] $Commit,
    [switch] $Push
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($Push) { $Commit = $true }

$repoRoot = Split-Path -Parent $PSScriptRoot
$bucketDir = Join-Path $repoRoot 'bucket'

if (-not (Test-Path -LiteralPath $bucketDir)) {
    throw "bucket directory not found: $bucketDir"
}

# --- locate Scoop's checkver -------------------------------------------------
$scoopRoot = $env:SCOOP
if (-not $scoopRoot) { $scoopRoot = Join-Path $env:USERPROFILE 'scoop' }

$checkver = Join-Path $scoopRoot 'apps\scoop\current\bin\checkver.ps1'
if (-not (Test-Path -LiteralPath $checkver)) {
    $cmd = Get-Command scoop -ErrorAction SilentlyContinue
    if ($cmd) {
        $scoopRoot = Split-Path -Parent (Split-Path -Parent $cmd.Source)
        $checkver = Join-Path $scoopRoot 'apps\scoop\current\bin\checkver.ps1'
    }
}
if (-not (Test-Path -LiteralPath $checkver)) {
    throw "checkver.ps1 not found. Install Scoop first: https://scoop.sh (looked in $scoopRoot)"
}

# --- snapshot for the change report -----------------------------------------
function Get-ManifestSnapshot {
    param([string] $Path)
    Get-ChildItem -LiteralPath $Path -Filter '*.json' -File |
        ForEach-Object {
            $json = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
            [pscustomobject]@{ App = $_.BaseName; Version = $json.version }
        }
}

$before = @{}
Get-ManifestSnapshot -Path $bucketDir | ForEach-Object { $before[$_.App] = $_.Version }

# --- run the real checkver ---------------------------------------------------
$checkverArgs = @(
    '-NoProfile', '-NoLogo',
    '-File', $checkver,
    '-App', $App,
    '-Dir', $bucketDir
)
if (-not $DryRun) { $checkverArgs += '-Update' }

Write-Host "» checkver -App $App -Dir $bucketDir $(if (-not $DryRun) { '-Update' })" -ForegroundColor DarkGray
& pwsh @checkverArgs
$exit = $LASTEXITCODE
if ($exit -ne 0) {
    throw "checkver failed with exit code $exit"
}

# --- report ------------------------------------------------------------------
$changed = @()
Get-ManifestSnapshot -Path $bucketDir | ForEach-Object {
    $old = $before[$_.App]
    if ($old -and $old -ne $_.Version) {
        $changed += "  {0}: {1} -> {2}" -f $_.App, $old, $_.Version
    }
}

if ($changed.Count -eq 0) {
    Write-Host "`nNo updates found." -ForegroundColor Green
    return
}

Write-Host "`nUpdated $($changed.Count) manifest(s):" -ForegroundColor Cyan
$changed | ForEach-Object { Write-Host $_ }

if ($DryRun) {
    Write-Host "`nDryRun: nothing written." -ForegroundColor Yellow
    return
}

# --- commit / push -----------------------------------------------------------
if ($Commit) {
    Push-Location $repoRoot
    try {
        git add -- bucket
        $stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm')
        $subject = if ($changed.Count -eq 1) {
            ($changed[0].Trim() -replace ': (\S+) -> ', ' -> ')
        } else {
            "Update $($changed.Count) app versions"
        }
        git commit -m "chore: $subject ($stamp UTC)" | Write-Host
        if ($Push) {
            git push origin HEAD
            if ($LASTEXITCODE -ne 0) { throw "git push failed" }
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "`nNot committed (pass -Commit / -Push to commit)." -ForegroundColor DarkGray
}
