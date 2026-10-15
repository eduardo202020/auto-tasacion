[CmdletBinding()]
param(
    [switch] $Activate,
    [switch] $DryRun,
    [switch] $EmitDefinitionJson,
    [switch] $ValidateOneDriveFolderIds,
    [string[]] $FlowName,
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_]*$')]
    [string] $SolutionUniqueName = 'autoTasacion',
    [string] $LocationsConfigPath,
    [string] $TeamsNotificationsConfigPath = $env:AUTOTASACION_TEAMS_NOTIFICATIONS_CONFIG,
    [string] $OneDriveBaseFolder = $env:AUTOTASACION_ONEDRIVE_BASE_FOLDER,
    [string] $PdfFolderId = $env:AUTOTASACION_PDFS_FOLDER_ID,
    [string] $ControlFolderId = $env:AUTOTASACION_CONTROLS_FOLDER_ID,
    [string] $LegacyControlFolderId = $env:AUTOTASACION_LEGACY_CONTROLS_FOLDER_ID
)

$ErrorActionPreference = 'Stop'

if ($Activate -and $DryRun) {
    throw '-Activate y -DryRun no se pueden usar juntos.'
}
if ($Activate -and $EmitDefinitionJson) {
    throw '-Activate y -EmitDefinitionJson no se pueden usar juntos.'
}

# An explicit activation is the only path that may change Dataverse.  A call
# without -Activate is intentionally a local plan, preserving existing flows.
$script:IsLocalPlan = [bool] ($DryRun -or -not $Activate)

# This script creates or updates mass-processing flows as solution-aware
# components. No document content or control token is written to this repository.
$DataverseUrl = 'https://org9a4ef0e0.crm4.dynamics.com'
$EnvironmentId = 'Default-3048dc87-43f0-4100-9acb-ae1971c79395'
$ServiceUrl = 'https://demo-tasaciones-ia-h75cd5qm2q-nn.a.run.app'

if ([string]::IsNullOrWhiteSpace($LocationsConfigPath)) {
    $LocationsConfigPath = Join-Path $PSScriptRoot '..\..\config\automation-locations.json'
}
$LocationsConfigPath = (Resolve-Path -LiteralPath $LocationsConfigPath).Path
$AutomationLocations = Get-Content -LiteralPath $LocationsConfigPath -Raw | ConvertFrom-Json
if ($AutomationLocations.schema_version -ne 1 -or $AutomationLocations.automation -ne 'auto-tasacion') {
    throw 'El archivo de ubicaciones no corresponde a auto-tasacion schema_version=1.'
}

# Teams is deliberately opt-in and configured outside Git.  The local file
# identifies the solution connection reference and the existing group chat;
# it contains no content from lots, PDFs, or Excel workbooks.
$script:TeamsNotifications = $null
if (-not [string]::IsNullOrWhiteSpace($TeamsNotificationsConfigPath)) {
    if (-not (Test-Path -LiteralPath $TeamsNotificationsConfigPath -PathType Leaf)) {
        throw "No se encontro la configuracion local de Teams: $TeamsNotificationsConfigPath"
    }
    $TeamsNotificationsConfigPath = (Resolve-Path -LiteralPath $TeamsNotificationsConfigPath).Path
    $teamsConfig = Get-Content -LiteralPath $TeamsNotificationsConfigPath -Raw | ConvertFrom-Json
    if ($teamsConfig.schema_version -ne 1 -or $teamsConfig.automation -ne 'auto-tasacion') {
        throw 'La configuracion local de Teams no corresponde a auto-tasacion schema_version=1.'
    }
    if ($teamsConfig.enabled -eq $true) {
        $referenceLogicalName = [string] $teamsConfig.connection.reference_logical_name
        $groupChatId = [string] $teamsConfig.destination.group_chat_id
        if ($referenceLogicalName -notmatch '^[A-Za-z][A-Za-z0-9_]*$') {
            throw 'connection.reference_logical_name de Teams no es un nombre logico valido.'
        }
        if ($groupChatId -notmatch '^19:[^\s]+@thread\.v2$') {
            throw 'destination.group_chat_id de Teams debe ser el identificador 19:...@thread.v2 de un chat grupal existente.'
        }
        $script:TeamsNotifications = [ordered]@{
            ReferenceLogicalName = $referenceLogicalName
            GroupChatId = $groupChatId
        }
    }
}

