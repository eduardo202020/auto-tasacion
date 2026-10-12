[CmdletBinding()]
param(
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $PSScriptRoot 'config.development.json'
}
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path

function Resolve-PadRuntimeDirectory {
    param([Parameter(Mandatory)] $Configuration, [Parameter(Mandatory)] [string] $ConfigurationPath)

    $runtimeDirectory = [string] $Configuration.runtime_directory
    if ([string]::IsNullOrWhiteSpace($runtimeDirectory) -and -not [string]::IsNullOrWhiteSpace([string] $Configuration.location_profile)) {
        $locationsReference = [string] $Configuration.locations_config_path
        if ([string]::IsNullOrWhiteSpace($locationsReference)) {
            $locationsReference = '../../config/automation-locations.json'
        }
        if (-not [System.IO.Path]::IsPathRooted($locationsReference)) {
            $locationsReference = Join-Path (Split-Path -Parent $ConfigurationPath) $locationsReference
        }
        $locations = Get-Content -LiteralPath $locationsReference -Raw | ConvertFrom-Json
        $runtimeDirectory = [string] $locations.pad.profiles.([string] $Configuration.location_profile).runtime_directory
    }
    if ([string]::IsNullOrWhiteSpace($runtimeDirectory)) {
        throw 'La configuración PAD no define runtime_directory ni un location_profile válido.'
    }
    if (-not [System.IO.Path]::IsPathRooted($runtimeDirectory)) {
        $runtimeDirectory = Join-Path (Split-Path -Parent $ConfigurationPath) $runtimeDirectory
    }
    return [System.IO.Path]::GetFullPath($runtimeDirectory)
}

$Settings = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$RuntimeDirectory = Resolve-PadRuntimeDirectory -Configuration $Settings -ConfigurationPath $ConfigPath
$MonitorState = Join-Path $RuntimeDirectory 'estado\monitor.pid.json'
if (-not (Test-Path -LiteralPath $MonitorState)) {
    Write-Output 'No hay un monitor local registrado.'
    exit 0
}

$Monitor = Get-Content -LiteralPath $MonitorState -Raw | ConvertFrom-Json
$Process = Get-Process -Id $Monitor.pid -ErrorAction SilentlyContinue
if ($null -ne $Process) {
    Stop-Process -Id $Monitor.pid -ErrorAction Stop
    Write-Output "Monitor local detenido (PID $($Monitor.pid))."
}
Remove-Item -LiteralPath $MonitorState -Force
