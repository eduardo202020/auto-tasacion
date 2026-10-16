[CmdletBinding()]
param(
    [switch] $Activate,
    [switch] $DryRun,
    [string] $FlowName = 'auto-tasacion-activar-pad',
    [string] $TeamsNotificationsConfigPath = (Join-Path $PSScriptRoot '..\..\config\teams-notifications.local.json'),
    [ValidateSet('Cloud', 'Desktop')]
    [string] $SuccessNotificationSource = 'Cloud'
)

$ErrorActionPreference = 'Stop'

if ($Activate -and $DryRun) {
    throw '-Activate y -DryRun no se pueden usar juntos.'
}

# This updater owns only the three notification actions. It first retrieves the
# saved PAD trigger flow, preserves its existing Desktop-flow connection and
# action settings, then adds the Teams nodes to its dependency graph. It never
# stores the flow definition, message recipients, or authentication material.
$DataverseUrl = 'https://org9a4ef0e0.crm4.dynamics.com'
$TeamsNotificationsConfigPath = (Resolve-Path -LiteralPath $TeamsNotificationsConfigPath).Path
$teamsConfig = Get-Content -LiteralPath $TeamsNotificationsConfigPath -Raw | ConvertFrom-Json
if ($teamsConfig.schema_version -ne 1 -or $teamsConfig.automation -ne 'auto-tasacion' -or $teamsConfig.enabled -ne $true) {
    throw 'La configuracion local de Teams no esta habilitada para auto-tasacion schema_version=1.'
}

$teamsConnectionReference = [string] $teamsConfig.connection.reference_logical_name
$groupChatId = [string] $teamsConfig.destination.group_chat_id
if ($teamsConnectionReference -notmatch '^[A-Za-z][A-Za-z0-9_]*$') {
    throw 'connection.reference_logical_name de Teams no es un nombre logico valido.'
}
if ($groupChatId -notmatch '^19:[^\s]+@thread\.v2$') {
    throw 'destination.group_chat_id de Teams debe ser el identificador de un chat grupal existente.'
}