function Normalize-OneDriveLogicalPath {
    param([Parameter(Mandatory)] [string] $Path, [Parameter(Mandatory)] [string] $Label)
    $value = $Path.Trim().Replace('\', '/')
    if (-not $value.StartsWith('/') -or $value -match '(^|/)\.\.($|/)' -or $value -eq '/') {
        throw "$Label debe ser una ruta lógica absoluta sin '..'."
    }
    return '/' + (($value -split '/' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join '/')
}

function Get-OneDriveSubfolderName {
    param([Parameter(Mandatory)] [string] $Name, [Parameter(Mandatory)] [string] $Label)
    $value = $Name.Trim()
    if ([string]::IsNullOrWhiteSpace($value) -or $value -match '[\\/]' -or $value -in @('.', '..')) {
        throw "$Label debe ser un nombre de subcarpeta, no una ruta."
    }
    return $value
}

function Assert-OneDriveFolderId {
    param([string] $FolderId, [Parameter(Mandatory)] [string] $LogicalPath, [Parameter(Mandatory)] [string] $EnvironmentVariable)
    if ([string]::IsNullOrWhiteSpace($FolderId)) {
        throw "$EnvironmentVariable es obligatorio para la carpeta $LogicalPath. Obtenga el ID con la conexión OneDrive que desplegará el flujo."
    }
    $value = $FolderId.Trim()
    if ($value.Length -lt 20 -or $value -match '[\\/\s]') {
        throw "$EnvironmentVariable no parece un folderId opaco válido para $LogicalPath."
    }
    return $value
}

$BaseFolderOverridden = -not [string]::IsNullOrWhiteSpace($OneDriveBaseFolder)
if (-not $BaseFolderOverridden) {
    $OneDriveBaseFolder = [string] $AutomationLocations.onedrive.base_folder
}
$OneDriveBaseFolder = Normalize-OneDriveLogicalPath -Path $OneDriveBaseFolder -Label 'onedrive.base_folder'
$PdfSubfolder = Get-OneDriveSubfolderName -Name ([string] $AutomationLocations.onedrive.subfolders.pdfs) -Label 'onedrive.subfolders.pdfs'
$ControlSubfolder = Get-OneDriveSubfolderName -Name ([string] $AutomationLocations.onedrive.subfolders.controls) -Label 'onedrive.subfolders.controls'
$ArchiveSubfolder = Get-OneDriveSubfolderName -Name ([string] $AutomationLocations.onedrive.subfolders.archives) -Label 'onedrive.subfolders.archives'
$SourceFolder = "$OneDriveBaseFolder/$PdfSubfolder"
$ControlFolder = "$OneDriveBaseFolder/$ControlSubfolder"
$ArchiveFolder = "$OneDriveBaseFolder/$ArchiveSubfolder"
# The two recurrent migration flows historically stored control JSON files in
# the PDFs folder. This is a folder mapping, never a PDF item identifier.
$LegacyControlFolder = $SourceFolder
$ResultFolderInput = if ($BaseFolderOverridden) { $OneDriveBaseFolder } else { [string] $AutomationLocations.onedrive.result_folder }
$ResultFolder = Normalize-OneDriveLogicalPath -Path $ResultFolderInput -Label 'onedrive.result_folder'
if ($ResultFolder -ne $OneDriveBaseFolder) {
    throw 'onedrive.result_folder debe coincidir con la raíz lógica de auto-tasaciones.'
}

# Folder IDs are intentionally supplied at deployment time. A move in OneDrive
# can preserve an ID, but only the active connection can prove its mapping.
# The new event controls and the historical recurrent controls must never share
# a folder ID, or both processing routes could react to the same JSON.
if (-not [string]::IsNullOrWhiteSpace($ControlFolderId) -and
    -not [string]::IsNullOrWhiteSpace($LegacyControlFolderId) -and
    $ControlFolderId.Trim() -eq $LegacyControlFolderId.Trim()) {
    throw 'AUTOTASACION_CONTROLS_FOLDER_ID y AUTOTASACION_LEGACY_CONTROLS_FOLDER_ID deben identificar carpetas distintas.'
}
$OneDriveConnectionId = 'shared-onedriveforbu-192895c8-7959-4901-bdd9-0dd1cc6a1c6f'
$OneDriveConnectionReference = 'tasatest_sharedonedriveforbusiness_132da'
$OneDriveConnectionReferenceId = '2f2b17a0-68c2-f111-aaaf-7ced8d92a1ed'
$Gcloud = 'C:\Users\jhglazar\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'

if ($ValidateOneDriveFolderIds) {
    # This is deliberately offline: only metadata from the active OneDrive
    # connection can prove the remote ID-to-path mapping. The preflight blocks
    # malformed or missing deployment-time values before authentication or any
    # Dataverse mutation is attempted.
    $validatedPdfFolderId = Assert-OneDriveFolderId -FolderId $PdfFolderId -LogicalPath $SourceFolder -EnvironmentVariable 'AUTOTASACION_PDFS_FOLDER_ID'
    $validatedControlFolderId = Assert-OneDriveFolderId -FolderId $ControlFolderId -LogicalPath $ControlFolder -EnvironmentVariable 'AUTOTASACION_CONTROLS_FOLDER_ID'
    $validatedLegacyControlFolderId = if ([string]::IsNullOrWhiteSpace($LegacyControlFolderId)) {
        $null
    }
    else {
        Assert-OneDriveFolderId -FolderId $LegacyControlFolderId -LogicalPath $LegacyControlFolder -EnvironmentVariable 'AUTOTASACION_LEGACY_CONTROLS_FOLDER_ID'
    }

    [pscustomobject]@{
        OneDriveBaseFolder = $OneDriveBaseFolder
        PdfsLogicalPath = $SourceFolder
        PdfsFolderId = $validatedPdfFolderId
        ControlsLogicalPath = $ControlFolder
        ControlsFolderId = $validatedControlFolderId
        ArchivesLogicalPath = $ArchiveFolder
        LegacyControlsLogicalPath = $LegacyControlFolder
        LegacyControlsFolderId = $validatedLegacyControlFolderId
        RemoteMappingVerified = $false
    } | Format-List
    Write-Warning 'La validación es local. Confirme la relación ID/ruta con metadata de la conexión OneDrive antes de desplegar.'
    return
}

$script:DataverseHeaders = $null

function Get-DataverseHeaders {
    if ($null -ne $script:DataverseHeaders) {
        return $script:DataverseHeaders
    }
    $token = Get-MsalToken `
        -ClientId '51f81489-12ee-4a9e-aaae-a2591f45987d' `
        -TenantId 'organizations' `
        -RedirectUri 'http://localhost' `
        -Scopes "$DataverseUrl/.default" `
        -Interactive `
        -LoginHint 'mailbox_27530@emeal.nttdata.com' `
        -Timeout ([TimeSpan]::FromMinutes(5))

    $script:DataverseHeaders = @{
        Authorization = "Bearer $($token.AccessToken)"
        Accept = 'application/json'
        'Content-Type' = 'application/json'
        'OData-MaxVersion' = '4.0'
        'OData-Version' = '4.0'
    }
    return $script:DataverseHeaders
}

function Invoke-DataverseRequest {
    param(
        [Parameter(Mandatory)] [string] $Method,
        [Parameter(Mandatory)] [string] $Path,
        [object] $Body
    )

    $headers = Get-DataverseHeaders
    $request = [System.Net.Http.HttpRequestMessage]::new(
        [System.Net.Http.HttpMethod]::new($Method),
        "$DataverseUrl/api/data/v9.2/$Path"
    )
    foreach ($entry in $headers.GetEnumerator()) {
        if ($entry.Key -ne 'Content-Type') {
            $request.Headers.TryAddWithoutValidation($entry.Key, [string] $entry.Value) | Out-Null
        }
    }
    if ($null -ne $Body) {
        $json = if ($Body -is [string]) { $Body } else { $Body | ConvertTo-Json -Depth 100 -Compress }
        $request.Content = [System.Net.Http.StringContent]::new($json, [System.Text.Encoding]::UTF8, 'application/json')
    }

    $client = [System.Net.Http.HttpClient]::new()
    try {
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $content = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            throw "Dataverse $Method $Path devolvió HTTP $([int]$response.StatusCode): $content"
        }
        $entityId = if ($response.Headers.Contains('OData-EntityId')) {
            $response.Headers.GetValues('OData-EntityId') | Select-Object -First 1
        }
        else {
            $null
        }
        return [pscustomobject]@{
            StatusCode = [int] $response.StatusCode
            Body = $content
            EntityId = $entityId
        }
    }
    finally {
        $client.Dispose()
        $request.Dispose()
    }
}

function Get-ControlToken {
    if ($script:IsLocalPlan) {
        # A plan still builds every definition but never invokes gcloud or reads
        # Secret Manager. The placeholder is only serialized in memory/output.
        return '__LOCAL_PLAN_CONTROL_TOKEN__'
    }
    $value = (& $Gcloud secrets versions access latest --secret 'batch-control-api-token' --project 'project-fe2e4c6a-b528-4bcf-aa1').Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw 'No se pudo obtener el token de control desde Secret Manager.'
    }
    return $value
}

function New-BaseDefinition {
    param(
        [Parameter(Mandatory)] [hashtable] $Triggers,
        [Parameter(Mandatory)] [hashtable] $Actions,
        [hashtable] $ConnectionReferences = @{}
    )

    return [ordered]@{
        '$schema' = 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
        contentVersion = '1.0.0.0'
        parameters = [ordered]@{
            '$connections' = [ordered]@{ defaultValue = @{}; type = 'Object' }
            '$authentication' = [ordered]@{ defaultValue = @{}; type = 'SecureObject' }
        }
        triggers = $Triggers
        actions = $Actions
    }
}

function New-PowerAppsTrigger {
    param([Parameter(Mandatory)] [string] $Title)
    return [ordered]@{
        manual = [ordered]@{
            type = 'Request'
            kind = 'PowerAppV2'
            inputs = [ordered]@{
                schema = [ordered]@{
                    type = 'object'
                    properties = [ordered]@{
                        text = [ordered]@{
                            title = $Title
                            type = 'string'
                            'x-ms-dynamically-added' = $true
                            description = $Title
                        }
                    }
                    required = @('text')
                }
            }
        }
    }
}

function New-RecurrenceTrigger {
    return [ordered]@{
        recurrence = [ordered]@{
            type = 'Recurrence'
            recurrence = [ordered]@{
                frequency = 'Minute'
                interval = 5
                timeZone = 'SA Pacific Standard Time'
            }
        }
    }
}

function New-OneDriveControlCreatedTrigger {
    param([Parameter(Mandatory)] [string] $FolderId)

    $FolderId = Assert-OneDriveFolderId -FolderId $FolderId -LogicalPath $ControlFolder -EnvironmentVariable 'AUTOTASACION_CONTROLS_FOLDER_ID'

    # OneDrive for Business: OnNewFilesV2 is "When a file is created
    # (properties only)". In this connection its body is the array of metadata
    # directly, so Split On must target triggerBody(). Each split execution then
    # receives one metadata object in triggerBody(), never PDF content.
    return [ordered]@{
        Al_crear_control_lote = [ordered]@{
            type = 'OpenApiConnection'
            # Connector polling configuration; it does not create a workflow
            # run when there is no new control. The business flow itself is
            # event-driven and has no Recurrence trigger.
            recurrence = [ordered]@{ frequency = 'Minute'; interval = 1 }
            splitOn = "@triggerBody()"
            inputs = [ordered]@{
                host = [ordered]@{
                    apiId = '/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness'
                    connectionName = 'shared_onedriveforbusiness'
                    operationId = 'OnNewFilesV2'
                }
                parameters = [ordered]@{
                    folderId = $FolderId
                    includeSubfolders = $false
                    maxFileCount = 1
                }
                authentication = "@parameters('`$authentication')"
            }
        }
    }
}

function New-InvokerOneDriveReference {
    return [ordered]@{
        shared_onedriveforbusiness = [ordered]@{
            runtimeSource = 'invoker'
            connection = [ordered]@{
                name = ''
                connectionReferenceLogicalName = $OneDriveConnectionReference
            }
            api = [ordered]@{ name = 'shared_onedriveforbusiness' }
        }
    }
}

