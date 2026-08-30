# Starts the FILO Asset Sentinel backend (FastAPI :8000) and dashboard (Vite :5173)
# in two child PowerShell windows. Ctrl+C in each to stop.
#
#   pwsh scripts/dev.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPy = Join-Path $backend ".venv/Scripts/python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "Creating backend venv..." -ForegroundColor Cyan
    py -3 -m venv (Join-Path $backend ".venv")
    & $venvPy -m pip install -q -r (Join-Path $backend "requirements.txt")
}
if (-not (Test-Path (Join-Path $root ".env"))) {
    Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env")
    Write-Host "Created .env from .env.example" -ForegroundColor Yellow
}
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing frontend deps..." -ForegroundColor Cyan
    Push-Location $frontend; npm install; Pop-Location
}

Start-Process pwsh -ArgumentList "-NoExit", "-Command", "cd '$backend'; & '$venvPy' -m uvicorn app.main:app --reload --port 8000"
Start-Process pwsh -ArgumentList "-NoExit", "-Command", "cd '$frontend'; npm run dev"

Write-Host "`nBackend : http://127.0.0.1:8000/api/health" -ForegroundColor Green
Write-Host "Dashboard: http://127.0.0.1:5173" -ForegroundColor Green
