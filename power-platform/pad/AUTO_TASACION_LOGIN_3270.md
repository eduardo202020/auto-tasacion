# Inicio automático de IBM 3270 para Auto Tasaciones

## Estado operativo validado en PBO

`AsegurarSesion3270` prepara IBM Personal Communications (PCOMM) para una
consulta segura. Abre el perfil, autentica la sesión `A`, selecciona el centro
`0727`, libera HLLAPI y deja PCOMM abierto para que Excel/VBA se vuelva a
adjuntar.

No procesa préstamos ni escribe campos de tasación. La operación posterior se
mantiene en `browse-lot`; `run-lot` continúa fuera del alcance de esta etapa.

```text
Main
├── InicializarLote
└── ValidarExcel
    ├── AsegurarSesion3270
    └── macro_3270_runner.py ... browse-lot
```

`AsegurarSesion3270` se invoca únicamente dentro de `ValidarExcel`,
inmediatamente antes de `browse-lot`. No debe añadirse a `Main`: duplicaría la
apertura y el inicio de sesión.

## Configuración y dependencias de PBO

| Elemento | Valor validado | Uso |
| --- | --- | --- |
| Perfil PCOMM | `C:\Data\3270.WS` | Se abre maximizado mediante PAD. |
| Biblioteca HLLAPI | `C:\Program Files (x86)\IBM\Personal Communications\EHLAPI32.dll` | PAD se adjunta después de abrir PCOMM. |
| Sesión | `A` | PAD y VBA usan la misma sesión, en momentos distintos. |
| Centro de Auto Tasaciones | `0727` | Se selecciona durante la preparación. |

El orden es obligatorio: abrir `.WS`, esperar su disponibilidad y luego abrir
la sesión HLLAPI. PAD no debe intentar adjuntarse antes de que PCOMM esté
abierto.

## Credenciales: estado actual y objetivo

### Implementación actual

El subflujo `CREDENCIALES` abre un `config.xlsx` compartido localmente y carga
los valores de las celdas `B2` y `B3` en las variables `USER3270` y
`PASS3270`. El archivo se abre sin mostrar Excel y se cierra al terminar la
lectura.

Esta es una configuración transitoria. La ruta concreta, el usuario y la
contraseña no se documentan, no se registran en logs y no se incorporan a Git.

### Estado objetivo

`config.xlsx` debe conservar solo parámetros no sensibles: proceso, usuario
lógico, sesión, centro y nombre lógico de credencial. La contraseña debe
recuperarse en tiempo de ejecución desde un almacén seguro o una variable
secreta de Power Automate. El cambio no está implementado aún.

## Secuencia exacta de `AsegurarSesion3270`

| Paso | Acción PAD | Resultado validado |
| ---: | --- | --- |
| 1 | Ejecutar `CREDENCIALES`. | Se cargan `USER3270` y `PASS3270` sin exponer sus valores. |
| 2 | Ejecutar `C:\Data\3270.WS`. | PCOMM queda abierto. |
| 3 | Esperar 10 segundos. | Espera fija usada por el flujo corporativo de referencia. |
| 4 | Abrir sesión de terminal HLLAPI `A`. | Se obtiene `TerminalSession`. |
| 5 | Mover a fila 24, columna 24; escribir `C`; transmitir. | Se selecciona la aplicación inicial. |
| 6 | Esperar 1 segundo. | El formulario de autenticación queda disponible. |
| 7 | Escribir usuario en 4/34 y contraseña en 5/34; transmitir. | Inicio de sesión 3270. |
| 8 | Esperar 1 segundo; leer 28 caracteres desde 1/1. | Se evalúa el indicador de bloqueo. |
| 9 | Si el texto contiene `BLOQUEA`, cerrar `TerminalSession` y finalizar. | La alerta Teams existe, pero está deshabilitada en el Robin actual. |
| 10 | Ejecutar `LIMPIAR_VENTANA`. | Envía `Clear` tres veces sobre `TerminalSession`. |
| 11 | Escribir `qgtr` en el cursor actual y transmitir. | Se solicita cambio de centro. |
| 12 | Esperar el texto `BXA0147` hasta 30 segundos; enviar `Clear`. | Se reconoce y confirma la pantalla intermedia real. |
| 13 | Escribir `0727` en el cursor actual y transmitir. | El host deja el cursor en el campo editable. |
| 14 | Esperar 2 segundos y ejecutar `LIMPIAR_VENTANA`. | La sesión queda lista para la macro. |
| 15 | Cerrar `TerminalSession`. | Libera HLLAPI; PCOMM y la sesión `A` permanecen abiertos. |