function New-EmbeddedOneDriveReference {
    return [ordered]@{
        shared_onedriveforbusiness = [ordered]@{
            runtimeSource = 'embedded'
            connection = [ordered]@{
                name = $OneDriveConnectionId
                connectionReferenceLogicalName = $OneDriveConnectionReference
            }
            api = [ordered]@{ name = 'shared_onedriveforbusiness' }
        }
    }
}

function Add-TeamsConnectionReference {
    param([Parameter(Mandatory)] [hashtable] $ConnectionReferences)

    $result = [ordered]@{}
    foreach ($entry in $ConnectionReferences.GetEnumerator()) {
        $result[$entry.Key] = $entry.Value
    }
    if ($null -ne $script:TeamsNotifications) {
        $result.shared_teams = [ordered]@{
            runtimeSource = 'embedded'
            connection = [ordered]@{
                connectionReferenceLogicalName = $script:TeamsNotifications.ReferenceLogicalName
            }
            api = [ordered]@{ name = 'shared_teams' }
        }
    }
    return $result
}

function New-TeamsGroupChatNotification {
    param(
        [Parameter(Mandatory)] [string] $MessageBody,
        [hashtable] $RunAfter = @{}
    )

    if ($null -eq $script:TeamsNotifications) {
        throw 'Se intento crear una notificacion de Teams sin configuracion local habilitada.'
    }
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
                'body/recipient' = $script:TeamsNotifications.GroupChatId
                'body/messageBody' = $MessageBody
            }
            authentication = "@parameters('`$authentication')"
        }
    }
}

function Get-NotificationCompletionRunAfter {
    param([Parameter(Mandatory)] [string] $ActionName)
    return [ordered]@{
        $ActionName = @('Succeeded', 'Failed', 'Skipped', 'TimedOut')
    }
}

function New-OneDriveAction {
    param(
        [Parameter(Mandatory)] [string] $OperationId,
        [Parameter(Mandatory)] [hashtable] $Parameters,
        [hashtable] $RunAfter = @{},
        [switch] $Invoker
    )

    $authentication = if ($Invoker) {
        [ordered]@{
            value = "@json(decodeBase64(triggerOutputs().headers['X-MS-APIM-Tokens']))['`$ConnectionKey']"
            type = 'Raw'
        }
    }
    else {
        "@parameters('`$authentication')"
    }
    return [ordered]@{
        runAfter = $RunAfter
        type = 'OpenApiConnection'
        inputs = [ordered]@{
            host = [ordered]@{
                apiId = '/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness'
                connectionName = 'shared_onedriveforbusiness'
                operationId = $OperationId
            }
            parameters = $Parameters
            authentication = $authentication
        }
    }
}

function Get-ControlJsonContentExpression {
    # GetFileContentByPath is a binary connector operation. Power Automate
    # exposes the base64 payload in body.$content; ParseJson cannot receive the
    # application/octet-stream envelope directly.
    return '@json(base64ToString(outputs(''Obtener_control_lote'')?[''body'']?[''$content'']))'
}

function New-HttpAction {
    param(
        [Parameter(Mandatory)] [string] $Method,
        [Parameter(Mandatory)] [string] $Uri,
        [hashtable] $Headers = @{},
        [object] $Body,
        [hashtable] $RunAfter = @{},
        [switch] $Secure
    )

    $action = [ordered]@{
        runAfter = $RunAfter
        type = 'Http'
        inputs = [ordered]@{ method = $Method; uri = $Uri; headers = $Headers }
    }
    if ($null -ne $Body) { $action.inputs.body = $Body }
    if ($Secure) {
        $action.runtimeConfiguration = [ordered]@{ secureData = [ordered]@{ properties = @('inputs', 'outputs') } }
    }
    return $action
}

