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
campos de negocio. Las alertas de Cloud informan lote registrado, Excel
entregado, inicio de PAD y error de PAD. En PAD, el cierre exitoso se obtiene
del JSON durable del mismo lote; no depende de salidas vacías del conector
Desktop Flow.

## Preparación manual y automatizada

| Área | Estado actual | Patrón reutilizable |
| --- | --- | --- |
| Cloud Run | El secreto de control se monta desde Secret Manager y el flujo usa la misma versión que la revisión activa. | Mantener cliente y servicio sobre la misma versión de secreto. |
| Power Platform | Referencias de OneDrive, Teams y Desktop Flow se crean por entorno. | Los identificadores opacos se obtienen en el entorno y permanecen fuera de Git. |
| Teams | Un flujo temporal permitió seleccionar el chat corporativo y exportar su configuración local. PAD tiene un resumen directo de 3270 configurado, pendiente de evidencia E2E. | Dejar que el diseñador resuelva el chat; no copiar su identificador. Construir el cierre desde el artefacto estructurado del mismo lote. |
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
    ├── macro_3270_runner.py ... browse-lot -> AppExitCode
    └── IF AppExitCode = 0
        ├── RESUMEN_RESULTADO_3270
        └── ELSE -> alerta técnica de Teams
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

## Cierre de PAD basado en código técnico y JSON

`ValidarExcel` espera el proceso `cmd.exe /d /c` que invoca el runner y guarda
su `AppExitCode`. La condición usa el número `0`, no el texto `"0"`:

```text
AppExitCode <> 0 -> alerta roja; no interpretar resultado funcional
AppExitCode = 0  -> RESUMEN_RESULTADO_3270 lee el JSON del mismo lote
```

El código `0` solo confirma que el runner terminó técnicamente. El subflujo
`RESUMEN_RESULTADO_3270` decide el estado operativo mediante
`<ID_LOTE>_<SHA>_macro_3270.json`: verde cuando el estado es
`CONSULTADO_SIN_CAMBIOS_3270` y todos los casos son `CONSULTA_3270_OK`, ámbar
para `CONSULTADO_SIN_CAMBIOS_3270_CON_INCIDENCIAS` y rojo si el JSON declara
`ERROR_MACRO_3270`.

El mensaje de Teams contiene lote, estado, modo, conteos, categorías de
resultado, duración y nombre del Excel publicado. No incluye préstamos, casos,
rutas ni errores técnicos. Los detalles se conservan en el JSON y `TRAZA_PAD`.

Al terminar, Excel, Python y `cmd.exe` cierran; PCOMM queda abierto de forma
intencional. PAD libera `TerminalSession` de HLLAPI, pero no mata PCOMM porque
VBA se adjunta después a la sesión `A`.

La estructura PAD está configurada. Falta una ejecución E2E nueva que pruebe
el mensaje directo de Teams antes de retirar el cierre genérico Cloud.

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
| Alerta final de PAD con campos vacíos | El Cloud Flow dependía de salidas no definidas del Desktop Flow. | Construir el resumen en PAD desde el JSON durable del mismo lote y enviar solo conteos seguros. |
| El runner terminó sin error pero hubo casos no correctos | Se confundió el código técnico con el resultado funcional. | Capturar el código de salida primero e interpretar el JSON solo cuando el código sea cero. |

## Evidencia mínima de aceptación

1. El lote obtiene una llave de correlación y Cloud entrega el Excel final.
2. PAD recibe esa misma llave, abre PCOMM desde cerrado y prepara la sesión A
   sin intervención manual.
3. PAD libera HLLAPI, mientras PCOMM permanece abierto.
4. `browse-lot` vuelve a adjuntarse, realiza `PAUSA -> I003 -> 01 -> préstamo
   -> ENTER` y registra `CONSULTA_3270_OK` por cada caso elegible.
5. PAD conserva `AppExitCode = 0`, el estado durable y el libro publicado del
   mismo lote. Las capturas de consulta no muestran error técnico.
6. Teams muestra los hitos con identificador y valores no vacíos. El cierre
   directo de PAD coincide con los conteos del JSON del mismo lote, sin exponer
   datos por caso, rutas locales ni detalles técnicos.

## Límite actual

La escritura en IBM 3270 sigue fuera del alcance. Cualquier proceso que vaya a
modificar el sistema de destino debe cerrar primero el modo seguro, validar los
datos de negocio con su responsable y recibir autorización explícita para
habilitar el modo transaccional.
