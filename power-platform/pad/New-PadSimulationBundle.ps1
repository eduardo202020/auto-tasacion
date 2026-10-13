[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $DestinationPath,
    [switch] $Zip
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$DestinationPath = [System.IO.Path]::GetFullPath($DestinationPath)
if (Test-Path -LiteralPath $DestinationPath) {
    throw "El destino ya existe: $DestinationPath. Elija una carpeta nueva para no sobrescribir una instalación."
}

$ReleaseRoot = Join-Path $DestinationPath 'auto-tasacion'
$PadSource = Join-Path $RepositoryRoot 'power-platform\pad'
$PadDestination = Join-Path $ReleaseRoot 'power-platform\pad'
New-Item -ItemType Directory -Force -Path $PadDestination, (Join-Path $ReleaseRoot 'tools'), (Join-Path $ReleaseRoot 'config') | Out-Null

# The bundle contains source and configuration examples only. It never includes
# local virtual environments, runtime state, OneDrive input, credentials, PDFs
# or results.
Get-ChildItem -LiteralPath $PadSource -Recurse -File -Force | Where-Object {
    $_.Name -ne 'config.local.json' -and
    $_.FullName -notmatch '[\\/](\.venv|runtime|__pycache__)[\\/]'
} | ForEach-Object {
    $relativePath = $_.FullName.Substring($PadSource.Length).TrimStart('\', '/')
    $destinationFile = Join-Path $PadDestination $relativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destinationFile) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $destinationFile -Force
}
Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'tools\verify_workbook.py') -Destination (Join-Path $ReleaseRoot 'tools\verify_workbook.py') -Force
Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'config\automation-locations.json') -Destination (Join-Path $ReleaseRoot 'config\automation-locations.json') -Force

$releaseGuide = @'
# Paquete local PAD — auto-tasacion

Este paquete proviene de un commit versionado y se puede copiar a NTTD-MKEY sin
instalar Git. No contiene credenciales, PDFs, resultados ni estados anteriores.

1. Copiar `auto-tasacion` a la ruta de instalación definida para producción:
   `C:\ProgramData\NTT DATA EMEAL\auto-tasacion`.
2. Crear la configuración local desde `power-platform\pad`:
   ```powershell
   .\New-PadSimulationConfig.ps1 -Profile production -OutputPath .\config.local.json
   ```
3. Crear un entorno Python local e instalar dependencias:
   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
4. Validar con datos sintéticos antes de configurar el Desktop Flow.

El flujo mantiene exclusivamente `SIMULACION` e `IBM_3270_MOCK`.
'@
$releaseGuide | Set-Content -LiteralPath (Join-Path $DestinationPath 'README.md') -Encoding utf8

if ($Zip) {
    $zipPath = "$DestinationPath.zip"
    Compress-Archive -LiteralPath $ReleaseRoot -DestinationPath $zipPath -CompressionLevel Optimal
    Write-Output "Paquete ZIP creado: $zipPath"
}
Write-Output "Paquete local PAD creado: $DestinationPath"
