[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z][a-z0-9-]{2,62}$')]
    [string] $ProcessKey,
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string] $DisplayName,
    [string] $DestinationRoot,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'

# Creates only versionable documentation and non-sensitive placeholders. It
# does not authenticate, call a platform API, or create connections, secrets,
# folders, flows, desktop flows, or notifications.
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$templateRoot = Join-Path $repositoryRoot 'docs\harness\templates'
if (-not (Test-Path -LiteralPath $templateRoot -PathType Container)) {
    throw "No se encontró el directorio de plantillas: $templateRoot"
}
if ([string]::IsNullOrWhiteSpace($DestinationRoot)) {
    $DestinationRoot = Join-Path $repositoryRoot 'docs\processes'
}
$DestinationRoot = [System.IO.Path]::GetFullPath($DestinationRoot)
$destination = Join-Path $DestinationRoot $ProcessKey

if ((Test-Path -LiteralPath $destination) -and -not $Force) {
    throw "Ya existe un harness para '$ProcessKey' en $destination. Use -Force solamente si desea actualizar sus plantillas."
}
New-Item -ItemType Directory -Force -Path $destination | Out-Null

$replacements = [ordered]@{
    '__PROCESS_KEY__' = $ProcessKey
    '__DISPLAY_NAME__' = $DisplayName.Trim()
    '__CREATED_UTC__' = [DateTime]::UtcNow.ToString('o')
}
$files = @(
    @{ Template = 'process-profile.example.json'; Output = 'process-profile.json' },
    @{ Template = 'implementation-checklist.md'; Output = 'implementation-checklist.md' },
    @{ Template = 'acceptance-record.md'; Output = 'acceptance-record.md' }
)

foreach ($file in $files) {
    $templatePath = Join-Path $templateRoot $file.Template
    $content = Get-Content -LiteralPath $templatePath -Raw
    foreach ($replacement in $replacements.GetEnumerator()) {
        $content = $content.Replace([string] $replacement.Key, [string] $replacement.Value)
    }
    Set-Content -LiteralPath (Join-Path $destination $file.Output) -Value $content -Encoding utf8
}

[pscustomobject]@{
    ProcessKey = $ProcessKey
    DisplayName = $DisplayName.Trim()
    Path = $destination
    Files = $files.Output
    RemoteChanges = $false
} | Format-List