function Set-ObjectProperty {
    param(
        [Parameter(Mandatory)] [object] $Object,
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [object] $Value
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
    else {
        $property.Value = $Value
    }
}

function Remove-ObjectProperty {
    param(
        [Parameter(Mandatory)] [object] $Object,
        [Parameter(Mandatory)] [string] $Name
    )

    if ($null -ne $Object.PSObject.Properties[$Name]) {
        [void] $Object.PSObject.Properties.Remove($Name)
    }
}

function New-TeamsGroupChatNotification {
    param(
        [Parameter(Mandatory)] [string] $MessageBody,
        [hashtable] $RunAfter = @{}
    )

    return [ordered]@{
        runAfter = $RunAfter
        type = 'OpenApiConnection'
        inputs = [ordered]@{
            host = [ordered]@{
                apiId = '/providers/Microsoft.PowerApps/apis/shared_teams'
                connectionName = 'shared_teams'
                operationId = 'PostMessageToConversation'
            }
            parameters = [ordered]@{
                poster = 'Flow bot'
                location = 'Group chat'
                'body/recipient' = $groupChatId
                'body/messageBody' = $MessageBody
            }
            authentication = "@parameters('`$authentication')"
        }
    }
}

function Get-PadDesktopAction {
    param([Parameter(Mandatory)] [object] $Actions)

    $matches = @(
        foreach ($property in $Actions.PSObject.Properties) {
            $action = $property.Value
            $connectorHost = $action.inputs.host
            if (($action.type -eq 'OpenApiConnection' -or $action.type -eq 'OpenApiConnectionWebhook') -and
                $connectorHost.apiId -eq '/providers/Microsoft.PowerApps/apis/shared_uiflow') {
                [pscustomobject]@{
                    Name = [string] $property.Name
                    Action = $action
                    OperationId = [string] $connectorHost.operationId
                }
            }
        }
    )
    if ($matches.Count -ne 1) {
        $found = if ($matches.Count -eq 0) { 'ninguna' } else { "$($matches.Count) acciones" }
        throw "Se encontraron $found acciones de Desktop Flow en la raiz de '$FlowName'. El actualizador no cambiara el flujo."
    }
    return $matches[0]
}

function Get-FlowByName {
    param([Parameter(Mandatory)] [hashtable] $Headers)

    $safeName = $FlowName.Replace("'", "''")
    $uri = "$DataverseUrl/api/data/v9.2/workflows?`$select=workflowid,name,statecode,statuscode,clientdata&`$filter=name eq '$safeName' and category eq 5"
    $response = Invoke-RestMethod -Method Get -Uri $uri -Headers $Headers
    $flows = @($response.value)
    if ($flows.Count -ne 1) {
        throw "No se encontro el flujo Cloud '$FlowName'."
    }
    return $flows[0]
}

function Invoke-DataversePatch {
    param(
        [Parameter(Mandatory)] [hashtable] $Headers,
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [object] $Body
    )

    Invoke-RestMethod -Method Patch -Uri "$DataverseUrl/api/data/v9.2/$Path" -Headers $Headers -ContentType 'application/json; charset=utf-8' -Body ($Body | ConvertTo-Json -Depth 100 -Compress) | Out-Null
}

function Publish-WorkflowDraft {
    param(
        [Parameter(Mandatory)] [hashtable] $Headers,
        [Parameter(Mandatory)] [string] $WorkflowId
    )

    $body = [ordered]@{
        ParameterXml = "<importexportxml><workflows><workflow>$WorkflowId</workflow></workflows></importexportxml>"
    }
    Invoke-RestMethod -Method Post -Uri "$DataverseUrl/api/data/v9.2/PublishXml" -Headers $Headers -ContentType 'application/json; charset=utf-8' -Body ($body | ConvertTo-Json -Compress) | Out-Null
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
$headers = @{
    Authorization = "Bearer $($token.AccessToken)"
    Accept = 'application/json'
    'If-Match' = '*'
}

$flow = Get-FlowByName -Headers $headers
$clientData = [string] $flow.clientdata | ConvertFrom-Json
if ($null -eq $clientData.properties -or $null -eq $clientData.properties.definition -or $null -eq $clientData.properties.definition.actions) {
    throw "La definicion guardada de '$FlowName' no tiene acciones actualizables."
}

$properties = $clientData.properties
$desktopAction = Get-PadDesktopAction -Actions $properties.definition.actions
$desktopActionName = $desktopAction.Name
$originalRunAfter = if ($null -eq $desktopAction.Action.runAfter) { @{} } else { $desktopAction.Action.runAfter }
$idLoteExpression = "replace(replace(triggerBody()?['Name'], 'Resultado_Final_', ''), '.xlsx', '')"

if ($null -eq $properties.connectionReferences) {
    throw "La definicion de '$FlowName' no tiene referencias de conexion para conservar."
}
Set-ObjectProperty -Object $properties.connectionReferences -Name 'shared_teams' -Value ([ordered]@{
    runtimeSource = 'embedded'
    connection = [ordered]@{
        connectionReferenceLogicalName = $teamsConnectionReference
    }
    api = [ordered]@{ name = 'shared_teams' }
})

$startNotificationName = 'Notificar_PAD_3270_inicio'
$successNotificationName = 'Notificar_PAD_3270_fin'
$errorNotificationName = 'Notificar_PAD_3270_error'
Set-ObjectProperty -Object $properties.definition.actions -Name $startNotificationName -Value (New-TeamsGroupChatNotification -RunAfter $originalRunAfter -MessageBody "@concat('Auto Tasaciones | lote ', $idLoteExpression, ' | PAD/3270 inicio.')")
Set-ObjectProperty -Object $desktopAction.Action -Name 'runAfter' -Value ([ordered]@{
    $startNotificationName = @('Succeeded', 'Failed', 'Skipped', 'TimedOut')
})
if ($SuccessNotificationSource -eq 'Cloud') {
    Set-ObjectProperty -Object $properties.definition.actions -Name $successNotificationName -Value (New-TeamsGroupChatNotification -RunAfter ([ordered]@{ $desktopActionName = @('Succeeded') }) -MessageBody "@concat('Auto Tasaciones | lote ', $idLoteExpression, ' | PAD/3270 finalizo. Estado: ', outputs('$desktopActionName')?['body/EstadoPad'], '. ', outputs('$desktopActionName')?['body/MensajePad'])")
}
else {
    # PAD posts the validated HTML summary read from its durable JSON. Keeping a
    # second Cloud success action would duplicate the operator-facing result.
    Remove-ObjectProperty -Object $properties.definition.actions -Name $successNotificationName
}
Set-ObjectProperty -Object $properties.definition.actions -Name $errorNotificationName -Value (New-TeamsGroupChatNotification -RunAfter ([ordered]@{ $desktopActionName = @('Failed', 'Skipped', 'TimedOut') }) -MessageBody "@concat('Auto Tasaciones | lote ', $idLoteExpression, ' | PAD/3270 requiere atencion. El flujo de escritorio no finalizo correctamente.')")

$plan = [pscustomobject]@{
    Flow = [string] $flow.name
    DesktopAction = $desktopActionName
    DesktopOperation = $desktopAction.OperationId
    Notifications = if ($SuccessNotificationSource -eq 'Cloud') { 3 } else { 2 }
    SuccessNotificationSource = $SuccessNotificationSource
    Mode = if ($Activate) { 'Activate' } elseif ($DryRun) { 'DryRun' } else { 'Plan' }
    WillModifyRemote = [bool] $Activate
}
$plan | Format-List

if (-not $Activate) {
    Write-Warning 'Se leyo la definicion actual para elaborar el plan. No se modifico Power Platform. Use -Activate unicamente durante un despliegue autorizado.'
    return
}

$workflowId = [string] $flow.workflowid
if ([int] $flow.statecode -eq 1) {
    # statecode/statuscode can still hide an ActiveUnpublished draft. Publish
    # this one named flow before deactivation so the subsequent PATCH remains
    # valid even when Dataverse reports statuscode=2.
    Publish-WorkflowDraft -Headers $headers -WorkflowId $workflowId
    Invoke-DataversePatch -Headers $headers -Path "workflows($workflowId)" -Body ([ordered]@{
        statecode = 0
        statuscode = 1
    })
}

Invoke-DataversePatch -Headers $headers -Path "workflows($workflowId)" -Body ([ordered]@{
    clientdata = ($clientData | ConvertTo-Json -Depth 100 -Compress)
})
Invoke-DataversePatch -Headers $headers -Path "workflows($workflowId)" -Body ([ordered]@{
    statecode = 1
    statuscode = 2
})
Publish-WorkflowDraft -Headers $headers -WorkflowId $workflowId
$publishedMessage = if ($SuccessNotificationSource -eq 'Cloud') { "Publicado con tres notificaciones de Teams: $FlowName" } else { "Publicado con inicio/error Cloud; el resumen exitoso lo publica PAD: $FlowName" }
Write-Output $publishedMessage