function New-FlowDefinition {
    param([Parameter(Mandatory)] [string] $Name)
    $controlToken = Get-ControlToken
    $controlHeaders = [ordered]@{
        'Content-Type' = 'application/json'
        'X-Batch-Control-Token' = $controlToken
    }

    switch ($Name) {
        'auto-tasacion-iniciar-lote' {
            $actions = [ordered]@{
                HTTP_Registrar_Lote = New-HttpAction -Method 'POST' -Uri "$ServiceUrl/v1/lotes" -Headers $controlHeaders -Body ([ordered]@{
                    carpeta_origen = $SourceFolder
                    archivos = "@json(triggerBody()?['text'])"
                }) -Secure
                Crear_control_lote = New-OneDriveAction -OperationId 'CreateFile' -Invoker -RunAfter ([ordered]@{ HTTP_Registrar_Lote = @('Succeeded') }) -Parameters ([ordered]@{
                    folderPath = $ControlFolder
                    name = "@concat('_autotasacion_lote_', body('HTTP_Registrar_Lote')?['id_lote'], '.json')"
                    body = '@concat(''{"id_lote":"'', body(''HTTP_Registrar_Lote'')?[''id_lote''], ''"}'')'
                })
                Responder_a_Power_Apps = [ordered]@{
                    runAfter = [ordered]@{ Crear_control_lote = @('Succeeded') }
                    type = 'Response'
                    kind = 'PowerApp'
                    inputs = [ordered]@{
                        statusCode = 200
                        body = [ordered]@{
                            id_lote = "@{body('HTTP_Registrar_Lote')?['id_lote']}"
                            estado = "@{body('HTTP_Registrar_Lote')?['estado']}"
                            fecha_inicio = "@{body('HTTP_Registrar_Lote')?['fecha_inicio']}"
                        }
                        schema = [ordered]@{
                            type = 'object'
                            properties = [ordered]@{
                                id_lote = [ordered]@{ title = 'IdLote'; 'x-ms-dynamically-added' = $true; type = 'string' }
                                estado = [ordered]@{ title = 'Estado'; 'x-ms-dynamically-added' = $true; type = 'string' }
                                fecha_inicio = [ordered]@{ title = 'FechaInicio'; 'x-ms-dynamically-added' = $true; type = 'string' }
                            }
                        }
                    }
                }
            }
            if ($null -ne $script:TeamsNotifications) {
                $actions.Notificar_lote_registrado = New-TeamsGroupChatNotification -RunAfter ([ordered]@{ Crear_control_lote = @('Succeeded') }) -MessageBody "@concat('Auto Tasaciones | lote ', body('HTTP_Registrar_Lote')?['id_lote'], ' registrado. PDFs seleccionados: ', string(length(json(triggerBody()?['text']))), '. Estado: ', body('HTTP_Registrar_Lote')?['estado'], '.')"
                # A notification outage must not leave Canvas waiting for the
                # response or roll back a correctly registered lot.
                $actions.Responder_a_Power_Apps.runAfter = Get-NotificationCompletionRunAfter -ActionName 'Notificar_lote_registrado'
            }
            return [ordered]@{ connectionReferences = Add-TeamsConnectionReference -ConnectionReferences (New-InvokerOneDriveReference); definition = New-BaseDefinition -Triggers (New-PowerAppsTrigger -Title 'SeleccionJson') -Actions $actions }
        }
        'auto-tasacion-consultar-lote' {
            $actions = [ordered]@{
                HTTP_Consultar_Lote = New-HttpAction -Method 'GET' -Uri "@concat('$ServiceUrl/v1/lotes/', triggerBody()?['text'])" -Headers $controlHeaders -Secure
                Responder_a_Power_Apps = [ordered]@{
                    runAfter = [ordered]@{ HTTP_Consultar_Lote = @('Succeeded') }
                    type = 'Response'; kind = 'PowerApp'
                    inputs = [ordered]@{
                        statusCode = 200
                        # Keep the Power Apps contract typed. The loader's
                        # per-file metadata remains server-side; the app only
                        # needs the batch state and safe aggregate progress.
                        body = [ordered]@{
                            id_lote = "@body('HTTP_Consultar_Lote')?['id_lote']"
                            estado = "@body('HTTP_Consultar_Lote')?['estado']"
                            mensaje = "@body('HTTP_Consultar_Lote')?['mensaje']"
                            total_pdfs = "@body('HTTP_Consultar_Lote')?['total_pdfs']"
                            pdfs_cargados = "@body('HTTP_Consultar_Lote')?['pdfs_cargados']"
                            pdfs_procesados = "@body('HTTP_Consultar_Lote')?['pdfs_procesados']"
                            pdfs_fallidos = "@body('HTTP_Consultar_Lote')?['pdfs_fallidos']"
                            resultado_disponible = "@body('HTTP_Consultar_Lote')?['resultado_disponible']"
                            fecha_inicio = "@body('HTTP_Consultar_Lote')?['fecha_inicio']"
                            fecha_fin = "@body('HTTP_Consultar_Lote')?['fecha_fin']"
                            duracion_segundos = "@body('HTTP_Consultar_Lote')?['duracion_segundos']"
                        }
                        schema = [ordered]@{
                            type = 'object'
                            properties = [ordered]@{
                                id_lote = [ordered]@{ title = 'IdLote'; 'x-ms-dynamically-added' = $true; type = 'string' }
                                estado = [ordered]@{ title = 'Estado'; 'x-ms-dynamically-added' = $true; type = 'string' }
                                mensaje = [ordered]@{ title = 'Mensaje'; 'x-ms-dynamically-added' = $true; type = 'string' }
                                total_pdfs = [ordered]@{ title = 'TotalPdfs'; 'x-ms-dynamically-added' = $true; type = 'integer' }
                                pdfs_cargados = [ordered]@{ title = 'PdfsCargados'; 'x-ms-dynamically-added' = $true; type = 'integer' }
                                pdfs_procesados = [ordered]@{ title = 'PdfsProcesados'; 'x-ms-dynamically-added' = $true; type = 'integer' }
                                pdfs_fallidos = [ordered]@{ title = 'PdfsFallidos'; 'x-ms-dynamically-added' = $true; type = 'integer' }
                                resultado_disponible = [ordered]@{ title = 'ResultadoDisponible'; 'x-ms-dynamically-added' = $true; type = 'boolean' }
                                fecha_inicio = [ordered]@{ title = 'FechaInicio'; 'x-ms-dynamically-added' = $true; type = 'string' }
                                fecha_fin = [ordered]@{ title = 'FechaFin'; 'x-ms-dynamically-added' = $true; type = 'string' }
                                duracion_segundos = [ordered]@{ title = 'DuracionSegundos'; 'x-ms-dynamically-added' = $true; type = 'integer' }
                            }
                            required = @('id_lote', 'estado', 'total_pdfs', 'pdfs_cargados', 'pdfs_procesados', 'pdfs_fallidos', 'resultado_disponible', 'fecha_inicio', 'fecha_fin', 'duracion_segundos')
                        }
                    }
                }
            }
            return [ordered]@{ connectionReferences = @{}; definition = New-BaseDefinition -Triggers (New-PowerAppsTrigger -Title 'IdLote') -Actions $actions }
        }
        'auto-tasacion-orquestar-lote' {
            # This flow is intentionally event-driven. Its dedicated OneDrive
            # folder contains only small control JSON files, never PDFs.
            $actions = [ordered]@{
                Inicializar_estado_lote = [ordered]@{
                    runAfter = @{}
                    type = 'InitializeVariable'
                    inputs = [ordered]@{ variables = @([ordered]@{ name = 'estado_lote'; type = 'string'; value = '' }) }
                }
                Inicializar_resultado_disponible = [ordered]@{
                    runAfter = [ordered]@{ Inicializar_estado_lote = @('Succeeded') }
                    type = 'InitializeVariable'
                    inputs = [ordered]@{ variables = @([ordered]@{ name = 'resultado_disponible'; type = 'boolean'; value = $false }) }
                }
                Inicializar_espera_segundos = [ordered]@{
                    runAfter = [ordered]@{ Inicializar_resultado_disponible = @('Succeeded') }
                    type = 'InitializeVariable'
                    inputs = [ordered]@{ variables = @([ordered]@{ name = 'espera_segundos'; type = 'integer'; value = 30 }) }
                }
                Inicializar_intentos_espera = [ordered]@{
                    runAfter = [ordered]@{ Inicializar_espera_segundos = @('Succeeded') }
                    type = 'InitializeVariable'
                    inputs = [ordered]@{ variables = @([ordered]@{ name = 'intentos_espera'; type = 'integer'; value = 0 }) }
                }
                Es_control_de_lote = [ordered]@{
                    runAfter = [ordered]@{ Inicializar_intentos_espera = @('Succeeded') }
                    type = 'If'
                    expression = "@and(startsWith(triggerBody()?['Name'], '_autotasacion_lote_'), endsWith(toLower(triggerBody()?['Name']), '.json'), equals(triggerBody()?['IsFolder'], false))"
                    actions = [ordered]@{
                        Obtener_control_lote = New-OneDriveAction -OperationId 'GetFileContentByPath' -Parameters ([ordered]@{ path = "@triggerBody()?['Path']" })
                        Leer_control_lote = [ordered]@{
                            runAfter = [ordered]@{ Obtener_control_lote = @('Succeeded') }
                            type = 'ParseJson'
                            inputs = [ordered]@{
                                content = Get-ControlJsonContentExpression
                                schema = [ordered]@{ type = 'object'; properties = [ordered]@{ id_lote = [ordered]@{ type = 'string' } }; required = @('id_lote') }
                            }
                        }
                        Reclamar_orquestacion = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/orquestacion/reclamar')" -Headers $controlHeaders -Body ([ordered]@{
                            id_ejecucion = "@workflow()?['run']?['name']"
                        }) -RunAfter ([ordered]@{ Leer_control_lote = @('Succeeded') }) -Secure
                        Es_propietario_del_lote = [ordered]@{
                            runAfter = [ordered]@{ Reclamar_orquestacion = @('Succeeded') }
                            type = 'If'
                            expression = "@equals(body('Reclamar_orquestacion')?['reclamado'], true)"
                            actions = [ordered]@{
                                HTTP_Consultar_Lote_inicial = New-HttpAction -Method 'GET' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'])" -Headers $controlHeaders -Secure
                                Lote_requiere_carga = [ordered]@{
                                    runAfter = [ordered]@{ HTTP_Consultar_Lote_inicial = @('Succeeded') }
                                    type = 'If'
                                    expression = "@or(equals(body('HTTP_Consultar_Lote_inicial')?['estado'], 'RECIBIDO'), equals(body('HTTP_Consultar_Lote_inicial')?['estado'], 'CARGANDO_PDFS'), equals(body('HTTP_Consultar_Lote_inicial')?['estado'], 'LISTO_PARA_PROCESAR'))"
                                    actions = [ordered]@{
                                        Filtrar_archivos_por_cargar = [ordered]@{
                                            runAfter = @{}
                                            type = 'Query'
                                            inputs = [ordered]@{
                                                from = "@body('HTTP_Consultar_Lote_inicial')?['archivos']"
                                                # SUBIENDO is an interrupted individual transfer. It is
                                                # safe to resume because the ticket and confirmation APIs
                                                # remain idempotent for the same manifest entry.
                                                where = "@or(equals(item()?['estado'], 'PENDIENTE'), equals(item()?['estado'], 'SUBIENDO'))"
                                            }
                                        }
                                        Por_cada_archivo = [ordered]@{
                                            runAfter = [ordered]@{ Filtrar_archivos_por_cargar = @('Succeeded') }
                                            type = 'Foreach'
                                            foreach = "@body('Filtrar_archivos_por_cargar')"
                                            actions = [ordered]@{
                                                Renovar_claim_antes_de_archivo = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/orquestacion/renovar')" -Headers $controlHeaders -Body ([ordered]@{ id_ejecucion = "@workflow()?['run']?['name']" }) -Secure
                                                Metadatos_iniciales = New-OneDriveAction -OperationId 'GetFileMetadataByPath' -RunAfter ([ordered]@{ Renovar_claim_antes_de_archivo = @('Succeeded') }) -Parameters ([ordered]@{ path = "@concat('$SourceFolder/', items('Por_cada_archivo')?['nombre'])" })
                                                Solicitar_ticket_de_carga = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/archivos/', items('Por_cada_archivo')?['id_archivo'], '/upload-ticket')" -Headers $controlHeaders -Body @{} -RunAfter ([ordered]@{ Metadatos_iniciales = @('Succeeded') }) -Secure
                                                Carga_PDF_requerida = [ordered]@{
                                                    runAfter = [ordered]@{ Solicitar_ticket_de_carga = @('Succeeded') }
                                                    type = 'If'
                                                    expression = "@equals(body('Solicitar_ticket_de_carga')?['requiere_carga'], true)"
                                                    actions = [ordered]@{
                                                        Obtener_contenido_del_PDF = New-OneDriveAction -OperationId 'GetFileContentByPath' -Parameters ([ordered]@{ path = "@concat('$SourceFolder/', items('Por_cada_archivo')?['nombre'])" })
                                                        Subir_PDF_a_GCS = New-HttpAction -Method 'PUT' -Uri "@body('Solicitar_ticket_de_carga')?['url_carga']" -Headers ([ordered]@{ 'Content-Type' = 'application/pdf' }) -Body "@body('Obtener_contenido_del_PDF')" -RunAfter ([ordered]@{ Obtener_contenido_del_PDF = @('Succeeded') }) -Secure
                                                    }
                                                    else = [ordered]@{ actions = @{} }
                                                }
                                                Metadatos_finales = New-OneDriveAction -OperationId 'GetFileMetadataByPath' -RunAfter ([ordered]@{ Carga_PDF_requerida = @('Succeeded') }) -Parameters ([ordered]@{ path = "@concat('$SourceFolder/', items('Por_cada_archivo')?['nombre'])" })
                                                Confirmar_carga = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/archivos/', items('Por_cada_archivo')?['id_archivo'], '/confirmar')" -Headers $controlHeaders -Body ([ordered]@{ etag_confirmado = "@outputs('Metadatos_finales')?['body/ETag']" }) -RunAfter ([ordered]@{ Metadatos_finales = @('Succeeded') }) -Secure
                                            }
                                            runtimeConfiguration = [ordered]@{ concurrency = [ordered]@{ repetitions = 1 } }
                                        }
                                        Renovar_claim_antes_de_iniciar_job = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/orquestacion/renovar')" -Headers $controlHeaders -Body ([ordered]@{ id_ejecucion = "@workflow()?['run']?['name']" }) -RunAfter ([ordered]@{ Por_cada_archivo = @('Succeeded') }) -Secure
                                        HTTP_Iniciar_Job = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/iniciar')" -Headers $controlHeaders -Body @{} -RunAfter ([ordered]@{ Renovar_claim_antes_de_iniciar_job = @('Succeeded') }) -Secure
                                    }
                                    else = [ordered]@{ actions = @{} }
                                }
                                HTTP_Consultar_Lote_para_espera = New-HttpAction -Method 'GET' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'])" -Headers $controlHeaders -RunAfter ([ordered]@{ Lote_requiere_carga = @('Succeeded') }) -Secure
                                Asignar_estado_lote_inicial = [ordered]@{
                                    runAfter = [ordered]@{ HTTP_Consultar_Lote_para_espera = @('Succeeded') }
                                    type = 'SetVariable'
                                    inputs = [ordered]@{ name = 'estado_lote'; value = "@body('HTTP_Consultar_Lote_para_espera')?['estado']" }
                                }
                                Asignar_resultado_disponible_inicial = [ordered]@{
                                    runAfter = [ordered]@{ Asignar_estado_lote_inicial = @('Succeeded') }
                                    type = 'SetVariable'
                                    inputs = [ordered]@{ name = 'resultado_disponible'; value = "@body('HTTP_Consultar_Lote_para_espera')?['resultado_disponible']" }
                                }
                                Reiniciar_espera_segundos = [ordered]@{
                                    runAfter = [ordered]@{ Asignar_resultado_disponible_inicial = @('Succeeded') }
                                    type = 'SetVariable'
                                    inputs = [ordered]@{ name = 'espera_segundos'; value = 30 }
                                }
                                Reiniciar_intentos_espera = [ordered]@{
                                    runAfter = [ordered]@{ Reiniciar_espera_segundos = @('Succeeded') }
                                    type = 'SetVariable'
                                    inputs = [ordered]@{ name = 'intentos_espera'; value = 0 }
                                }
                                Esperar_resultado_del_lote = [ordered]@{
                                    runAfter = [ordered]@{ Reiniciar_intentos_espera = @('Succeeded') }
                                    type = 'Until'
                                    expression = "@or(equals(variables('estado_lote'), 'COMPLETADO'), equals(variables('estado_lote'), 'ENTREGADO'), equals(variables('estado_lote'), 'FALLIDO'), equals(variables('estado_lote'), 'FALLIDO_ORIGEN_CAMBIO'))"
                                    limit = [ordered]@{ count = 30; timeout = 'PT2H' }
                                    actions = [ordered]@{
                                        Esperar_con_backoff = [ordered]@{
                                            runAfter = @{}
                                            type = 'Wait'
                                            inputs = [ordered]@{
                                                interval = [ordered]@{
                                                    count = "@variables('espera_segundos')"
                                                    unit = 'Second'
                                                }
                                            }
                                        }
                                        Renovar_claim_en_espera = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/orquestacion/renovar')" -Headers $controlHeaders -Body ([ordered]@{ id_ejecucion = "@workflow()?['run']?['name']" }) -RunAfter ([ordered]@{ Esperar_con_backoff = @('Succeeded') }) -Secure
                                        HTTP_Consultar_Lote_en_espera = New-HttpAction -Method 'GET' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'])" -Headers $controlHeaders -RunAfter ([ordered]@{ Renovar_claim_en_espera = @('Succeeded') }) -Secure
                                        Actualizar_estado_lote = [ordered]@{
                                            runAfter = [ordered]@{ HTTP_Consultar_Lote_en_espera = @('Succeeded') }
                                            type = 'SetVariable'
                                            inputs = [ordered]@{ name = 'estado_lote'; value = "@body('HTTP_Consultar_Lote_en_espera')?['estado']" }
                                        }
                                        Actualizar_resultado_disponible = [ordered]@{
                                            runAfter = [ordered]@{ Actualizar_estado_lote = @('Succeeded') }
                                            type = 'SetVariable'
                                            inputs = [ordered]@{ name = 'resultado_disponible'; value = "@body('HTTP_Consultar_Lote_en_espera')?['resultado_disponible']" }
                                        }
                                        Incrementar_intentos_espera = [ordered]@{
                                            runAfter = [ordered]@{ Actualizar_resultado_disponible = @('Succeeded') }
                                            type = 'IncrementVariable'
                                            inputs = [ordered]@{ name = 'intentos_espera'; value = 1 }
                                        }
                                        Aumentar_espera_hasta_cinco_minutos = [ordered]@{
                                            runAfter = [ordered]@{ Incrementar_intentos_espera = @('Succeeded') }
                                            type = 'SetVariable'
                                            inputs = [ordered]@{
                                                name = 'espera_segundos'
                                                # SetVariable cannot read its own target variable. The step is
                                                # calculated from the independent attempt counter: 30, 60, 120,
                                                # then 300 seconds for subsequent polls.
                                                value = "@if(lessOrEquals(variables('intentos_espera'), 1), 60, if(equals(variables('intentos_espera'), 2), 120, 300))"
                                            }
                                        }
                                    }
                                }
                                Lote_alcanzo_estado_terminal = [ordered]@{
                                    runAfter = [ordered]@{ Esperar_resultado_del_lote = @('Succeeded') }
                                    type = 'If'
                                    expression = "@or(equals(variables('estado_lote'), 'COMPLETADO'), equals(variables('estado_lote'), 'ENTREGADO'), equals(variables('estado_lote'), 'FALLIDO'), equals(variables('estado_lote'), 'FALLIDO_ORIGEN_CAMBIO'))"
                                    actions = [ordered]@{
                                        Lote_completado_con_resultado = [ordered]@{
                                            runAfter = @{}
                                            type = 'If'
                                            expression = "@and(equals(variables('estado_lote'), 'COMPLETADO'), equals(variables('resultado_disponible'), true))"
                                            actions = [ordered]@{
                                                Renovar_claim_antes_de_entrega = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/orquestacion/renovar')" -Headers $controlHeaders -Body ([ordered]@{ id_ejecucion = "@workflow()?['run']?['name']" }) -Secure
                                                # A previous run may have created the deterministic XLSX and failed before
                                                # confirming delivery. Search first so a recovery run confirms that exact
                                                # artifact instead of creating it again. FindFilesByPath returns an array.
                                                Buscar_excel_final_existente = New-OneDriveAction -OperationId 'FindFilesByPath' -RunAfter ([ordered]@{ Renovar_claim_antes_de_entrega = @('Succeeded') }) -Parameters ([ordered]@{
                                                    path = $ResultFolder
                                                    query = "@concat('^Resultado_Final_', body('Leer_control_lote')?['id_lote'], '\.xlsx$')"
                                                    # The connector exposes regular-expression matching with the
                                                    # `Pattern` enum value, rather than its display label.
                                                    findMode = 'Pattern'
                                                    maxFileCount = 1
                                                })
                                                Excel_final_ya_existe = [ordered]@{
                                                    runAfter = [ordered]@{ Buscar_excel_final_existente = @('Succeeded') }
                                                    type = 'If'
                                                    expression = "@greater(length(body('Buscar_excel_final_existente')), 0)"
                                                    actions = [ordered]@{
                                                        Confirmar_entrega_existente = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/entrega')" -Headers $controlHeaders -Body @{} -Secure
                                                        Eliminar_control_lote_existente = New-OneDriveAction -OperationId 'DeleteFile' -RunAfter ([ordered]@{ Confirmar_entrega_existente = @('Succeeded') }) -Parameters ([ordered]@{ id = "@triggerBody()?['Id']" })
                                                    }
                                                    else = [ordered]@{
                                                        actions = [ordered]@{
                                                            Solicitar_ticket_resultado = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/resultado-ticket')" -Headers $controlHeaders -Body @{} -Secure
                                                            Descargar_resultado = New-HttpAction -Method 'GET' -Uri "@body('Solicitar_ticket_resultado')?['url_descarga']" -RunAfter ([ordered]@{ Solicitar_ticket_resultado = @('Succeeded') }) -Secure
                                                            Crear_excel_final = New-OneDriveAction -OperationId 'CreateFile' -RunAfter ([ordered]@{ Descargar_resultado = @('Succeeded') }) -Parameters ([ordered]@{
                                                                folderPath = $ResultFolder
                                                                name = "@concat('Resultado_Final_', body('Leer_control_lote')?['id_lote'], '.xlsx')"
                                                                body = "@body('Descargar_resultado')"
                                                            })
                                                            Confirmar_entrega_nuevo = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/entrega')" -Headers $controlHeaders -Body @{} -RunAfter ([ordered]@{ Crear_excel_final = @('Succeeded') }) -Secure
                                                            Eliminar_control_lote_nuevo = New-OneDriveAction -OperationId 'DeleteFile' -RunAfter ([ordered]@{ Confirmar_entrega_nuevo = @('Succeeded') }) -Parameters ([ordered]@{ id = "@triggerBody()?['Id']" })
                                                        }
                                                    }
                                                }
                                            }
                                            else = [ordered]@{ actions = @{} }
                                        }
                                    }
                                    else = [ordered]@{
                                        actions = [ordered]@{
                                            Liberar_claim_por_timeout = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/orquestacion/liberar')" -Headers $controlHeaders -Body ([ordered]@{
                                                id_ejecucion = "@workflow()?['run']?['name']"
                                                motivo = 'TIEMPO_DE_ESPERA_AGOTADO'
                                            }) -Secure
                                        }
                                    }
                                }
                            }
                            else = [ordered]@{
                                # If a prior owner reached ENTREGADO but stopped before deleting
                                # the control, a duplicate event safely performs only that cleanup.
                                actions = [ordered]@{
                                    Limpiar_control_de_lote_entregado = [ordered]@{
                                        runAfter = @{}
                                        type = 'If'
                                        expression = "@equals(body('Reclamar_orquestacion')?['estado'], 'ENTREGADO')"
                                        actions = [ordered]@{
                                            Eliminar_control_lote_entregado = New-OneDriveAction -OperationId 'DeleteFile' -Parameters ([ordered]@{ id = "@triggerBody()?['Id']" })
                                        }
                                        else = [ordered]@{ actions = @{} }
                                    }
                                }
                            }
                        }
                    }
                    else = [ordered]@{ actions = @{} }
                }
            }
            if ($null -ne $script:TeamsNotifications) {
                $ownerActions = $actions.Es_control_de_lote.actions.Es_propietario_del_lote.actions
                $terminalActions = $ownerActions.Lote_alcanzo_estado_terminal.actions
                $deliveryBranch = $terminalActions.Lote_completado_con_resultado
                $deliveryActions = $deliveryBranch.actions.Excel_final_ya_existe

                $existingDeliveryActions = $deliveryActions.actions
                $existingDeliveryActions.Notificar_excel_final_disponible_existente = New-TeamsGroupChatNotification -RunAfter ([ordered]@{ Confirmar_entrega_existente = @('Succeeded') }) -MessageBody "@concat('Auto Tasaciones | lote ', body('Leer_control_lote')?['id_lote'], ' entregado. Excel final disponible en OneDrive: Resultado_Final_', body('Leer_control_lote')?['id_lote'], '.xlsx.')"
                $existingDeliveryActions.Eliminar_control_lote_existente.runAfter = Get-NotificationCompletionRunAfter -ActionName 'Notificar_excel_final_disponible_existente'

                $newDeliveryActions = $deliveryActions.else.actions
                $newDeliveryActions.Notificar_excel_final_disponible_nuevo = New-TeamsGroupChatNotification -RunAfter ([ordered]@{ Confirmar_entrega_nuevo = @('Succeeded') }) -MessageBody "@concat('Auto Tasaciones | lote ', body('Leer_control_lote')?['id_lote'], ' entregado. Excel final disponible en OneDrive: Resultado_Final_', body('Leer_control_lote')?['id_lote'], '.xlsx.')"
                $newDeliveryActions.Eliminar_control_lote_nuevo.runAfter = Get-NotificationCompletionRunAfter -ActionName 'Notificar_excel_final_disponible_nuevo'

                $deliveryBranch.else.actions.Notificar_lote_con_error = New-TeamsGroupChatNotification -MessageBody "@concat('Auto Tasaciones | lote ', body('Leer_control_lote')?['id_lote'], ' requiere atencion. Estado: ', variables('estado_lote'), '.')"
                $ownerActions.Lote_alcanzo_estado_terminal.else.actions.Notificar_espera_agotada = New-TeamsGroupChatNotification -RunAfter ([ordered]@{ Liberar_claim_por_timeout = @('Succeeded', 'Failed', 'Skipped', 'TimedOut') }) -MessageBody "@concat('Auto Tasaciones | lote ', body('Leer_control_lote')?['id_lote'], ' requiere atencion: se agoto la espera de procesamiento. Estado observado: ', variables('estado_lote'), '.')"
            }
            return [ordered]@{
                connectionReferences = Add-TeamsConnectionReference -ConnectionReferences (New-EmbeddedOneDriveReference)
                definition = New-BaseDefinition -Triggers (New-OneDriveControlCreatedTrigger -FolderId $ControlFolderId) -Actions $actions
            }
        }
        'auto-tasacion-cargar-lotes' {
            $LegacyControlFolderId = Assert-OneDriveFolderId -FolderId $LegacyControlFolderId -LogicalPath $LegacyControlFolder -EnvironmentVariable 'AUTOTASACION_LEGACY_CONTROLS_FOLDER_ID'
            $actions = [ordered]@{
                Mostrar_controles_de_lote = New-OneDriveAction -OperationId 'ListFolderV2' -Parameters ([ordered]@{ id = $LegacyControlFolderId })
                Filtrar_controles_de_lote = [ordered]@{
                    runAfter = [ordered]@{ Mostrar_controles_de_lote = @('Succeeded') }
                    type = 'Query'
                    inputs = [ordered]@{
                        from = "@outputs('Mostrar_controles_de_lote')?['body/value']"
                        where = "@and(startsWith(item()?['Name'], '_autotasacion_lote_'), endsWith(toLower(item()?['Name']), '.json'))"
                    }
                }
                Por_cada_control = [ordered]@{
                    runAfter = [ordered]@{ Filtrar_controles_de_lote = @('Succeeded') }
                    type = 'Foreach'
                    foreach = "@body('Filtrar_controles_de_lote')"
                    actions = [ordered]@{
                        Obtener_control_lote = New-OneDriveAction -OperationId 'GetFileContentByPath' -Parameters ([ordered]@{ path = "@items('Por_cada_control')?['Path']" })
                        Leer_control_lote = [ordered]@{
                            runAfter = [ordered]@{ Obtener_control_lote = @('Succeeded') }
                            type = 'ParseJson'
                            inputs = [ordered]@{
                                content = Get-ControlJsonContentExpression
                                schema = [ordered]@{ type = 'object'; properties = [ordered]@{ id_lote = [ordered]@{ type = 'string' } }; required = @('id_lote') }
                            }
                        }
                        HTTP_Consultar_Lote = New-HttpAction -Method 'GET' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'])" -Headers $controlHeaders -RunAfter ([ordered]@{ Leer_control_lote = @('Succeeded') }) -Secure
                        Lote_requiere_carga = [ordered]@{
                            runAfter = [ordered]@{ HTTP_Consultar_Lote = @('Succeeded') }
                            type = 'If'
                            expression = "@or(equals(body('HTTP_Consultar_Lote')?['estado'], 'RECIBIDO'), equals(body('HTTP_Consultar_Lote')?['estado'], 'CARGANDO_PDFS'), equals(body('HTTP_Consultar_Lote')?['estado'], 'LISTO_PARA_PROCESAR'))"
                            actions = [ordered]@{
                                Filtrar_archivos_pendientes = [ordered]@{
                                    runAfter = @{}
                                    type = 'Query'
                                    inputs = [ordered]@{
                                        from = "@body('HTTP_Consultar_Lote')?['archivos']"
                                        where = "@equals(item()?['estado'], 'PENDIENTE')"
                                    }
                                }
                                Por_cada_archivo = [ordered]@{
                                    runAfter = [ordered]@{ Filtrar_archivos_pendientes = @('Succeeded') }
                                    type = 'Foreach'
                                    foreach = "@body('Filtrar_archivos_pendientes')"
                                    actions = [ordered]@{
                                        Metadatos_iniciales = New-OneDriveAction -OperationId 'GetFileMetadataByPath' -Parameters ([ordered]@{ path = "@concat('$SourceFolder/', items('Por_cada_archivo')?['nombre'])" })
                                        Solicitar_ticket_de_carga = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/archivos/', items('Por_cada_archivo')?['id_archivo'], '/upload-ticket')" -Headers $controlHeaders -Body @{} -RunAfter ([ordered]@{ Metadatos_iniciales = @('Succeeded') }) -Secure
                                        Obtener_contenido_del_PDF = New-OneDriveAction -OperationId 'GetFileContentByPath' -RunAfter ([ordered]@{ Solicitar_ticket_de_carga = @('Succeeded') }) -Parameters ([ordered]@{ path = "@concat('$SourceFolder/', items('Por_cada_archivo')?['nombre'])" })
                                        Subir_PDF_a_GCS = New-HttpAction -Method 'PUT' -Uri "@body('Solicitar_ticket_de_carga')?['url_carga']" -Headers ([ordered]@{ 'Content-Type' = 'application/pdf' }) -Body "@body('Obtener_contenido_del_PDF')" -RunAfter ([ordered]@{ Obtener_contenido_del_PDF = @('Succeeded') }) -Secure
                                        Metadatos_finales = New-OneDriveAction -OperationId 'GetFileMetadataByPath' -RunAfter ([ordered]@{ Subir_PDF_a_GCS = @('Succeeded') }) -Parameters ([ordered]@{ path = "@concat('$SourceFolder/', items('Por_cada_archivo')?['nombre'])" })
                                        Confirmar_carga = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/archivos/', items('Por_cada_archivo')?['id_archivo'], '/confirmar')" -Headers $controlHeaders -Body ([ordered]@{ etag_confirmado = "@outputs('Metadatos_finales')?['body/ETag']" }) -RunAfter ([ordered]@{ Metadatos_finales = @('Succeeded') }) -Secure
                                    }
                                    runtimeConfiguration = [ordered]@{ concurrency = [ordered]@{ repetitions = 1 } }
                                }
                                HTTP_Iniciar_Job = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/iniciar')" -Headers $controlHeaders -Body @{} -RunAfter ([ordered]@{ Por_cada_archivo = @('Succeeded') }) -Secure
                            }
                            else = [ordered]@{ actions = @{} }
                        }
                    }
                    runtimeConfiguration = [ordered]@{ concurrency = [ordered]@{ repetitions = 1 } }
                }
            }
            return [ordered]@{ connectionReferences = New-EmbeddedOneDriveReference; definition = New-BaseDefinition -Triggers (New-RecurrenceTrigger) -Actions $actions }
        }
        'auto-tasacion-entregar-lote' {
            $LegacyControlFolderId = Assert-OneDriveFolderId -FolderId $LegacyControlFolderId -LogicalPath $LegacyControlFolder -EnvironmentVariable 'AUTOTASACION_LEGACY_CONTROLS_FOLDER_ID'
            $actions = [ordered]@{
                Mostrar_controles_de_lote = New-OneDriveAction -OperationId 'ListFolderV2' -Parameters ([ordered]@{ id = $LegacyControlFolderId })
                Filtrar_controles_de_lote = [ordered]@{
                    runAfter = [ordered]@{ Mostrar_controles_de_lote = @('Succeeded') }
                    type = 'Query'
                    inputs = [ordered]@{
                        from = "@outputs('Mostrar_controles_de_lote')?['body/value']"
                        where = "@and(startsWith(item()?['Name'], '_autotasacion_lote_'), endsWith(toLower(item()?['Name']), '.json'))"
                    }
                }
                Por_cada_control = [ordered]@{
                    runAfter = [ordered]@{ Filtrar_controles_de_lote = @('Succeeded') }
                    type = 'Foreach'
                    foreach = "@body('Filtrar_controles_de_lote')"
                    actions = [ordered]@{
                        Obtener_control_lote = New-OneDriveAction -OperationId 'GetFileContentByPath' -Parameters ([ordered]@{ path = "@items('Por_cada_control')?['Path']" })
                        Leer_control_lote = [ordered]@{
                            runAfter = [ordered]@{ Obtener_control_lote = @('Succeeded') }
                            type = 'ParseJson'
                            inputs = [ordered]@{
                                content = Get-ControlJsonContentExpression
                                schema = [ordered]@{ type = 'object'; properties = [ordered]@{ id_lote = [ordered]@{ type = 'string' } }; required = @('id_lote') }
                            }
                        }
                        HTTP_Consultar_Lote = New-HttpAction -Method 'GET' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'])" -Headers $controlHeaders -RunAfter ([ordered]@{ Leer_control_lote = @('Succeeded') }) -Secure
                        Lote_completado = [ordered]@{
                            runAfter = [ordered]@{ HTTP_Consultar_Lote = @('Succeeded') }
                            type = 'If'
                            expression = "@and(equals(body('HTTP_Consultar_Lote')?['estado'], 'COMPLETADO'), equals(body('HTTP_Consultar_Lote')?['resultado_disponible'], true))"
                            actions = [ordered]@{
                                Solicitar_ticket_resultado = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/resultado-ticket')" -Headers $controlHeaders -Body @{} -Secure
                                Descargar_resultado = New-HttpAction -Method 'GET' -Uri "@body('Solicitar_ticket_resultado')?['url_descarga']" -RunAfter ([ordered]@{ Solicitar_ticket_resultado = @('Succeeded') }) -Secure
                                Crear_excel_final = New-OneDriveAction -OperationId 'CreateFile' -RunAfter ([ordered]@{ Descargar_resultado = @('Succeeded') }) -Parameters ([ordered]@{
                                    folderPath = $ResultFolder
                                    name = "@concat('Resultado_Final_', body('Leer_control_lote')?['id_lote'], '.xlsx')"
                                    body = "@body('Descargar_resultado')"
                                })
                                Confirmar_entrega = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/entrega')" -Headers $controlHeaders -Body @{} -RunAfter ([ordered]@{ Crear_excel_final = @('Succeeded') }) -Secure
                                Eliminar_control_lote = New-OneDriveAction -OperationId 'DeleteFile' -RunAfter ([ordered]@{ Confirmar_entrega = @('Succeeded') }) -Parameters ([ordered]@{ id = "@items('Por_cada_control')?['Id']" })
                            }
                            else = [ordered]@{ actions = @{} }
                        }
                    }
                    runtimeConfiguration = [ordered]@{ concurrency = [ordered]@{ repetitions = 1 } }
                }
            }
            return [ordered]@{ connectionReferences = New-EmbeddedOneDriveReference; definition = New-BaseDefinition -Triggers (New-RecurrenceTrigger) -Actions $actions }
        }
        default { throw "Flujo no reconocido: $Name" }
    }
}