Las acciones de mover cursor a 1/1 antes de `qgtr` y a 4/34 antes de `0727`
quedaron deshabilitadas. No deben reactivarse sin una nueva prueba PBO. El host
posiciona el cursor tras `Clear`; moverlo manualmente llevó a una zona protegida
y rechazó el valor del centro.

`LIMPIAR_VENTANA` es un subflujo requerido, no una acción implícita:

```text
Clear
Clear
Clear
```

No cierra PCOMM.

## Tratamiento de Teams y bloqueo

El Robin contiene acciones de Teams para inicio de login y usuario bloqueado,
pero figuran como `DISABLE External.InvokeCloudConnector`. Están configuradas
pero deshabilitadas en el Desktop Flow actual; no cuentan como alertas
operativas ni como evidencia de aceptación.

La rama de usuario bloqueado termina actualmente con código 0. Debe evolucionar
a un estado técnico explícito, por ejemplo `3270_USUARIO_BLOQUEADO`, para que
una falla funcional no se interprete como éxito.

## Transferencia a la macro

Al volver a `ValidarExcel`, PAD ejecuta `macro_3270_runner.py` mediante
`cmd.exe /d /c`, espera a que termine y usa:

```text
--config "%RutaConfiguracion%" browse-lot --lot "%IdLote%"
```

VBA vuelve a conectarse mediante `CONEXION.Init "A"` y realiza la consulta
segura:

```text
PAUSA -> I003 -> opción 01 -> préstamo -> ENTER
```

Por ello es indispensable cerrar el manejador HLLAPI de PAD antes de invocar la
macro, sin cerrar PCOMM.

## Evidencia y criterio de aceptación

Partiendo de PCOMM cerrado, se acepta `AsegurarSesion3270` cuando:

1. PAD abre el perfil y se adjunta a HLLAPI sesión `A`.
2. La autenticación se completa y no se detecta `BLOQUEA`.
3. `qgtr` es aceptado, aparece `BXA0147`, se confirma con `Clear` y `0727` es
   aceptado desde el cursor actual.
4. PAD libera `TerminalSession`; PCOMM permanece abierto con sesión `A`
   disponible.
5. `browse-lot` vuelve a adjuntarse y consulta `PAUSA -> I003 -> 01 -> préstamo
   -> ENTER` sin preparación manual ni escritura de negocio.

## Incidencias resueltas y aprendizaje

| Síntoma | Causa comprobada | Corrección validada |
| --- | --- | --- |
| `Se rechazó el texto de entrada` al enviar `0727`. | El cursor se movía a una posición protegida. | Escribir el centro en la posición actual después de confirmar `BXA0147`. |
| Timeout esperando cambio de centro. | Tras `qgtr` aparece primero `BXA0147`. | Esperar `BXA0147`, enviar `Clear` y continuar. |
| `qgtr` no progresaba. | Faltaba confirmar el contexto de host tras login. | Ejecutar `LIMPIAR_VENTANA` antes del comando. |
| Error de subflujo inexistente. | La copia de la lógica omitió `LIMPIAR_VENTANA`. | Versionar y llamar el subflujo auxiliar. |
| Doble login. | La preparación se llamaba desde `Main` y `ValidarExcel`. | Llamarla solo desde `ValidarExcel`. |
| Ruta de configuración ausente. | Se heredó una variable de otro proceso. | Usar configuración explícita del proceso, sin valores sensibles en el flujo. |
| VBA no lograba adjuntarse. | PAD mantenía HLLAPI abierto. | Cerrar `TerminalSession` al final y conservar PCOMM abierto. |

Las acciones de terminal se basan en [la configuración HLLAPI de Microsoft](https://learn.microsoft.com/en-us/power-automate/desktop-flows/how-to/terminal-emulation-open-new-session) y su [referencia de terminal](https://learn.microsoft.com/es-es/power-automate/desktop-flows/actions-reference/terminalemulation).
