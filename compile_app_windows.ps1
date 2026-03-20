# ========================================================================
#  PIERRE HUYGHE BALE — Windows App Builder
#  Builds a standalone .exe folder using PyInstaller + pywebview + Flask
# ========================================================================
#
#  PREREQUISITES:
#    1. Python 3.10+ with pip
#    2. Node.js 18+ with npm
#    3. Git
#
#  USAGE:
#    powershell -ExecutionPolicy Bypass -File compile_app_windows.ps1
#
#  OUTPUT:
#    apps/PIERRE HUYGHE BALE/  — standalone folder with .exe
#
#  NOTE: No code signing — Windows SmartScreen may warn on first run.
# ========================================================================

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildDir = Join-Path $ScriptDir "admin\build"
$BackendDir = Join-Path $ScriptDir "admin\backend"
$FrontendDir = Join-Path $ScriptDir "admin\frontend"
$IconPng = Join-Path $BuildDir "icon_1024.png"
$IconIco = Join-Path $BuildDir "app_icon.ico"
$AppName = "PIERRE HUYGHE BALE"
$AppsDir = Join-Path $ScriptDir "apps"

Write-Host "========================================"
Write-Host "  PIERRE HUYGHE BALE - Windows Builder"
Write-Host "========================================"
Write-Host ""

# --- 1. Install build dependencies ---
Write-Host "=== Installing build dependencies ==="
pip install --quiet Pillow pywebview pyinstaller
Write-Host ""

# --- 2. Generate icon ---
if (-not (Test-Path $IconIco)) {
    Write-Host "=== Generating app icon ==="

    python (Join-Path $BuildDir "generate_icon.py") $IconPng --ico $IconIco

    Write-Host "Icon: $IconIco"
    Write-Host ""
} else {
    Write-Host "=== Using cached icon: $IconIco ==="
    Write-Host ""
}

# --- 3. Generate VERSION file from current git state ---
Write-Host "=== Generating VERSION file ==="
$VersionFile = Join-Path $BackendDir "VERSION"
$GitHash = git -C $ScriptDir rev-parse --short HEAD
$GitDate = git -C $ScriptDir log -1 --format=%ci
$GitMsg = git -C $ScriptDir log -1 --format=%s
@"
{"hash": "$GitHash", "date": "$GitDate", "message": "$GitMsg"}
"@ | Out-File -FilePath $VersionFile -Encoding utf8
Write-Host "  Version: $GitHash ($GitDate)"
Write-Host ""

# --- 4. Build frontend ---
Write-Host "=== Building frontend ==="
Push-Location $FrontendDir
npm run build
Pop-Location
Write-Host ""

# --- 5. Delete stale .spec file (it overrides CLI flags) ---
$SpecFile = Join-Path $BackendDir "$AppName.spec"
if (Test-Path $SpecFile) {
    Remove-Item $SpecFile
}

# --- 6. Build Windows .exe with PyInstaller ---
Write-Host "=== Building Windows .exe ==="
Push-Location $BackendDir
pyinstaller `
    --name $AppName `
    --windowed `
    --noconfirm `
    --icon=$IconIco `
    --add-data "..\frontend\dist;frontend\dist" `
    --add-data "VERSION;." `
    launcher.py
Pop-Location
Write-Host ""

# Clean up generated VERSION file
Remove-Item -Path $VersionFile -ErrorAction SilentlyContinue

# --- 7. Copy output to apps/ ---
Write-Host "=== Copying app to apps/ ==="
if (-not (Test-Path $AppsDir)) {
    New-Item -ItemType Directory -Path $AppsDir | Out-Null
}

$DestPath = Join-Path $AppsDir $AppName
if (Test-Path $DestPath) {
    Remove-Item -Recurse -Force $DestPath
}
Copy-Item -Recurse (Join-Path $BackendDir "dist\$AppName") $DestPath

Write-Host ""
Write-Host "========================================"
Write-Host "  Build complete!"
Write-Host "========================================"
Write-Host ""
Write-Host "  App folder: $DestPath"
Write-Host "  Executable: $DestPath\$AppName.exe"
Write-Host ""
Write-Host "  Not signed — Windows SmartScreen may warn on first run."
Write-Host "  Distribute the folder as-is or zip it."
Write-Host ""
