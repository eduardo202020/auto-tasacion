[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9-]+$')]
    [string] $LotId,

    [string] $ConfigPath,

    [string] $ResultsDirectory,

    [ValidateSet('Html', 'Text')]
    [string] $OutputFormat = 'Html'
)

$ErrorActionPreference = 'Stop'

function Resolve-LocalPath {
    param(
        [Parameter(Mandatory)] [string] $RawPath,
        [Parameter(Mandatory)] [string] $BaseDirectory
    )

    $expanded = [Environment]::ExpandEnvironmentVariables($RawPath)
    if ([System.IO.Path]::IsPathRooted($expanded)) {
        return [System.IO.Path]::GetFullPath($expanded)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BaseDirectory $expanded))
}

function Get-ResultsDirectoryFromConfig {
    param([Parameter(Mandatory)] [string] $Path)

    $configFile = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    $config = Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json
    $configDirectory = Split-Path -Parent $configFile
    $runtimeDirectory = [string] $config.runtime_directory

    if ([string]::IsNullOrWhiteSpace($runtimeDirectory)) {
        $locationsRaw = [string] $config.locations_config_path
        if ([string]::IsNullOrWhiteSpace($locationsRaw)) {
            throw 'La configuracion no contiene runtime_directory ni locations_config_path.'
        }
        $locationsPath = Resolve-LocalPath -RawPath $locationsRaw -BaseDirectory $configDirectory
        $locations = Get-Content -LiteralPath $locationsPath -Raw | ConvertFrom-Json
        $profile = if ([string]::IsNullOrWhiteSpace([string] $config.location_profile)) { 'production' } else { [string] $config.location_profile }
        $runtimeDirectory = [string] $locations.pad.profiles.$profile.runtime_directory
    }

    if ([string]::IsNullOrWhiteSpace($runtimeDirectory)) {
        throw 'No se pudo resolver runtime_directory para el resumen de Teams.'
    }
    return Join-Path (Resolve-LocalPath -RawPath $runtimeDirectory -BaseDirectory $configDirectory) 'resultados'
}

function Encode-Html {
    param([AllowEmptyString()] [string] $Value)
    return [System.Net.WebUtility]::HtmlEncode($Value)
}

function Format-StatusLabel {
    param([string] $Status)
    return (($Status -replace '_', ' ').ToLowerInvariant())
}

function Format-RunDuration {
    param(
        [AllowEmptyString()] [string] $CreatedAt,
        [AllowEmptyString()] [string] $UpdatedAt
    )

    $started = [datetimeoffset]::MinValue
    $finished = [datetimeoffset]::MinValue
    if (-not [datetimeoffset]::TryParse($CreatedAt, [ref] $started) -or
        -not [datetimeoffset]::TryParse($UpdatedAt, [ref] $finished) -or
        $finished -lt $started) {
        return 'No informada'
    }

    $span = $finished - $started
    $seconds = [Math]::Floor($span.TotalSeconds)
    if ($seconds -lt 60) {
        return "$seconds s"
    }
    if ($seconds -lt 3600) {
        return "$([Math]::Floor($seconds / 60)) min $($seconds % 60) s"
    }
    return "$([Math]::Floor($seconds / 3600)) h $([Math]::Floor(($seconds % 3600) / 60)) min"
}

if ([string]::IsNullOrWhiteSpace($ResultsDirectory)) {
    if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
        throw 'Indique -ConfigPath o -ResultsDirectory.'
    }
    $ResultsDirectory = Get-ResultsDirectoryFromConfig -Path $ConfigPath
}

$resolvedResultsDirectory = (Resolve-Path -LiteralPath $ResultsDirectory -ErrorAction Stop).Path
$matches = @(
    Get-ChildItem -LiteralPath $resolvedResultsDirectory -File -Filter "$LotId*_macro_3270.json" |
        Where-Object { $_.BaseName -match "^$([regex]::Escape($LotId))_[0-9A-Fa-f]{12}_macro_3270$" } |
        Sort-Object LastWriteTimeUtc -Descending
)
if ($matches.Count -eq 0) {
    throw "No existe un resultado macro_3270 para el lote $LotId."
}

$record = Get-Content -LiteralPath $matches[0].FullName -Raw | ConvertFrom-Json
if ([string] $record.id_lote -ne $LotId) {
    throw 'El resultado seleccionado no corresponde al lote solicitado.'
}

