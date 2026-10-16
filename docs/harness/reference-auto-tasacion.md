# Implementación de referencia: Auto Tasaciones

Esta referencia registra la ruta validada desde Power Apps hasta la consulta
segura de IBM 3270. Sirve para adaptar el harness: no se deben copiar a otro
proceso sus nombres, rutas, conexiones ni identificadores.

## Resultado alcanzado

```text
Power Apps -> registro de lote -> Cloud Run -> Resultado_Final.xlsx
-> flujo de activación -> PAD -> Excel MASIVO -> PCOMM/3270 en consulta
-> Teams
```

La prueba 3270 usa `browse-lot`: consulta pantallas por préstamo sin grabar
campos de negocio. Las alertas de Cloud informan lote registrado y Excel
entregado; PAD informa inicio y final. El aviso final de PAD aún requiere
validar que sus campos de salida no lleguen vacíos.

## Preparación manual y automatizada

| Área | Estado actual | Patrón reutilizable |
| --- | --- | --- |
| Cloud Run | El secreto de control se monta desde Secret Manager y el flujo usa la misma versión que la revisión activa. | Mantener cliente y servicio sobre la misma versión de secreto. |
| Power Platform | Referencias de OneDrive, Teams y Desktop Flow se crean por entorno. | Los identificadores opacos se obtienen en el entorno y permanecen fuera de Git. |
| Teams | Un flujo temporal permitió seleccionar el chat corporativo y exportar su configuración local. | Dejar que el diseñador resuelva el chat; no copiar su identificador. |
| OneDrive | Se preparan carpetas separadas para PDFs, controles y resultados. | Evitar que dos desencadenadores consuman el mismo artefacto. |
| BPO/PAD | Se instaló `pywin32`, se preparó Excel y se configuró PCOMM/HLLAPI. | Cada dependencia de escritorio se valida en la cuenta que ejecuta PAD. |
| PCOMM | PAD abre, autentica y prepara la sesión `A` antes de `browse-lot`. | Separar apertura/autenticación de la operación de negocio. |
| Credenciales 3270 | Un Excel compartido provee temporalmente usuario y contraseña al subflujo PAD. | Tratarlo como deuda técnica y migrar a un almacén seguro. |

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

El archivo `teams-notifications.local.json` contiene configuración local de
Teams y queda fuera de Git. `Get-OneDriveControlFolderId` obtiene la carpeta de
control desde la definición del flujo, evitando copiarla del diseñador.

## Preparación automática de 3270 validada en PBO

La arquitectura definitiva del Desktop Flow es:

```text
Main
├── InicializarLote
└── ValidarExcel
    ├── AsegurarSesion3270
    └── macro_3270_runner.py ... browse-lot
```

`AsegurarSesion3270` no se llama desde `Main`: hacerlo provocaría una doble
apertura y login. El subflujo abre PCOMM, espera, se adjunta por HLLAPI `A`,
selecciona la aplicación, inicia sesión y prepara el centro. Después libera
HLLAPI y conserva PCOMM abierto para que VBA se adjunte a `A`.

La secuencia real de host es:

```text
LIMPIAR_VENTANA -> qgtr -> Transmitir -> BXA0147 -> Clear -> 0727
-> Transmitir -> espera -> LIMPIAR_VENTANA -> cerrar TerminalSession
```

No se debe asumir que `qgtr` abre de forma directa la pantalla de centro, ni
forzar las coordenadas de cursor tras `Clear`. La pantalla intermedia `BXA0147`
y el cursor que deja el host fueron comprobados en PBO.

Las acciones Teams de inicio de login y usuario bloqueado están configuradas en
el Robin, pero deshabilitadas. No se consideran alertas operativas hasta
habilitarlas y validarlas. La rama de usuario bloqueado hoy finaliza con código
0; debe producir un estado técnico de error antes de su cierre operativo.

## Mejoras y diagnósticos incorporados

| Síntoma | Causa encontrada | Patrón que se debe reutilizar |
| --- | --- | --- |
| `InvalidTemplate` con `StartArray` en el header | PowerShell serializó dos líneas del secreto como array. | Convertir el secreto a una sola cadena no vacía antes de crear la definición HTTP. |
| `NO_AUTORIZADO` aunque el header era válido | El flujo usó una versión distinta de la montada por Cloud Run. | Obtener la versión de la revisión activa y recuperarla para el flujo. |
| `ActiveUnpublished` al actualizar un flujo | Existía un borrador activo sin publicar. | Publicar el flujo objetivo antes de aplicar el PATCH. |
| Tiempo de espera al publicar | `PublishXml` excedió el timeout por defecto. | Aumentar el timeout de forma acotada y publicar solo los flujos afectados. |
| PAD no encontró `python.exe` | La ruta contenía espacios. | Ejecutar mediante `cmd.exe /d /c` y esperar a que termine. |
| Excel COM falló al abrir plantilla | El archivo no estaba disponible localmente. | Confirmar sincronización y validar libro, hoja y tabla antes de PAD. |
| Centro rechazado por 3270 | Se movió el cursor a una zona protegida. | Confirmar `BXA0147` y escribir el centro en el cursor actual. |
| VBA no pudo tomar la sesión | PAD retuvo HLLAPI. | Cerrar `TerminalSession` sin cerrar PCOMM antes de llamar la macro. |
| Alerta final de PAD con campos vacíos | Debe confirmarse el contrato de salida del Desktop Flow. | La aceptación exige estado y mensaje no vacíos. |

## Evidencia mínima de aceptación

1. El lote obtiene una llave de correlación y Cloud entrega el Excel final.
2. PAD recibe esa misma llave, abre PCOMM desde cerrado y prepara la sesión A
   sin intervención manual.
3. PAD libera HLLAPI, mientras PCOMM permanece abierto.
4. `browse-lot` vuelve a adjuntarse, realiza `PAUSA -> I003 -> 01 -> préstamo
   -> ENTER` y registra `CONSULTA_3270_OK` por cada caso elegible.
5. El estado durable, el libro publicado y las capturas de consulta no muestran
   error técnico.
6. Teams muestra los hitos con identificador, estado y mensaje no vacíos.

## Límite actual

La escritura en IBM 3270 sigue fuera del alcance. Cualquier proceso que vaya a
modificar el sistema de destino debe cerrar primero el modo seguro, validar los
datos de negocio con su responsable y recibir autorización explícita para
habilitar el modo transaccional.
