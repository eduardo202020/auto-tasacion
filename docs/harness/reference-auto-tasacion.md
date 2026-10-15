# Implementación de referencia: Auto Tasaciones

Esta referencia explica los pasos que convirtieron Auto Tasaciones en una ruta operativa desde Power Apps hasta la consulta segura de IBM 3270. Sirve para adaptar el harness; sus nombres, rutas, conexiones e identificadores no deben copiarse a otro proceso.

## Resultado alcanzado

La ejecución E2E confirma esta cadena:

```text
Power Apps -> registro de lote -> Cloud Run -> Resultado_Final.xlsx
-> flujo de activación -> PAD -> Excel MASIVO -> PCOMM/3270 en modo consulta
-> Teams
```

El flujo entrega cuatro avisos de Teams: lote registrado, Excel disponible, inicio de PAD/3270 y final de PAD/3270. La prueba de 3270 usa `browse-lot`: consulta pantallas por préstamo y no realiza grabaciones.

## Pasos manuales que fueron necesarios

| Área | Paso manual | Motivo reutilizable |
| --- | --- | --- |
| Cloud Run | Montar `BATCH_CONTROL_API_TOKEN` desde Secret Manager y conservar la versión usada por la revisión activa. | El cliente HTTP debe usar el mismo secreto que valida el servicio. |
| Power Platform | Crear o reutilizar referencias de conexión de OneDrive, Teams y Desktop Flow dentro de la solución. | Las referencias son propias de cada entorno. |
| Teams | Crear una acción temporal `Flow bot` -> `Group chat`, seleccionar el chat corporativo y guardar el flujo. | El diseñador obtiene el identificador opaco del chat sin exponerlo. |
| OneDrive | Crear y validar carpetas separadas para PDFs, controles y resultados. | Evita que dos desencadenadores procesen el mismo archivo. |
| BPO / PAD | Instalar `pywin32` en el Python que ejecuta PAD y crear la carpeta local de trabajo. | Excel COM debe ejecutarse en el mismo perfil operativo que PAD. |
| Excel | Copiar la plantilla `.xlsm`, importar `AutoTasacion3270.bas` y agregar la carpeta de trabajo a Ubicaciones de confianza. | El libro requiere macro y acceso COM sin diálogos. |
| PAD | Ejecutar Python por `C:\Windows\System32\cmd.exe` con `/d /c` cuando la ruta contiene espacios. | PAD no resolvió directamente el ejecutable Python en esa ruta. |
| PCOMM | Dejar la sesión A autenticada antes de una prueba `read-lot`, `navigate-lot` o `browse-lot`. | La automatización se adjunta a una sesión existente. |

## Comandos automatizados aplicados

Ejecutados desde la raíz del repositorio en una consola autorizada:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

.\power-platform\scripts\Export-TeamsNotificationConfig.ps1 `
  -FlowName auto-tasacion-configurar-teams

$controlFolderId = .\power-platform\scripts\Get-OneDriveControlFolderId.ps1

.\power-platform\scripts\deploy-mass-flows.ps1 `
  -DryRun `
  -TeamsNotificationsConfigPath .\config\teams-notifications.local.json `
  -ControlFolderId $controlFolderId `
  -FlowName auto-tasacion-iniciar-lote,auto-tasacion-orquestar-lote

.\power-platform\scripts\deploy-mass-flows.ps1 `
  -Activate `
  -TeamsNotificationsConfigPath .\config\teams-notifications.local.json `
  -ControlFolderId $controlFolderId `
  -FlowName auto-tasacion-iniciar-lote,auto-tasacion-orquestar-lote

.\power-platform\scripts\Update-PadTeamsNotifications.ps1 -DryRun
.\power-platform\scripts\Update-PadTeamsNotifications.ps1 -Activate
```

`teams-notifications.local.json` contiene el identificador del chat y la referencia de conexión; se mantiene fuera de Git. `Get-OneDriveControlFolderId` devuelve el identificador actual desde la definición almacenada del flujo, de modo que no se copia desde el diseñador.

## Mejoras y diagnósticos incorporados

| Síntoma | Causa encontrada | Patrón que se debe reutilizar |
| --- | --- | --- |
| `InvalidTemplate` con `StartArray` en el header | PowerShell serializó dos líneas del secreto como array. | Convertir el secreto a una sola cadena no vacía antes de crear la definición HTTP. |
| `NO_AUTORIZADO` aunque el header era válido | El flujo usó `latest`, pero Cloud Run tenía una versión de secreto fijada. | Obtener la versión montada por la revisión activa y recuperar esa misma versión para el flujo. |
| `ActiveUnpublished` al actualizar un flujo | Existía un borrador activo sin publicar. | Publicar el flujo objetivo antes de desactivarlo y aplicar el PATCH. |
| Tiempo de espera al publicar | `PublishXml` excedió el timeout por defecto. | Usar timeout acotado mayor y publicar solo los flujos afectados. |
| PAD no encontró `python.exe` | La ruta contenía espacios y PAD no la inició directamente. | Ejecutar mediante `cmd.exe /d /c` y esperar a que termine. |
| Excel COM falló al abrir plantilla | Archivo aún no sincronizado o ruta no disponible. | Confirmar sincronización y validar libro, hoja y tabla con una apertura COM antes de PAD. |
| Alerta final de PAD con campos vacíos | La acción de Teams se ejecutó, pero se debe confirmar el mapeo de salidas de Desktop Flow. | La aceptación exige valores no vacíos para estado y mensaje; revisar el contrato de salidas antes del cierre. |

## Evidencia que debe conservarse

1. Historial del flujo de inicio: HTTP correcto, ID nuevo y control creado.
2. Historial del orquestador: salida final creada y entrega confirmada.
3. Estado durable local de PAD, incluyendo modo, filas, resultado y error técnico vacío.
4. Libro publicado en la carpeta de salida y traza por caso.
5. Los cuatro avisos de Teams asociados al mismo ID de lote, con estado y mensaje no vacíos en el evento final de PAD.

## Límite actual

La escritura en IBM 3270 sigue fuera del alcance. Cualquier proceso que vaya a modificar el sistema de destino debe cerrar primero el modo seguro, validar datos de negocio con su responsable y recibir autorización explícita para habilitar su modo transaccional.
