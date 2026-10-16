# Alertas de Microsoft Teams para Auto Tasaciones

## Destino aprobado

Las alertas operativas se publican mediante **Flow bot** en el chat grupal de
Teams **[BBVA] AUTOMATIZACION TASACIONES**. El nombre facilita seleccionar el
chat en el diseñador; la definición técnica usa el identificador opaco del
chat, que se guarda solamente en la configuración local del entorno.

No se envían préstamos, expedientes, PDFs, tasaciones ni contenido de los
archivos. Los mensajes contienen solamente `ID_LOTE`, estado, conteos y el
nombre del Excel de salida.

## Eventos cubiertos por la definición versionada

| Momento | Flujo | Mensaje |
| --- | --- | --- |
| Lote registrado desde Canvas | `auto-tasacion-iniciar-lote` | ID del lote, PDFs seleccionados y estado inicial. |
| Excel final entregado en OneDrive | `auto-tasacion-orquestar-lote` | ID del lote y nombre del Excel final. |
| Lote terminal sin resultado | `auto-tasacion-orquestar-lote` | ID del lote y estado que requiere atención. |
| Espera Cloud agotada | `auto-tasacion-orquestar-lote` | ID del lote y estado observado al agotarse las dos horas. |

La acción de Teams no bloquea la respuesta a Power Apps ni la eliminación del
control una vez que la entrega se confirmó. Las acciones posteriores se
configuran para continuar tanto si el envío a Teams termina correctamente como
si falla.

Los mensajes del tramo **PAD / 3270** se agregan manualmente al Cloud Flow que
invoca el Desktop Flow, porque ese flujo no lo genera
`deploy-mass-flows.ps1`. El procedimiento está al final de este documento.

## Configuración local por entorno

La definición sólo incorpora Teams cuando se le entrega un JSON local. El
archivo real está excluido de Git:

```text
config/teams-notifications.local.json
```

1. En **Soluciones → autoTasacion → Referencias de conexión**, cree o reutilice
   una referencia de **Microsoft Teams** conectada con la cuenta corporativa
   autorizada.
2. En un borrador de flujo, agregue **Publicar un mensaje en un chat o canal**:
   - **Publicar como**: `Flow bot`;
   - **Publicar en**: `Group chat`;
   - **Group chat**: `[BBVA] AUTOMATIZACION TASACIONES`.
3. Guarde el borrador con esa única acción temporal de Teams y ejecute desde la
   raíz del repositorio:

   ```powershell
   .\power-platform\scripts\Export-TeamsNotificationConfig.ps1
   ```

   El script abre la autenticación corporativa, lee sólo la definición guardada
   y genera `config/teams-notifications.local.json`. No imprime ni versiona el
   identificador del chat. La acción temporal quedará reemplazada por las
   acciones versionadas al publicar el siguiente paso.

El archivo generado tiene esta forma, sin comillas adicionales dentro de los
valores:

```json
{
  "schema_version": 1,
  "automation": "auto-tasacion",
  "enabled": true,
  "connection": {
    "reference_logical_name": "<valor_de_connectionReferenceLogicalName>"
  },
  "destination": {
    "kind": "group_chat",
    "group_chat_id": "19:<valor_de_body_recipient>@thread.v2",
    "display_name": "[BBVA] AUTOMATIZACION TASACIONES"
  }
}
```

La referencia de conexión debe existir dentro de la solución antes del
despliegue. Por ello el generador no crea conexiones ni solicita credenciales.

## Revisar y publicar la definición Cloud

Primero genere las dos definiciones localmente, sin autenticarse ni cambiar
Power Platform:

```powershell
$controlFolderId = .\power-platform\scripts\Get-OneDriveControlFolderId.ps1
.\power-platform\scripts\deploy-mass-flows.ps1 `
  -DryRun `
  -TeamsNotificationsConfigPath .\config\teams-notifications.local.json `
  -ControlFolderId $controlFolderId `
  -FlowName auto-tasacion-iniciar-lote,auto-tasacion-orquestar-lote
```

La definición resultante incluirá la referencia `shared_teams` y la operación
`PostMessageToConversation`. Revise que el chat tenga el destino esperado.

En una ventana operativa sin controles JSON pendientes, publique sólo esos dos
flujos:

```powershell
$controlFolderId = .\power-platform\scripts\Get-OneDriveControlFolderId.ps1
.\power-platform\scripts\deploy-mass-flows.ps1 `
  -Activate `
  -TeamsNotificationsConfigPath .\config\teams-notifications.local.json `
  -ControlFolderId $controlFolderId `
  -FlowName auto-tasacion-iniciar-lote,auto-tasacion-orquestar-lote
```

El despliegue se ejecuta manualmente. No publique cambios desde el diseñador
después de este paso sin reflejarlos en el generador, porque la próxima
publicación sustituye la definición completa del flujo.

## Avisos de PAD y 3270

El actualizador `Update-PadTeamsNotifications.ps1` conserva la definicion ya
publicada de `auto-tasacion-activar-pad`, incluida la conexion al Desktop Flow.
Por defecto mantiene tres mensajes Cloud:

| Ubicacion | Ejecucion posterior | Mensaje |
| --- | --- | --- |
| Antes del Desktop Flow | Dependencias originales del Desktop Flow | Inicio de PAD/3270 para el lote. |
| Despues del Desktop Flow | `Succeeded` | Cierre generico Cloud basado en las salidas del Desktop Flow. |
| Despues del Desktop Flow | `Failed`, `TimedOut` o `Skipped` | Aviso de atencion sin detalles tecnicos. |

El cierre generico es temporal mientras PAD no publique su resumen detallado.
Cuando `ValidarExcel` ya lea el JSON durable y publique el HTML mediante
`Format-Macro3270TeamsSummary.ps1`, use `-SuccessNotificationSource Desktop`.
Ese modo conserva los avisos Cloud de inicio y error, y retira solo
`Notificar_PAD_3270_fin` para que no haya dos cierres.

La configuracion paso a paso y el formato del mensaje estan en
[`resumen-teams-resultado-3270.md`](resumen-teams-resultado-3270.md). Primero
revise el plan; esta lectura no escribe definiciones ni muestra el ID del chat:

```powershell
.\power-platform\scripts\Update-PadTeamsNotifications.ps1 -DryRun
```

Despues de validar visualmente el resumen de un lote nuevo, aplique el modo PAD:

```powershell
.\power-platform\scripts\Update-PadTeamsNotifications.ps1 `
  -Activate `
  -SuccessNotificationSource Desktop
```

No modifique manualmente los avisos Cloud que administra este script, porque el
siguiente despliegue dirigido volveria a aplicar la definicion versionada.
el siguiente despliegue dirigido volvería a aplicar la definición versionada.

## Validación operativa

1. Ejecute un lote de prueba con un PDF o con los diez casos autorizados.
2. Confirme en el chat la alerta de registro y, cuando termine Cloud Run, la
   alerta de Excel final.
3. Confirme que el flujo Cloud activa PAD y que llegan el aviso de inicio y el
   terminal de PAD/3270.
4. Compare el `ID_LOTE` de las alertas con Power Apps, el historial de Cloud
   Flows y el JSON de estado local de PAD.

Microsoft documenta que la acción **Post a message in a chat or channel** se
configura con `Flow bot`, `Group chat` y el grupo existente elegido en el
desplegable. [Guía oficial de Microsoft](https://learn.microsoft.com/en-us/power-automate/teams/send-a-message-in-teams).
