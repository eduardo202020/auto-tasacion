[CmdletBinding()]
param(
    [switch] $Activate
)

$ErrorActionPreference = 'Stop'

# This script creates or updates mass-processing flows as solution-aware
# components. No document content or control token is written to this repository.
$DataverseUrl = 'https://org9a4ef0e0.crm4.dynamics.com'
$SolutionUniqueName = 'autoTasacion'
$EnvironmentId = 'Default-3048dc87-43f0-4100-9acb-ae1971c79395'
$ServiceUrl = 'https://demo-tasaciones-ia-h75cd5qm2q-nn.a.run.app'
$SourceFolder = '/auto-tasaciones/PDFs'
$PdfFolderId = 'b!ana6TpGRu0a2hKHjlUBacJlpM_jFZw1Ag7HCRmtA2cvfU_73uexKT44DJr0wIKqF.01NAERNYGYDB4D2NACL5FYP7EE2UHEZXFR'
$OneDriveConnectionId = 'shared-onedriveforbu-192895c8-7959-4901-bdd9-0dd1cc6a1c6f'
$OneDriveConnectionReference = 'tasatest_sharedonedriveforbusiness_132da'
$OneDriveConnectionReferenceId = '2f2b17a0-68c2-f111-aaaf-7ced8d92a1ed'
$Gcloud = 'C:\Users\jhglazar\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Import-Module MSAL.PS -Force

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
    $value = (& $Gcloud secrets versions access 2 --secret 'batch-control-api-token' --project 'project-fe2e4c6a-b528-4bcf-aa1').Trim()
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
                    folderPath = $SourceFolder
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
                        }
                        schema = [ordered]@{
                            type = 'object'
                            properties = [ordered]@{
                                id_lote = [ordered]@{ title = 'IdLote'; 'x-ms-dynamically-added' = $true; type = 'string' }
                                estado = [ordered]@{ title = 'Estado'; 'x-ms-dynamically-added' = $true; type = 'string' }
                            }
                        }
                    }
                }
            }
            return [ordered]@{ connectionReferences = New-InvokerOneDriveReference; definition = New-BaseDefinition -Triggers (New-PowerAppsTrigger -Title 'SeleccionJson') -Actions $actions }
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
                            }
                            required = @('id_lote', 'estado', 'total_pdfs', 'pdfs_cargados', 'pdfs_procesados', 'pdfs_fallidos', 'resultado_disponible')
                        }
                    }
                }
            }
            return [ordered]@{ connectionReferences = @{}; definition = New-BaseDefinition -Triggers (New-PowerAppsTrigger -Title 'IdLote') -Actions $actions }
        }
        'auto-tasacion-cargar-lotes' {
            $actions = [ordered]@{
                Mostrar_controles_de_lote = New-OneDriveAction -OperationId 'ListFolderV2' -Parameters ([ordered]@{ id = $PdfFolderId })
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
            $actions = [ordered]@{
                Mostrar_controles_de_lote = New-OneDriveAction -OperationId 'ListFolderV2' -Parameters ([ordered]@{ id = $PdfFolderId })
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
                            expression = "@equals(body('HTTP_Consultar_Lote')?['estado'], 'COMPLETADO')"
                            actions = [ordered]@{
                                Solicitar_ticket_resultado = New-HttpAction -Method 'POST' -Uri "@concat('$ServiceUrl/v1/lotes/', body('Leer_control_lote')?['id_lote'], '/resultado-ticket')" -Headers $controlHeaders -Body @{} -Secure
                                Descargar_resultado = New-HttpAction -Method 'GET' -Uri "@body('Solicitar_ticket_resultado')?['url_descarga']" -RunAfter ([ordered]@{ Solicitar_ticket_resultado = @('Succeeded') }) -Secure
                                Crear_excel_final = New-OneDriveAction -OperationId 'CreateFile' -RunAfter ([ordered]@{ Descargar_resultado = @('Succeeded') }) -Parameters ([ordered]@{
                                    folderPath = '/auto-tasaciones'
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
    $response = Invoke-DataverseRequest -Method 'GET' -Path "workflows?`$select=workflowid,name,statecode,clientdata&`$filter=name eq '$safeName' and category eq 5"
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

Write-Output "Usando referencia de conexión: $OneDriveConnectionReferenceId"
Add-SolutionComponent -ComponentId ([string] $OneDriveConnectionReferenceId) -ComponentType 10423

$flows = [ordered]@{
    'auto-tasacion-iniciar-lote' = 'Registra un lote de PDFs seleccionado desde Power Apps y crea su control operativo.'
    'auto-tasacion-consultar-lote' = 'Consulta el estado y progreso de un lote de tasaciones en Cloud Run.'
    'auto-tasacion-cargar-lotes' = 'Carga PDFs individuales pendientes desde OneDrive hacia GCS y arranca el Job.'
    'auto-tasacion-entregar-lote' = 'Entrega el XLSX final en OneDrive cuando Cloud Run completa el lote.'
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
                clientdata = [string] $currentFlow.clientdata
            }) | Out-Null
            Write-Output "Activado: $($flow.Key)"
        }
        else {
            Write-Output "Ya publicado: $($flow.Key)"
        }
    }
}

Write-Output 'Flujos masivos creados correctamente.'
