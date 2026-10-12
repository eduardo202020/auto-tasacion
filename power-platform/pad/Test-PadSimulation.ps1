[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    throw "No existe $Python. Cree el entorno con: py -3.13 -m venv power-platform/pad/.venv"
}
& $Python -m unittest discover -s (Join-Path $PSScriptRoot 'tests') -v
exit $LASTEXITCODE
