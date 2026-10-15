[CmdletBinding()]
param(
    [string] $FlowName = 'auto-tasacion-orquestar-lote'
)

$ErrorActionPreference = 'Stop'

# Reads the currently saved cloud-flow definition and returns only the folder
# identifier used by its OneDrive "when a file is created" trigger. This lets
# a deployment reuse the verified trigger target without printing clientdata
# or copying an opaque value from the Power Automate designer.
$DataverseUrl = 'https://org9a4ef0e0.crm4.dynamics.com'

function Get-OneDriveCreatedFileTriggers {
    param([Parameter(Mandatory)] [object] $Triggers)

    foreach ($property in $Triggers.PSObject.Properties) {
        $trigger = $property.Value
        $connectorHost = $trigger.inputs.host
        $parameters = $trigger.inputs.parameters
        if ($trigger.type -eq 'OpenApiConnection' -and
            $connectorHost.apiId -eq '/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness' -and
            $connectorHost.operationId -eq 'OnNewFilesV2' -and
            -not [string]::IsNullOrWhiteSpace([string] $parameters.folderId)) {
            [pscustomobject]@{
                Name = [string] $property.Name
                FolderId = [string] $parameters.folderId
            }
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
    throw "No se encontro el flujo '$FlowName'."
}

$definition = ([string] $flows[0].clientdata | ConvertFrom-Json).properties.definition
$matches = @(Get-OneDriveCreatedFileTriggers -Triggers $definition.triggers)
if ($matches.Count -ne 1) {
    $found = if ($matches.Count -eq 0) { 'ninguno' } else { "$($matches.Count) desencadenadores" }
    throw "Se encontraron $found de OneDrive OnNewFilesV2 en '$FlowName'."
}

if ($matches[0].FolderId.Length -lt 20 -or $matches[0].FolderId -match '[\\/\s]') {
    throw "El folderId configurado en '$FlowName' no parece valido."
}

# Deliberately emit just the opaque ID so callers can assign it directly to a
# local variable. Do not write flow definitions or change Power Platform.
Write-Output $matches[0].FolderId