$status = [string] $record.status
$mode = [string] $record.modo_ejecucion
$results = @($record.results)
$total = $results.Count
$ok = @($results | Where-Object { [string] $_.estado -match '(_OK$|^COMPLETADO$)' }).Count
$incidents = [Math]::Max(0, $total - $ok)
$technicalError = -not [string]::IsNullOrWhiteSpace([string] $record.technical_error)
$withIncidents = $status -match 'CON_INCIDENCIAS' -or $incidents -gt 0
$failed = $technicalError -or $status -match '(^ERROR|_ERROR_)'
$duration = Format-RunDuration -CreatedAt ([string] $record.created_at) -UpdatedAt ([string] $record.updated_at)

if ($failed) {
    $headline = 'El procesamiento 3270 requiere atenci&#243;n'
    $color = '#c62828'
    $stateLabel = 'Error operativo'
}
elseif ($withIncidents) {
    $headline = 'Consulta 3270 finalizada con observaciones'
    $color = '#b54708'
    $stateLabel = 'Finalizado con observaciones'
}
else {
    $headline = 'Consulta 3270 finalizada sin cambios'
    $color = '#1a7f37'
    $stateLabel = 'Completado'
}

$resultGroups = @(
    $results |
        Where-Object { -not [string]::IsNullOrWhiteSpace([string] $_.resultado_3270) } |
        Group-Object -Property resultado_3270 |
        Sort-Object -Property @{ Expression = 'Count'; Descending = $true }, @{ Expression = 'Name'; Descending = $false } |
        ForEach-Object { "$(Encode-Html ([string] $_.Name)) ($($_.Count))" }
)
$publishedWorkbook = [string] $record.published_workbook
$published = -not [string]::IsNullOrWhiteSpace($publishedWorkbook)
$publishedFilename = if ($published) { [System.IO.Path]::GetFileName($publishedWorkbook) } else { 'No publicado' }
$revisionIa = if ($record.revision_ia_excluida -eq $true) { 'Excluidas del 3270' } else { 'No informado' }

if ($OutputFormat -eq 'Text') {
    $lines = @(
        "AUTO TASACIONES | RESULTADO 3270",
        "Lote: $LotId",
        "Estado global: $status",
        "Estado: $stateLabel",
        "Modo: $mode",
        "Casos enviados a 3270: $total",
        "Consultas correctas: $ok",
        "Con incidencias: $incidents",
        "Revision IA: $revisionIa",
        "Duracion: $duration",
        "Libro final: $publishedFilename"
    )
    if ($resultGroups.Count -gt 0 -and -not $failed) {
        $lines += "Resultado observado: $($resultGroups -join '; ')"
    }
    Write-Output ($lines -join [Environment]::NewLine)
    return
}

$html = @(
    '<p>'
    '<span style="font-size:12px;color:#616161;"><b>AUTO TASACIONES &middot; RESULTADO 3270</b></span><br>'
    "<span style=`"color:$color;`"><b>&#9679; $headline</b></span><br>"
    "<span style=`"font-size:11px;color:#616161;`">Lote: $(Encode-Html $LotId)</span>"
    '</p>'
    '<p><b>Resumen de la consulta</b><br>'
    "Casos enviados a 3270: <b>$total</b><br>"
    "Consultas correctas: <b>$ok</b><br>"
    "Con incidencias: <b>$incidents</b><br>"
    "Revision IA: <b>$revisionIa</b><br>"
    "Modo: <b>$(Encode-Html $mode)</b><br>"
    "Estado: <b>$(Encode-Html $stateLabel)</b><br>"
    "Estado global: <b>$(Encode-Html $status)</b><br>"
    "Duraci&#243;n: <b>$(Encode-Html $duration)</b>"
    '</p>'
)
if ($resultGroups.Count -gt 0 -and -not $failed) {
    $html += "<p><span style=`"font-size:11px;color:#616161;`">Resultado observado: $($resultGroups -join '; ')</span></p>"
}
$html += "<p><span style=`"font-size:11px;color:#616161;`">Libro final: $(Encode-Html $publishedFilename)</span></p>"
$html += '<p><span style="font-size:10px;color:#616161;">El detalle tecnico y la traza por caso permanecen en el JSON y el XLSM local.</span></p>'

Write-Output ($html -join '')
