[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'config.development.json')
)

$ErrorActionPreference = 'Stop'
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
$Settings = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$RuntimeDirectory = [string]$Settings.runtime_directory
if (-not [System.IO.Path]::IsPathRooted($RuntimeDirectory)) {
    $RuntimeDirectory = Join-Path (Split-Path -Parent $ConfigPath) $RuntimeDirectory
}
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
