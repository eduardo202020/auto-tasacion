# Resumen de resultado 3270 en Microsoft Teams

## Configuración vigente en PAD

`ValidarExcel` ya separa el resultado técnico de `macro_3270_runner.py` del
resultado funcional del lote. La secuencia configurada en el Desktop Flow es:

```text
ValidarExcel
|
├── AsegurarSesion3270
├── Ejecutar aplicación: cmd.exe /d /c ... macro_3270_runner.py ... browse-lot
│   └── espera a que termine y guarda AppExitCode
└── IF AppExitCode = 0
    ├── Sí  -> RESUMEN_RESULTADO_3270
    └── No  -> mensaje Teams de error técnico
```

En la condición de PAD, `AppExitCode` se compara como número contra `0`; no se
usa la cadena de texto `"0"`.

`RESUMEN_RESULTADO_3270` publica el resumen directo de PAD en el chat
corporativo. El JSON durable del runner es la fuente de verdad; Teams solo
presenta una vista segura para el operador.

## Dos niveles de resultado

| Nivel | Evidencia | Interpretación |
| --- | --- | --- |
| Técnico | `AppExitCode` | `0` indica que el runner terminó técnicamente; otro valor exige alerta roja y no se interpreta el resultado funcional. |
| Funcional | `<ID_LOTE>_<SHA>_macro_3270.json` | Determina si la consulta fue correcta, terminó con incidencias o registró un error funcional. |

Por ello, `AppExitCode = 0` no significa que todos los casos estén correctos.
Una ejecución técnicamente completa puede quedar en
`CONSULTADO_SIN_CAMBIOS_3270_CON_INCIDENCIAS`.

## Artefacto y contenido del resumen

El subflujo lee el JSON más reciente que coincida exactamente con el lote en el
directorio de resultados configurado para PAD, con este patrón:

```text
<ID_LOTE>_<SHA>_macro_3270.json
```

El mensaje debe derivar de ese mismo JSON e incluir únicamente:

- ID de lote;
- estado global y modo de ejecución;
- casos procesados, correctos e incidencias;
- categorías de `resultado_3270` con su conteo;
- duración, tomada de las marcas de tiempo del artefacto cuando esté disponible;
- nombre del Excel publicado, sin su ruta local.

No publica préstamos, `ID_CASO`, rutas, usuario, contraseñas ni detalles del
error técnico. El detalle por caso permanece en el JSON, `TRAZA_PAD` y la
evidencia local del lote.

## Semáforo operacional

| Estado Teams | Condición |
| --- | --- |
| Verde | `AppExitCode = 0`, estado `CONSULTADO_SIN_CAMBIOS_3270` y todos los casos `CONSULTA_3270_OK`. |
| Ámbar | `AppExitCode = 0` y estado `CONSULTADO_SIN_CAMBIOS_3270_CON_INCIDENCIAS`. |
| Rojo | `AppExitCode <> 0` o estado JSON `ERROR_MACRO_3270`. |

Cuando el código técnico no es `0`, `ValidarExcel` ya publica un mensaje rojo
con el lote, estado `ERROR`, el código técnico y una indicación de validar antes
de reintentar. Esa rama no intenta leer ni resumir un JSON funcional.

## Evidencia E2E requerida

La configuración manual está hecha, pero el resumen directo de PAD todavía se
considera **pendiente de evidencia E2E**. Para cerrarlo con un lote nuevo se
debe comprobar:

1. `AppExitCode = 0` en la ejecución de PAD.
2. Un JSON del mismo lote con estado
   `CONSULTADO_SIN_CAMBIOS_3270` o su variante con incidencias.
3. El libro `.xlsm` publicado y su `TRAZA_PAD` con el resultado por caso.
4. Un único mensaje estilizado en Teams cuyos conteos, estado y nombre del
   libro coincidan con el JSON.

`browse-lot` se mantiene como la operación de prueba. Esta validación no
habilita `run-lot` ni realiza cambios en 3270.

## Ciclo de vida esperado

Al completar la consulta, Excel, Python y `cmd.exe` deben terminar; PAD termina
`ValidarExcel`. PCOMM/3270 permanece abierto de forma intencional en la sesión
`A`: `AsegurarSesion3270` libera solamente `TerminalSession` de HLLAPI para que
Excel/VBA pueda adjuntarse. No se debe usar el script heredado que mata procesos
PCOMM como cierre normal.

## Soporte versionado reutilizable

[`Format-Macro3270TeamsSummary.ps1`](../../power-platform/pad/Format-Macro3270TeamsSummary.ps1)
es una referencia reutilizable para implementar el formateo a partir del JSON.
No describe ni sustituye el subflujo manual vigente
`RESUMEN_RESULTADO_3270`; puede reutilizarse cuando otro proceso necesite el
mismo contrato de entrada y salida HTML.

## Evitar cierres duplicados

El Cloud Flow `auto-tasacion-activar-pad` conserva por ahora su cierre genérico.
Después de validar visualmente el mensaje directo de PAD en una ejecución nueva,
se puede retirar solo ese cierre y mantener los avisos Cloud de inicio y error:

```powershell
.\power-platform\scripts\Update-PadTeamsNotifications.ps1 `
  -DryRun `
  -SuccessNotificationSource Desktop

.\power-platform\scripts\Update-PadTeamsNotifications.ps1 `
  -Activate `
  -SuccessNotificationSource Desktop
```

No se debe aplicar `-Activate` antes de conservar la evidencia E2E del mensaje
directo de PAD.
