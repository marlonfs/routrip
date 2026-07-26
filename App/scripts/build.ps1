$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "[1/2] Build do frontend (Vite)..."
Set-Location (Join-Path $root "frontend")
npm run build
if ($LASTEXITCODE -ne 0) { throw "Build do frontend falhou." }

Write-Host "[2/2] Empacotamento (PyInstaller)..."
Set-Location (Join-Path $root "backend")
if (-not (Test-Path "vendor\tesseract\tesseract.exe")) {
    Write-Warning "Tesseract não vendorizado (vendor\tesseract). O exe exigirá Tesseract instalado na máquina. Rode scripts\get_tesseract.ps1 para embutir."
}
& $python -m PyInstaller routrip.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

Write-Host ""
Write-Host "Executável gerado em: $root\backend\dist\Routrip\Routrip.exe"