function Get-WorkflowByName {
    param([Parameter(Mandatory)] [string] $Name)
    $safeName = $Name.Replace("'", "''")
    $response = Invoke-DataverseRequest -Method 'GET' -Path "workflows?`$select=workflowid,name,statecode,statuscode,clientdata&`$filter=name eq '$safeName' and category eq 5"
    $items = if ($response.Body) { ($response.Body | ConvertFrom-Json).value } else { @() }
    return @($items | Select-Object -First 1)
}

function Add-SolutionComponent {
    param(
        [Parameter(Mandatory)] [string] $ComponentId,
        [Parameter(Mandatory)] [int] $ComponentType
    )
    Invoke-DataverseRequest -Method 'POST' -Path 'AddSolutionComponent' -Body ([ordered]@{
        ComponentId = $ComponentId
        ComponentType = $ComponentType
        SolutionUniqueName = $SolutionUniqueName
        AddRequiredComponents = $false
        DoNotIncludeSubcomponents = $false
    }) | Out-Null
}

function Publish-WorkflowDraft {
    param([Parameter(Mandatory)] [string] $WorkflowId)

    # A solution-aware cloud flow can retain an ActiveUnpublished draft even
    # though statecode reports Activated. Publish only this workflow before the
    # update so Dataverse accepts the controlled Draft -> update -> Activated
    # lifecycle below; never publish unrelated environment customizations.
    $parameterXml = "<importexportxml><workflows><workflow>$WorkflowId</workflow></workflows></importexportxml>"
    Invoke-DataverseRequest -Method 'POST' -Path 'PublishXml' -Body ([ordered]@{
        ParameterXml = $parameterXml
    }) | Out-Null
}

