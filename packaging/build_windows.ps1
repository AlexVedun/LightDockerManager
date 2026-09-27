$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Version = if ($env:VERSION) {
    $env:VERSION -replace '^v', ''
} else {
    python -c "from version import __version__; print(__version__)"
}

$DistributionDir = Join-Path $ProjectRoot "distribution"
$OutputFile = Join-Path $DistributionDir "LightDockerManager-$Version-x86_64.exe"

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $DistributionDir | Out-Null

python -m PyInstaller `
    --name LightDockerManager `
    --windowed `
    --onefile `
    --noconfirm `
    --clean `
    --icon packaging/icon.ico `
    --add-data "i18n;i18n" `
    --add-data "packaging/icon.png;packaging" `
    main.py

Copy-Item -Force "dist/LightDockerManager.exe" $OutputFile
Remove-Item -Recurse -Force build, dist

Write-Host "Built: $OutputFile"
