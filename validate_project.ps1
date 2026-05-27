$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    throw "Workspace virtual environment not found at .venv"
}

. .\.venv\Scripts\Activate.ps1

Write-Host "[1/3] Installing backend requirements into workspace venv..."
python -m pip install -r .\backend\requirements.txt

Write-Host "[2/3] Running backend test suite..."
Set-Location .\backend
python -m pytest
Set-Location $root

Write-Host "[3/3] Building frontend-next..."
Set-Location .\frontend-next
npm run build
Set-Location $root

Write-Host "Validation complete: backend and frontend checks passed."
