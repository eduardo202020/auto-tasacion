[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'config.development.json'),
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
$EntryPoint = Join-Path $PSScriptRoot 'pad_simulator.py'
$VenvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (Test-Path -LiteralPath $VenvPython) {
    $Python = $VenvPython
    $Arguments = '"{0}" --config "{1}" monitor' -f $EntryPoint, $ConfigPath
}
else {
    $Python = (Get-Command py.exe -ErrorAction Stop).Source
    $Arguments = '-3.13 "{0}" --config "{1}" monitor' -f $EntryPoint, $ConfigPath
}

if ($Foreground) {
    if (Test-Path -LiteralPath $VenvPython) {
        & $Python $EntryPoint '--config' $ConfigPath 'monitor'
    }
    else {
        & $Python '-3.13' $EntryPoint '--config' $ConfigPath 'monitor'
    }
    exit $LASTEXITCODE
}

$Settings = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$RuntimeDirectory = [string]$Settings.runtime_directory
if (-not [System.IO.Path]::IsPathRooted($RuntimeDirectory)) {
    $RuntimeDirectory = Join-Path (Split-Path -Parent $ConfigPath) $RuntimeDirectory
}
$MonitorState = Join-Path $RuntimeDirectory 'estado\monitor.pid.json'
if (Test-Path -LiteralPath $MonitorState) {
    $Existing = Get-Content -LiteralPath $MonitorState -Raw | ConvertFrom-Json
    if (Get-Process -Id $Existing.pid -ErrorAction SilentlyContinue) {
        throw "Ya existe un monitor local activo con PID $($Existing.pid). Use Stop-PadSimulationMonitor.ps1 antes de iniciar otro."
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $MonitorState) | Out-Null
$Process = Start-Process -FilePath $Python -ArgumentList $Arguments -WindowStyle Hidden -PassThru
@{
    pid = $Process.Id
    started_at = [DateTime]::UtcNow.ToString('o')
    config_path = $ConfigPath
    entry_point = $EntryPoint
    mode = 'SIMULACION'
} | ConvertTo-Json | Set-Content -LiteralPath $MonitorState -Encoding utf8

Write-Output "Monitor local iniciado (PID $($Process.Id)). No se conecta a IBM 3270 ni a Power Platform."
