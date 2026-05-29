<#
.SYNOPSIS
  Clones the Kaoto repository and builds the full Kaoto Online UI so that
  Flask can serve it as static assets. The user then gets the full Kaoto
  workspace (Camel route designer + DataMapper) in their browser.

.DESCRIPTION
  Phase 2 helper. Idempotent: re-running just rebuilds.

  Steps:
    1. Ensure Yarn is enabled via corepack.
    2. Clone https://github.com/KaotoIO/kaoto into ../.kaoto-src (if missing).
    3. yarn install (Kaoto monorepo).
    4. yarn workspace @kaoto/kaoto build  (full Vite app -> packages/ui/dist).

  After this script finishes, start the Flask server with:
      $env:FRONTEND_DIST = (Resolve-Path .kaoto-src/packages/ui/dist).Path
      python app.py

  Then open http://127.0.0.1:5000 — the full Kaoto UI loads. Create a Camel
  route, drop in a kaoto-datamapper step, and open the DataMapper. State is
  persisted by Kaoto in browser localStorage by default.

.PARAMETER Ref
  Git ref (branch / tag / sha) of Kaoto to check out. Default: main.

.EXAMPLE
  pwsh scripts/setup-kaoto.ps1
  pwsh scripts/setup-kaoto.ps1 -Ref 2.10.0
#>
[CmdletBinding()]
param(
  [string]$Ref = "main"
)

$ErrorActionPreference = "Stop"

$root     = Resolve-Path "$PSScriptRoot/.."
$kaotoSrc = Join-Path $root ".kaoto-src"

Write-Host "=== Verifying corepack (yarn) ==="
# Don't rely on `corepack enable` (needs admin on Windows). Invoke yarn
# via `corepack yarn` instead so no global shim is required.
$null = corepack yarn --version
function Invoke-Yarn { corepack yarn @args }

if (-not (Test-Path $kaotoSrc)) {
  Write-Host "=== Cloning Kaoto into $kaotoSrc ==="
  git clone --depth 1 --branch $Ref https://github.com/KaotoIO/kaoto $kaotoSrc
} else {
  Write-Host "=== Kaoto checkout already present at $kaotoSrc ==="
}

Write-Host "=== yarn install (this takes a while — 1800+ packages) ==="
Push-Location $kaotoSrc
Invoke-Yarn install

Write-Host "=== yarn workspace @kaoto/kaoto build (full Kaoto Online app) ==="
# Vite picks up VITE_* env vars at build time. Enabling the debugger flag
# replaces the "DataMapper cannot be configured in browser" placeholder
# with the real standalone DataMapperDebugger page at #/datamapper.
$env:VITE_ENABLE_DATAMAPPER_DEBUGGER = 'true'
# DataMapper-only mode: hide the left nav + other pages; index route
# renders the DataMapper debugger directly.
$env:VITE_DATAMAPPER_ONLY = 'true'
Invoke-Yarn workspace '@kaoto/kaoto' build
Pop-Location

$dist = Join-Path $kaotoSrc "packages/ui/dist"
Write-Host ""
Write-Host "Done. Built Kaoto Online at:" -ForegroundColor Green
Write-Host "  $dist" -ForegroundColor Green
Write-Host ""
Write-Host "Start the Flask server with:" -ForegroundColor Cyan
Write-Host "  `$env:FRONTEND_DIST = '$dist'"
Write-Host "  python app.py"
Write-Host ""
Write-Host "Then open http://127.0.0.1:5000" -ForegroundColor Cyan
