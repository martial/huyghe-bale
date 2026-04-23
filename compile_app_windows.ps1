# ========================================================================
#  PIERRE HUYGHE BALE - Windows App Builder
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
#    apps/PIERRE HUYGHE BALE/  - standalone folder with .exe
#
#  NOTE: No code signing - Windows SmartScreen may warn on first run.
# ========================================================================

$ErrorActionPreference = "Stop"

# --- 0. Resolve a usable Python ---
# On Windows, `python` in PATH often resolves to the Microsoft Store stub
# (C:\Users\<user>\AppData\Local\Microsoft\WindowsApps\python.exe) which does
# nothing. Detect that case and prepend a real install to PATH so the rest
# of the script can call `python` / `pip` directly.
function Resolve-RealPython {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Path -notlike "*\WindowsApps\*") {
        try {
            $v = & $cmd.Path --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $v -match "^Python 3\.(1[0-9]|[2-9][0-9])") {
                return $null  # already good, no PATH change needed
            }
        } catch {}
    }

    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312",
        "$env:LOCALAPPDATA\Programs\Python\Python311",
        "$env:LOCALAPPDATA\Programs\Python\Python310",
        "C:\Python312",
        "C:\Python311",
        "C:\Python310"
    )
    foreach ($dir in $candidates) {
        if (Test-Path (Join-Path $dir "python.exe")) {
            return $dir
        }
    }

    # Last resort: py launcher
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $dir = & $py.Path -c "import sys, os; print(os.path.dirname(sys.executable))" 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Path $dir)) { return $dir }
    }

    throw "No usable Python 3.10+ found. Install from https://www.python.org/downloads/ and re-run."
}

$PythonDir = Resolve-RealPython
if ($PythonDir) {
    Write-Host "Using Python at: $PythonDir"
    $env:PATH = "$PythonDir;$PythonDir\Scripts;$env:PATH"
}

# --- 0b. Require Node.js 18+ ---
# Node <18 silently fails to parse modern TS/Vite syntax (e.g. `??=`),
# but `npm run build` can still exit 0 and leave the previous dist/
# untouched — which then gets bundled into the .exe as a stale UI.
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    throw "Node.js is not installed. Install Node 18+ LTS from https://nodejs.org/"
}
$nodeVer = (& node --version).TrimStart('v')
$nodeMajor = [int]($nodeVer -split '\.')[0]
if ($nodeMajor -lt 18) {
    throw "Node $nodeVer is too old. Install Node 18+ LTS from https://nodejs.org/ and re-run."
}
Write-Host "Using Node: v$nodeVer"

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
pip install --quiet -r (Join-Path $BackendDir "requirements.txt") Pillow pywebview pyinstaller
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
$VersionJson = @"
{"hash": "$GitHash", "date": "$GitDate", "message": "$GitMsg"}
"@
# Write UTF-8 without BOM — Python's json.load() chokes on a BOM,
# and PS 5.1's `Out-File -Encoding utf8` emits one by default.
[System.IO.File]::WriteAllText($VersionFile, $VersionJson, (New-Object System.Text.UTF8Encoding $false))
Write-Host "  Version: $GitHash ($GitDate)"
Write-Host ""

# --- 4. Build frontend ---
Write-Host "=== Building frontend ==="
Push-Location $FrontendDir
npm run build
$npmExit = $LASTEXITCODE
Pop-Location
if ($npmExit -ne 0) {
    throw "npm run build failed (exit $npmExit). Aborting before we bundle a stale dist/."
}
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

# --- 8. Bundle WebView2 Evergreen bootstrapper + install helper ---
# pywebview renders with Edge WebView2; on a fresh Windows the runtime is
# missing and the app launches as a blank window. We ship a 1.7 MB
# bootstrapper and a one-shot install.bat so the on-site crew can prep
# the machine without manual downloads.
Write-Host "=== Bundling WebView2 installer ==="
$CacheDir = Join-Path $BuildDir "cache"
if (-not (Test-Path $CacheDir)) { New-Item -ItemType Directory -Path $CacheDir | Out-Null }
$Wv2Cache = Join-Path $CacheDir "MicrosoftEdgeWebview2Setup.exe"
if (-not (Test-Path $Wv2Cache)) {
    Write-Host "  downloading WebView2 bootstrapper..."
    Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $Wv2Cache -UseBasicParsing
}
Copy-Item $Wv2Cache (Join-Path $DestPath "MicrosoftEdgeWebview2Setup.exe")

$InstallBat = @'
@echo off
REM One-shot WebView2 Evergreen installer.
REM Run once on a fresh machine before launching "PIERRE HUYGHE BALE.exe".
echo Installing Microsoft Edge WebView2 Runtime...
"%~dp0MicrosoftEdgeWebview2Setup.exe" /silent /install
if errorlevel 1 (
    echo.
    echo WebView2 installer reported errorlevel %errorlevel%.
    echo If the runtime is already installed, this is harmless.
) else (
    echo Done.
)
echo.
echo You can now double-click "PIERRE HUYGHE BALE.exe".
pause
'@
[System.IO.File]::WriteAllText(
    (Join-Path $DestPath "install-webview2.bat"),
    $InstallBat,
    (New-Object System.Text.ASCIIEncoding)
)
Write-Host "  bundled MicrosoftEdgeWebview2Setup.exe + install-webview2.bat"

Write-Host ""
Write-Host "========================================"
Write-Host "  Build complete!"
Write-Host "========================================"
Write-Host ""
Write-Host "  App folder: $DestPath"
Write-Host "  Executable: $DestPath\$AppName.exe"
Write-Host ""
Write-Host "  Not signed - Windows SmartScreen may warn on first run."
Write-Host "  On a fresh PC, run install-webview2.bat once before first launch."
Write-Host "  Distribute the folder as-is or zip it."
Write-Host ""
