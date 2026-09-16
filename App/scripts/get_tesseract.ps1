param(
    [string]$TesseractUrl = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe",
    [string]$TessdataBase = "https://github.com/tesseract-ocr/tessdata_fast/raw/main"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Get-File([string]$Url, [string]$OutFile) {
    & "$env:SystemRoot\System32\curl.exe" -fL --retry 5 --retry-delay 3 -sS -o $OutFile $Url
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $OutFile) -or (Get-Item $OutFile).Length -lt 1024) {
        throw "Falha ao baixar $Url"
    }
}

$root = Split-Path $PSScriptRoot -Parent
$vendor = Join-Path $root "backend\vendor\tesseract"
$tmp = Join-Path $env:TEMP "routrip_get_tesseract"

New-Item -ItemType Directory -Force -Path $tmp | Out-Null

Write-Host "[1/5] Baixando 7zr.exe (extrator standalone)..."
$sevenZr = Join-Path $tmp "7zr.exe"
Get-File "https://www.7-zip.org/a/7zr.exe" $sevenZr

Write-Host "[2/5] Baixando e extraindo 7-Zip completo (suporte a NSIS)..."
$sevenZipSfx = Join-Path $tmp "7zfull.exe"
Get-File "https://www.7-zip.org/a/7z2409-x64.exe" $sevenZipSfx
$sevenZipDir = Join-Path $tmp "7zip"
& $sevenZr x $sevenZipSfx "-o$sevenZipDir" -y | Out-Null
$sevenZ = Join-Path $sevenZipDir "7z.exe"
if (-not (Test-Path $sevenZ)) { throw "Falha ao extrair o 7-Zip." }

Write-Host "[3/5] Baixando o instalador do Tesseract (UB-Mannheim, ~55 MB)..."
$installer = Join-Path $tmp "tesseract-setup.exe"
Get-File $TesseractUrl $installer

Write-Host "[4/5] Extraindo o Tesseract (sem instalar)..."
$extractDir = Join-Path $tmp "tesseract"
if (Test-Path $extractDir) { Remove-Item $extractDir -Recurse -Force -Confirm:$false }
& $sevenZ x $installer "-o$extractDir" -y | Out-Null
if (-not (Test-Path (Join-Path $extractDir "tesseract.exe"))) {
    throw "tesseract.exe não encontrado no instalador extraído."
}

if (Test-Path $vendor) { Remove-Item $vendor -Recurse -Force -Confirm:$false }
New-Item -ItemType Directory -Force -Path $vendor | Out-Null
Get-ChildItem $extractDir | Where-Object { $_.Name -notlike '$*' -and $_.Name -ne "Uninstall.exe" } |
    Copy-Item -Destination $vendor -Recurse -Force

Get-ChildItem $vendor -File | Where-Object {
    ($_.Extension -eq ".exe" -and $_.Name -ne "tesseract.exe") -or $_.Extension -eq ".html"
} | Remove-Item -Force -Confirm:$false
Remove-Item (Join-Path $vendor "doc") -Recurse -Force -Confirm:$false -ErrorAction SilentlyContinue
Get-ChildItem (Join-Path $vendor "tessdata") -Filter "*.jar" -ErrorAction SilentlyContinue |
    Remove-Item -Force -Confirm:$false

Write-Host "[5/5] Baixando idiomas (por, osd) do tessdata_fast..."
$tessdata = Join-Path $vendor "tessdata"
New-Item -ItemType Directory -Force -Path $tessdata | Out-Null
Get-File "$TessdataBase/por.traineddata" (Join-Path $tessdata "por.traineddata")
Get-File "$TessdataBase/osd.traineddata" (Join-Path $tessdata "osd.traineddata")

Remove-Item $tmp -Recurse -Force -Confirm:$false

$size = [math]::Round((Get-ChildItem $vendor -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host ""
Write-Host "Tesseract vendorizado em $vendor ($size MB)"
& (Join-Path $vendor "tesseract.exe") --version | Select-Object -First 2
