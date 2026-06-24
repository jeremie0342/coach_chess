# Build a standalone .exe for the coach_chess launcher, and (optionally)
# drop a shortcut on the desktop.
#
# Usage:
#   .\scripts\build_launcher.ps1            # build only
#   .\scripts\build_launcher.ps1 -Shortcut  # build + create desktop shortcut

param(
    [switch]$Shortcut
)

$ErrorActionPreference = "Stop"
$PROJECT = Split-Path -Parent $PSScriptRoot
$LAUNCHER = Join-Path $PROJECT "scripts\launcher.py"
$DIST = Join-Path $PROJECT "dist"

Write-Host "== Building coach_chess launcher.exe ==" -ForegroundColor Cyan

Push-Location $PROJECT
try {
    # Install PyInstaller into the project venv (one-time, idempotent)
    uv add --dev pyinstaller | Out-Null

    # Clean previous build
    if (Test-Path (Join-Path $PROJECT "build")) {
        Remove-Item -Recurse -Force (Join-Path $PROJECT "build")
    }
    if (Test-Path (Join-Path $DIST "coach_chess_launcher")) {
        Remove-Item -Recurse -Force (Join-Path $DIST "coach_chess_launcher")
    }
    if (Test-Path (Join-Path $DIST "coach_chess_launcher.exe")) {
        Remove-Item -Force (Join-Path $DIST "coach_chess_launcher.exe")
    }

    # --noconsole : no flashing console window (tk handles UI)
    # --onedir   : folder layout (FAR faster startup than --onefile, no temp
    #              extraction on every launch)
    # --name      : output name
    # --collect-all : ensure tray icon stack + win32 are fully bundled
    uv run pyinstaller `
        --noconfirm --clean --onedir --noconsole `
        --name "coach_chess_launcher" `
        --collect-all pystray `
        --collect-all PIL `
        --hidden-import win32com.client `
        --hidden-import pythoncom `
        $LAUNCHER

    $exe = Join-Path $DIST "coach_chess_launcher\coach_chess_launcher.exe"
    if (-not (Test-Path $exe)) {
        Write-Host "Build FAILED - exe not found at $exe" -ForegroundColor Red
        exit 1
    }
    Write-Host ""
    Write-Host "Built: $exe" -ForegroundColor Green

    if ($Shortcut) {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $lnk = Join-Path $desktop "coach_chess.lnk"
        $shell = New-Object -ComObject WScript.Shell
        $sc = $shell.CreateShortcut($lnk)
        $sc.TargetPath = $exe
        $sc.WorkingDirectory = $PROJECT
        $sc.IconLocation = $exe
        $sc.Description = "coach_chess local stack launcher"
        $sc.Save()
        Write-Host "Shortcut created: $lnk" -ForegroundColor Green
    }
}
finally {
    Pop-Location
}
