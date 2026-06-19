# Launch the coach_chess stack: arq worker + FastAPI in separate windows.
# Run once: .\start.ps1
#
# Assumes Memurai (Redis-compat) is already running as a Windows service
# and that Ollama is set up as a Windows service or has been started manually.

$ErrorActionPreference = "Stop"
$PROJECT = "C:\Users\KPS\flemart\coach_chess"
$env:Path = "C:\Users\KPS\.local\bin;C:\Users\KPS\AppData\Local\Programs\Ollama;$env:Path"

Write-Host "== Pre-flight checks ==" -ForegroundColor Cyan

# 1. Memurai
$memurai = Get-Service -Name "Memurai" -ErrorAction SilentlyContinue
if ($memurai -and $memurai.Status -eq "Running") {
    Write-Host "  [OK]    Memurai service running on 6379"
} else {
    Write-Host "  [WARN]  Memurai service not running. Starting..."
    Start-Service Memurai -ErrorAction SilentlyContinue
}

# 2. Postgres
$pg = Test-NetConnection -ComputerName 127.0.0.1 -Port 5432 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($pg) { Write-Host "  [OK]    Postgres reachable on 5432" }
else { Write-Host "  [FAIL]  Postgres not reachable" -ForegroundColor Red; exit 1 }

# 3. Ollama
try {
    $r = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2
    Write-Host "  [OK]    Ollama responding ($($r.models.Count) models)"
} catch {
    Write-Host "  [WARN]  Ollama not responding. Starting..."
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "== Launching services ==" -ForegroundColor Cyan

# Worker in a new window
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "`$env:Path = 'C:\Users\KPS\.local\bin;'+`$env:Path; cd '$PROJECT'; Write-Host 'arq worker' -ForegroundColor Yellow; uv run arq app.worker.settings.WorkerSettings"
Write-Host "  Worker:   launched (separate window)"

# Sleep so worker registers cron jobs first
Start-Sleep -Seconds 2

# FastAPI in a new window
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "`$env:Path = 'C:\Users\KPS\.local\bin;'+`$env:Path; cd '$PROJECT'; Write-Host 'FastAPI on :8765' -ForegroundColor Yellow; uv run uvicorn app.main:app --host 127.0.0.1 --port 8765"
Write-Host "  FastAPI:  launched (separate window) on http://127.0.0.1:8765"
Write-Host "            docs at http://127.0.0.1:8765/docs"
Write-Host ""
Write-Host "Use uv run python scripts/coach_status.py to verify health." -ForegroundColor Green
