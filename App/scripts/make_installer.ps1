param(
    [Parameter(Mandatory = $true)][string]$Version,
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot "build.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Build falhou." }
}
if (-not (Test-Path (Join-Path $root "backend\dist\Routrip\Routrip.exe"))) {
    throw "backend\dist\Routrip\Routrip.exe não existe. Rode sem -SkipBuild."
}

$iscc = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 não encontrado. Instale com: winget install -e --id JRSoftware.InnoSetup"
}

Write-Host "Compactando o instalador (LZMA2 ultra, leva alguns minutos)..."
& $iscc "/DAppVersion=$Version" (Join-Path $root "installer\routrip.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC falhou." }

$saida = Join-Path $root "installer\output\Routrip-Setup-$Version.exe"
Write-Host ("Instalador gerado: {0} ({1:N0} MB)" -f $saida, ((Get-Item $saida).Length / 1MB))
