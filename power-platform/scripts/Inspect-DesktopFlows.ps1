[CmdletBinding()]
param(
    # Regular expression applied to the Desktop Flow display name.
    [string] $NamePattern = '(?i)fuvex|emisoras|leasing',
    [string] $OutputPath,
    [string] $LoginHint = 'mailbox_27530@emeal.nttdata.com',
    [switch] $Skip3270SignalAnalysis
)

$ErrorActionPreference = 'Stop'

# Read-only inventory for Desktop Flows in the current Dataverse environment.
# It never starts, stops, publishes, updates, exports, or prints a flow's
# clientdata. Clientdata is inspected only in memory to report generic 3270
# preparation signals without exposing credentials, paths, or UI selectors.
$DataverseUrl = 'https://org9a4ef0e0.crm4.dynamics.com'

function Get-DesktopSchemaNames {
    param(
        [Parameter(Mandatory)] [hashtable] $Headers,
        [Parameter(Mandatory)] [string] $WorkflowId,
        [Parameter(Mandatory)] [ValidateSet('inputs', 'outputs')] [string] $Kind
    )

    $path = "workflows($WorkflowId)/$Kind/`$value"
    try {
        $response = Invoke-RestMethod -Method Get -Uri "$DataverseUrl/api/data/v9.2/$path" -Headers $Headers
        if ($null -eq $response.schema -or $null -eq $response.schema.properties) {
            return @()
        }
        return @($response.schema.properties.PSObject.Properties.Name | Sort-Object)
    }
    catch {
        # A flow without the requested schema is valid. Keep the inventory
        # useful even if a legacy flow does not expose inputs or outputs.
        return @()
    }
}

function Get-3270PreparationSignals {
    param([AllowEmptyString()] [string] $ClientData)

    if ([string]::IsNullOrWhiteSpace($ClientData)) {
        return @()
    }

    # The values are labels only. Never return the matched content because a
    # Desktop Flow may contain paths, selectors, or credentials.
    $rules = @(
        [pscustomobject]@{ Label = 'emulador_o_sesion_3270'; Pattern = '(?i)\b(pcomm|personal communications|\.ws\b|3270|hllapi)\b' },
        [pscustomobject]@{ Label = 'apertura_de_aplicacion'; Pattern = '(?i)(runapplication|ejecutar aplicaci[oó]n|launch application)' },
        [pscustomobject]@{ Label = 'interaccion_de_teclado'; Pattern = '(?i)(sendkeys|send keys|enviar teclas|press key|key press)' },
        [pscustomobject]@{ Label = 'inicio_de_sesion'; Pattern = '(?i)(\blogon\b|\blogin\b|iniciar sesi[oó]n|usuario|contrase[ñn]a|password)' },
        [pscustomobject]@{ Label = 'espera_o_reintento'; Pattern = '(?i)(\bwait\b|esperar|timeout|reintento|retry)' }
    )

    return @(
        foreach ($rule in $rules) {
            if ($ClientData -match $rule.Pattern) {
                $rule.Label
            }
        }
    )
}

function Convert-DesktopFlowState {
    param([object] $StateCode)

    switch ([int] $StateCode) {
        0 { return 'Borrador/Desactivado' }
        1 { return 'Activado' }
        2 { return 'Suspendido' }
        default { return "Desconocido ($StateCode)" }
    }
}

Import-Module MSAL.PS -Force
$token = Get-MsalToken `
    -ClientId '51f81489-12ee-4a9e-aaae-a2591f45987d' `
    -TenantId 'organizations' `
    -RedirectUri 'http://localhost' `
    -Scopes "$DataverseUrl/.default" `
    -Interactive `
    -LoginHint $LoginHint `
    -Timeout ([TimeSpan]::FromMinutes(5))

$headers = @{
    Authorization = "Bearer $($token.AccessToken)"
    Accept = 'application/json'
    'MSCRM.IncludeUnpublished' = 'true'
}

$uri = "$DataverseUrl/api/data/v9.2/workflows?`$select=workflowid,name,statecode,statuscode,modifiedon,description,clientdata&`$filter=category eq 6&`$orderby=name"
$response = Invoke-RestMethod -Method Get -Uri $uri -Headers $headers
$flows = @($response.value | Where-Object { ([string] $_.name) -match $NamePattern })

if ($flows.Count -eq 0) {
    Write-Warning "No se encontraron Desktop Flows cuyo nombre coincida con: $NamePattern"
    Write-Output 'Se consultaron solo metadatos de Dataverse; no se modifico ni ejecuto ningun flujo.'
    return
}

$results = foreach ($flow in $flows) {
    $flowId = [string] $flow.workflowid
    $signals = if ($Skip3270SignalAnalysis) { @() } else { Get-3270PreparationSignals -ClientData ([string] $flow.clientdata) }
    [pscustomobject]@{
        Name = [string] $flow.name
        WorkflowId = $flowId
        State = Convert-DesktopFlowState -StateCode $flow.statecode
        StatusCode = $flow.statuscode
        ModifiedOn = $flow.modifiedon
        InputVariables = Get-DesktopSchemaNames -Headers $headers -WorkflowId $flowId -Kind 'inputs'
        OutputVariables = Get-DesktopSchemaNames -Headers $headers -WorkflowId $flowId -Kind 'outputs'
        Signals3270 = $signals
    }
}

$results | Select-Object `
    Name, WorkflowId, State, StatusCode, ModifiedOn,
    @{ Name = 'InputVariables'; Expression = { $_.InputVariables -join ', ' } },
    @{ Name = 'OutputVariables'; Expression = { $_.OutputVariables -join ', ' } },
    @{ Name = 'Signals3270'; Expression = { $_.Signals3270 -join ', ' } }

if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $resolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
    $directory = Split-Path -Parent $resolvedOutputPath
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $results | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $resolvedOutputPath -Encoding utf8
    Write-Output "Inventario local creado: $resolvedOutputPath"
}

Write-Output 'Consulta terminada. No se modifico, publico, ejecuto ni exporto ningun Desktop Flow.'