function Create-DisabledFlow {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [string] $Description
    )

    $flowDefinition = New-FlowDefinition -Name $Name
    $clientdata = [ordered]@{
        properties = [ordered]@{
            connectionReferences = $flowDefinition.connectionReferences
            definition = $flowDefinition.definition
        }
        schemaVersion = '1.0.0.0'
    } | ConvertTo-Json -Depth 100 -Compress

    $existing = Get-WorkflowByName -Name $Name
    if ($existing) {
        # An active cloud flow can retain an unpublished active draft. Dataverse
        # rejects a direct published update in that state (0x80040203). Move it
        # to Draft first, replace the definition, then let -Activate publish it
        # again below. This keeps deployments repeatable for edited flows.
        if ([int] $existing.statecode -eq 1) {
            # Publish only an ActiveUnpublished predecessor. Publishing a flow
            # already in state/status Published before the PATCH is redundant
            # and can fail after Dataverse has accepted the request, preventing
            # the actual definition update from running.
            if ([int] $existing.statuscode -ne 2) {
                Publish-WorkflowDraft -WorkflowId ([string] $existing.workflowid)
            }
            Invoke-DataverseRequest -Method 'PATCH' -Path "workflows($($existing.workflowid))" -Body ([ordered]@{
                statecode = 0
                statuscode = 1
            }) | Out-Null
            $existing = Get-WorkflowByName -Name $Name
            Write-Verbose "Desactivado para actualizar: $Name ($($existing.workflowid))"
        }
        Invoke-DataverseRequest -Method 'PATCH' -Path "workflows($($existing.workflowid))" -Body ([ordered]@{
            clientdata = $clientdata
        }) | Out-Null
        Write-Verbose "Actualizado: $Name ($($existing.workflowid))"
        return [string] $existing.workflowid
    }

    $response = Invoke-DataverseRequest -Method 'POST' -Path 'workflows' -Body ([ordered]@{
        category = 5
        name = $Name
        type = 1
        primaryentity = 'none'
        description = $Description
        clientdata = $clientdata
    })
    if ($response.EntityId -notmatch '\(([0-9a-fA-F-]{36})\)') {
        throw "Dataverse no devolvió el identificador de $Name."
    }
    $workflowId = $Matches[1]
    Write-Verbose "Creado: $Name ($workflowId)"
    return $workflowId
}

