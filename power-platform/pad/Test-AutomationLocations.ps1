[CmdletBinding()]
param(
    [string] $LocationsConfigPath,
    [ValidateSet('all', 'development', 'production')]
    [string] $Profile = 'all',
    [switch] $CheckLocalPaths
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($LocationsConfigPath)) {
    $LocationsConfigPath = Join-Path $PSScriptRoot '..\..\config\automation-locations.json'
}
$LocationsConfigPath = (Resolve-Path -LiteralPath $LocationsConfigPath).Path
$locations = Get-Content -LiteralPath $LocationsConfigPath -Raw | ConvertFrom-Json
$failures = [System.Collections.Generic.List[string]]::new()

function Add-Failure([string] $Message) { $script:failures.Add($Message) }
function Normalize-CloudPath([string] $Path) {
    $value = ([string] $Path).Trim().Replace('\', '/')
    if (-not $value.StartsWith('/') -or $value.Contains('/../') -or $value.EndsWith('/..')) { return $null }
    return '/' + (($value -split '/' | Where-Object { $_ }) -join '/')
}

$base = Normalize-CloudPath $locations.onedrive.base_folder
$result = Normalize-CloudPath $locations.onedrive.result_folder
if ($null -eq $base) { Add-Failure 'onedrive.base_folder debe ser una ruta absoluta válida.' }
if ($null -eq $result) { Add-Failure 'onedrive.result_folder debe ser una ruta absoluta válida.' }
if ($null -ne $base -and $result -ne $base) { Add-Failure 'onedrive.result_folder debe coincidir con onedrive.base_folder.' }
foreach ($name in 'pdfs', 'controls', 'archives') {
    $value = [string] $locations.onedrive.subfolders.$name
    if ([string]::IsNullOrWhiteSpace($value) -or $value -match '[\\/]' -or $value -in '.', '..') {
        Add-Failure "onedrive.subfolders.$name debe ser un nombre de carpeta único."
    }
}
$profilesToCheck = if ($Profile -eq 'all') { @('development', 'production') } else { @($Profile) }
foreach ($profileName in $profilesToCheck) {
    $profile = $locations.pad.profiles.$profileName
    if ($null -eq $profile) { Add-Failure "Falta el perfil PAD '$profileName'."; continue }
    $input = [System.IO.Path]::GetFullPath(([string] $profile.input_directory)).TrimEnd('\')
    $runtime = [System.IO.Path]::GetFullPath(([string] $profile.runtime_directory)).TrimEnd('\')
    if ($runtime -eq $input -or $runtime.StartsWith($input + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        Add-Failure "El runtime PAD de '$profileName' no puede estar dentro de su input_directory OneDrive."
    }
    if ($CheckLocalPaths) {
        # Read-only checks: the validator never creates the OneDrive input,
        # local installation, or runtime directories.
        foreach ($path in @($input, [string] $profile.install_directory, $runtime)) {
            if (-not (Test-Path -LiteralPath $path)) { Add-Failure "No existe en este equipo: $path" }
        }
    }
}

if ($failures.Count) { throw ($failures -join [Environment]::NewLine) }
[pscustomobject]@{
    base_folder = $base
    pdfs_folder = "$base/$($locations.onedrive.subfolders.pdfs)"
    controls_folder = "$base/$($locations.onedrive.subfolders.controls)"
    archives_folder = "$base/$($locations.onedrive.subfolders.archives)"
    result_folder = $result
    profiles_checked = $profilesToCheck -join ','
    checked_local_paths = [bool] $CheckLocalPaths
} | Format-List
