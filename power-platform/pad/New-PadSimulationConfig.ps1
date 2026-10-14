[CmdletBinding()]
param(
    [ValidateSet('development', 'production')]
    [string] $Profile = 'development',
    [string] $LocationsConfigPath,
    [string] $OutputPath,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($LocationsConfigPath)) {
    $LocationsConfigPath = Join-Path $PSScriptRoot '..\..\config\automation-locations.json'
}
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $PSScriptRoot 'config.local.json'
}
$LocationsConfigPath = (Resolve-Path -LiteralPath $LocationsConfigPath).Path
if ((Test-Path -LiteralPath $OutputPath) -and -not $Force) {
    throw "Ya existe $OutputPath. Use -Force para reemplazar solo esa configuración local."
}

$locations = Get-Content -LiteralPath $LocationsConfigPath -Raw | ConvertFrom-Json
if ($locations.schema_version -ne 1 -or $locations.automation -ne 'auto-tasacion') {
    throw 'El archivo de ubicaciones no corresponde a auto-tasacion schema_version=1.'
}
$profileConfiguration = $locations.pad.profiles.$Profile
if ($null -eq $profileConfiguration) {
    throw "No existe el perfil PAD '$Profile'."
}
$inputDirectory = [string] $profileConfiguration.input_directory
$runtimeDirectory = [string] $profileConfiguration.runtime_directory
if ([string]::IsNullOrWhiteSpace($inputDirectory) -or [string]::IsNullOrWhiteSpace($runtimeDirectory)) {
    throw "El perfil '$Profile' requiere input_directory y runtime_directory."
}
$inputFull = [System.IO.Path]::GetFullPath($inputDirectory).TrimEnd('\')
$runtimeFull = [System.IO.Path]::GetFullPath($runtimeDirectory).TrimEnd('\')
if ($runtimeFull.StartsWith($inputFull + '\', [System.StringComparison]::OrdinalIgnoreCase) -or $runtimeFull -eq $inputFull) {
    throw 'runtime_directory debe quedar fuera de la carpeta OneDrive de entrada.'
}

@{
    schema_version = 1
    mode = 'SIMULACION'
    input_directory = $inputFull
    runtime_directory = $runtimeFull
    poll_seconds = 5
    stability_checks = 3
    stability_interval_seconds = 2
    processing_lease_seconds = 900
    suspicious_floors_threshold = 100
    suspicious_basements_threshold = 20
    file_retry_attempts = 5
    file_retry_base_seconds = 0.1
    input_sync_timeout_seconds = 600
    input_sync_poll_seconds = 5
    synthetic_failure_case_ids = @()
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $OutputPath -Encoding utf8

Write-Output "Configuración PAD '$Profile' generada en $OutputPath. Modo: SIMULACION."