$flows = [ordered]@{
    'auto-tasacion-iniciar-lote' = 'Registra un lote de PDFs seleccionado desde Power Apps y crea su control operativo.'
    'auto-tasacion-consultar-lote' = 'Consulta el estado y progreso de un lote de tasaciones en Cloud Run.'
    'auto-tasacion-orquestar-lote' = 'Orquesta un único lote al crearse su control de OneDrive, con claim persistido e idempotencia.'
    'auto-tasacion-cargar-lotes' = 'Carga PDFs individuales pendientes desde OneDrive hacia GCS y arranca el Job.'
    'auto-tasacion-entregar-lote' = 'Entrega el XLSX final en OneDrive cuando Cloud Run completa el lote.'
}

if ($FlowName) {
    # A partial deployment is useful to recover a single flow without
    # touching the others. Validate names explicitly so an unknown name is
    # never silently ignored.
    $unknownFlowNames = @($FlowName | Where-Object { -not $flows.Contains($_) })
    if ($unknownFlowNames.Count -gt 0) {
        throw "Flujo no reconocido: $($unknownFlowNames -join ', ')"
    }
    $selectedFlows = [ordered]@{}
    foreach ($name in $FlowName) {
        $selectedFlows[$name] = $flows[$name]
    }
    $flows = $selectedFlows
}

