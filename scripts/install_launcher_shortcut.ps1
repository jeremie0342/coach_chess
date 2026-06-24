# Drop a desktop shortcut that launches scripts\launcher.py directly via
# pythonw (no .exe build, instant code reload).
#
# Usage:
#   .\scripts\install_launcher_shortcut.ps1

$ErrorActionPreference = "Stop"
$PROJECT = Split-Path -Parent $PSScriptRoot
$LAUNCHER = Join-Path $PROJECT "scripts\launcher.py"

# Find pythonw.exe — prefer the project's uv-managed venv, fall back to system.
$pythonw = $null
$candidates = @(
    (Join-Path $PROJECT ".venv\Scripts\pythonw.exe"),
    "C:\Python314\pythonw.exe",
    "C:\Python313\pythonw.exe",
    "C:\Python312\pythonw.exe"
)
foreach ($c in $candidates) {
    if (Test-Path $c) { $pythonw = $c; break }
}
if (-not $pythonw) {
    Write-Host "pythonw.exe not found. Tried: $($candidates -join ', ')" -ForegroundColor Red
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$lnk = Join-Path $desktop "coach_chess.lnk"

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath = $pythonw
$sc.Arguments = "`"$LAUNCHER`""
$sc.WorkingDirectory = $PROJECT
$sc.IconLocation = $pythonw
$sc.Description = "coach_chess local stack launcher"
$sc.Save()

Write-Host "Shortcut created: $lnk" -ForegroundColor Green
Write-Host "  Target: $pythonw $LAUNCHER" -ForegroundColor Gray
