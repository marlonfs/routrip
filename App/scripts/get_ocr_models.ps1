<#
    Baixa os modelos de OCR (PP-OCR em ONNX) para backend\vendor\ocr.

    Quem baixa e confere o SHA256 é o próprio rapidocr, a partir do catálogo que ele
    mantém em default_models.yaml — aqui só instanciamos o motor uma vez apontando o
    diretório de destino. O aplicativo nunca baixa nada em tempo de execução.
#>
param(
    # "latin" (padrão): reconhecedor só de escrita latina, 7,5 MB.
    # "multi": reconhecedor multilíngue do PP-OCRv6, 20 MB. Ver PRESETS em services/ocr.py.
    [ValidateSet("latin", "multi")]
    [string]$Preset = "latin"
)

$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
$vendor = Join-Path $root "backend\vendor\ocr"
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Ambiente virtual não encontrado em $python. Rode antes: python -m venv .venv; .venv\Scripts\pip install -r backend\requirements.txt"
}

New-Item -ItemType Directory -Force -Path $vendor | Out-Null

Write-Host "Baixando os modelos de OCR (preset '$Preset') para $vendor ..."

$env:ROUTRIP_OCR_PRESET = $Preset
& $python -c @"
import sys
sys.path.insert(0, r'$root\backend')
from services import ocr
print('destino:', ocr.baixar_modelos())
"@
if ($LASTEXITCODE -ne 0) { throw "Falha ao baixar os modelos de OCR." }

$arquivos = Get-ChildItem $vendor -Filter *.onnx -File
if (-not $arquivos) { throw "Nenhum modelo .onnx foi gravado em $vendor." }

$size = [math]::Round(($arquivos | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host ""
Write-Host "Modelos em $vendor ($size MB):"
$arquivos | ForEach-Object { Write-Host ("  {0,-42} {1,6:N2} MB" -f $_.Name, ($_.Length / 1MB)) }