# The event-driven orchestrator needs the opaque OneDrive identifier stored in
# its trigger. Validate it before building any local plan so a missing shell
# environment variable produces an actionable message instead of a PowerShell
# parameter-binding error inside the definition builder.
if ($flows.Contains('auto-tasacion-orquestar-lote')) {
    $ControlFolderId = Assert-OneDriveFolderId -FolderId $ControlFolderId -LogicalPath $ControlFolder -EnvironmentVariable 'AUTOTASACION_CONTROLS_FOLDER_ID'
}

if ($EmitDefinitionJson) {
    if ($flows.Count -ne 1) {
        throw '-EmitDefinitionJson requiere exactamente un -FlowName.'
    }
    $flow = $flows.GetEnumerator() | Select-Object -First 1
    $flowDefinition = New-FlowDefinition -Name $flow.Key
    [ordered]@{
        name = $flow.Key
        connectionReferences = $flowDefinition.connectionReferences
        definition = $flowDefinition.definition
    } | ConvertTo-Json -Depth 100
    return
}

if ($script:IsLocalPlan) {
    # Never authenticate, read Secret Manager, call Dataverse, create a flow, or
    # alter state in a local plan. -DryRun makes this safety intent explicit;
    # omitting -Activate has the same no-remote-effect behavior.
    $plan = foreach ($flow in $flows.GetEnumerator()) {
        $flowDefinition = New-FlowDefinition -Name $flow.Key
        [pscustomobject]@{
            Name = $flow.Key
            Mode = if ($DryRun) { 'DryRun' } else { 'Plan' }
            WillModifyRemote = $false
            TriggerNames = (@($flowDefinition.definition.triggers.Keys) -join ',')
            ActionCount = @($flowDefinition.definition.actions.Keys).Count
        }
    }
    $plan | Format-Table -AutoSize
    Write-Warning 'No se autentico ni se modifico Power Platform, Secret Manager o Cloud Run. Use -Activate unicamente durante un despliegue autorizado.'
    return
}

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Import-Module MSAL.PS -Force

Write-Output "Usando referencia de conexion: $OneDriveConnectionReferenceId"
Add-SolutionComponent -ComponentId ([string] $OneDriveConnectionReferenceId) -ComponentType 10423
if ($null -ne $script:TeamsNotifications) {
    Write-Output "Usando referencia de conexion de Teams: $($script:TeamsNotifications.ReferenceLogicalName)"
}

foreach ($flow in $flows.GetEnumerator()) {
    $id = Create-DisabledFlow -Name $flow.Key -Description $flow.Value
    Add-SolutionComponent -ComponentId $id -ComponentType 29
    if ($Activate) {
        # The Power Automate service validates the full definition when a draft
        # cloud flow turns on, so preserve its current clientdata in the update.
        $currentFlow = Get-WorkflowByName -Name $flow.Key
        if ([int] $currentFlow.statecode -ne 1) {
            Invoke-DataverseRequest -Method 'PATCH' -Path "workflows($id)" -Body ([ordered]@{
                statecode = 1
                statuscode = 2
                clientdata = [string] $currentFlow.clientdata
            }) | Out-Null
        }

        # Publish after PATCH and activation. Without this final publication,
        # the service can retain the preceding runtime definition even though
        # workflow.clientdata contains a newer draft.
        Publish-WorkflowDraft -WorkflowId $id
        $publishedFlow = Get-WorkflowByName -Name $flow.Key
        if ([int] $publishedFlow.statecode -ne 1 -or [int] $publishedFlow.statuscode -ne 2) {
            throw "El flujo no quedo publicado: $($flow.Key) ($id)."
        }
        Write-Output "Publicado: $($flow.Key)"
    }
}

Write-Output 'Flujos masivos creados y publicados correctamente.'
