$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "[1/2] Build do frontend (Vite)..."
Set-Location (Join-Path $root "frontend")
npm run build
if ($LASTEXITCODE -ne 0) { throw "Build do frontend falhou." }

Write-Host "[2/2] Empacotamento (PyInstaller)..."
Set-Location (Join-Path $root "backend")
if (-not (Get-ChildItem "vendor\ocr" -Filter *.onnx -File -ErrorAction SilentlyContinue)) {
    Write-Warning "Modelos de OCR ausentes (vendor\ocr). O aplicativo empacotado não conseguirá ler imagens. Rode scripts\get_ocr_models.ps1 para embutir."
}
if (-not (Test-Path "vendor\cnefe.sqlite")) {
    Write-Warning "Base do IBGE ausente (vendor\cnefe.sqlite). A validação de endereços cairá para o ViaCEP sozinho. Rode 'python tools\build_cnefe.py' para gerá-la."
}
& $python -m PyInstaller routrip.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

Write-Host ""
Write-Host "Executável gerado em: $root\backend\dist\Routrip\Routrip.exe"
