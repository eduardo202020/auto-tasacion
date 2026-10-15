[CmdletBinding()]
param(
    [string] $FlowName = 'auto-tasacion-orquestar-lote',
    [string] $OutputPath,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'

# This utility reads a saved cloud-flow definition and writes only the Teams
# connection-reference logical name and group-chat identifier needed by the
# deployment generator. It never writes Power Platform or prints clientdata,
# which can contain unrelated secure HTTP action settings.
$DataverseUrl = 'https://org9a4ef0e0.crm4.dynamics.com'
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $PSScriptRoot '..\..\config\teams-notifications.local.json'
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
if ((Test-Path -LiteralPath $OutputPath) -and -not $Force) {
    throw "Ya existe $OutputPath. Use -Force para reemplazar solamente la configuracion local de Teams."
}

function Get-TeamsPostActions {
    param(
        [Parameter(Mandatory)] [object] $Actions,
        [string] $Path = ''
    )

    foreach ($property in $Actions.PSObject.Properties) {
        $name = [string] $property.Name
        $action = $property.Value
        $actionPath = if ([string]::IsNullOrWhiteSpace($Path)) { $name } else { "$Path/$name" }
        $host = $action.inputs.host
        $parameters = $action.inputs.parameters
        if ($action.type -eq 'OpenApiConnection' -and
            $host.apiId -eq '/providers/Microsoft.PowerApps/apis/shared_teams' -and
            $host.operationId -eq 'PostMessageToConversation' -and
            $parameters.poster -eq 'Flow bot' -and
            $parameters.location -eq 'Group chat' -and
            ([string] $parameters.'body/recipient') -match '^19:[^\s]+@thread\.v2$') {
            [pscustomobject]@{
                Name = $name
                Path = $actionPath
                GroupChatId = [string] $parameters.'body/recipient'
            }
        }
        if ($null -ne $action.actions) {
            Get-TeamsPostActions -Actions $action.actions -Path $actionPath
        }
        if ($null -ne $action.else -and $null -ne $action.else.actions) {
            Get-TeamsPostActions -Actions $action.else.actions -Path "$actionPath/else"
        }
    }
}

Import-Module MSAL.PS -Force
$token = Get-MsalToken `
    -ClientId '51f81489-12ee-4a9e-aaae-a2591f45987d' `
    -TenantId 'organizations' `
    -RedirectUri 'http://localhost' `
    -Scopes "$DataverseUrl/.default" `
    -Interactive `
    -LoginHint 'mailbox_27530@emeal.nttdata.com' `
    -Timeout ([TimeSpan]::FromMinutes(5))

$safeName = $FlowName.Replace("'", "''")
$uri = "$DataverseUrl/api/data/v9.2/workflows?`$select=name,clientdata&`$filter=name eq '$safeName' and category eq 5"
$response = Invoke-RestMethod -Method Get -Uri $uri -Headers @{ Authorization = "Bearer $($token.AccessToken)"; Accept = 'application/json' }
$flows = @($response.value)
if ($flows.Count -ne 1) {
    throw "No se encontro el flujo '$FlowName'. Guarde primero el borrador que contiene la accion de Teams."
}

$clientData = ([string] $flows[0].clientdata | ConvertFrom-Json).properties
$teamsReference = $clientData.connectionReferences.shared_teams
if ($null -eq $teamsReference -or [string]::IsNullOrWhiteSpace([string] $teamsReference.connection.connectionReferenceLogicalName)) {
    throw "El flujo '$FlowName' no tiene la referencia shared_teams. Agregue y guarde una accion de Teams con Flow bot y Group chat."
}
$matches = @(Get-TeamsPostActions -Actions $clientData.definition.actions)
if ($matches.Count -ne 1) {
    $found = if ($matches.Count -eq 0) { 'ninguna' } else { "$($matches.Count) acciones" }
    throw "Se encontraron $found acciones de Teams Flow bot / Group chat en '$FlowName'. Deje exactamente una accion temporal antes de exportar la configuracion."
}

$config = [ordered]@{
    schema_version = 1
    automation = 'auto-tasacion'
    enabled = $true
    connection = [ordered]@{
        reference_logical_name = [string] $teamsReference.connection.connectionReferenceLogicalName
    }
    destination = [ordered]@{
        kind = 'group_chat'
        group_chat_id = [string] $matches[0].GroupChatId
        display_name = '[BBVA] AUTOMATIZACION TASACIONES'
    }
}

$directory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
$config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding utf8
Write-Output "Configuracion local de Teams creada: $OutputPath"
