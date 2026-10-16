# Resumen de resultado 3270 en Microsoft Teams

## Objetivo

Al terminar `browse-lot`, PAD transforma el JSON durable
`<LOTE>_<SHA>_macro_3270.json` en un mensaje HTML para el chat de Teams. El
mensaje resume el resultado operativo sin publicar préstamos, `ID_CASO`, rutas
locales, errores técnicos, usuario ni contraseñas.

El resumen se genera localmente después de que la macro termine; no depende de
las salidas opcionales del conector Desktop Flow en Cloud.

## Contenido del mensaje

El formato incluye:

- lote, modo y estado operativo;
- número de casos enviados a 3270, correctos y con incidencias;
- indicación de exclusión de `REVISION_IA`;
- categorías de resultado de 3270 y sus conteos;
- disponibilidad del libro final en OneDrive.

Para un lote de consulta sin incidencias, el título verde es **Consulta 3270
finalizada sin cambios**. Si hay resultados no correctos usa ámbar; si el JSON
indica error técnico usa rojo y omite el detalle técnico.

## Script versionado

[`Format-Macro3270TeamsSummary.ps1`](../../power-platform/pad/Format-Macro3270TeamsSummary.ps1)
recibe el lote y la configuración ya usada por `macro_3270_runner.py`:

```powershell
& "<instalacion-pad>\Format-Macro3270TeamsSummary.ps1" `
  -ConfigPath "%RutaConfiguracion%" `
  -LotId "%IdLote%"
```

Busca el JSON más reciente que coincida exactamente con el lote bajo el
runtime configurado y escribe un único valor HTML a la salida estándar. Si no
encuentra un JSON válido, termina con error para que PAD no envíe un resumen de
otro lote.

## Cambio manual en PAD

En el subflujo `ValidarExcel`, después de la acción que ejecuta
`macro_3270_runner.py ... browse-lot` y solo en su ruta correcta:

1. Agregue **Ejecutar script de PowerShell** con el comando anterior.
2. Guarde su salida en una variable de texto, por ejemplo `ResumenTeamsHtml`.
3. Agregue **Publicar mensaje en un chat o canal** justo después.
4. Seleccione el mismo `Bot de Flow`, `Chat de grupo` y chat configurado para
   las alertas del proceso.
5. En **Mensaje**, inserte exclusivamente la variable `%ResumenTeamsHtml%`.
6. Guarde, publique y ejecute un lote nuevo de consulta.

La acción debe quedar en `ValidarExcel`, no en `AsegurarSesion3270`: el JSON
solo existe después de ejecutar la macro.

Las acciones Teams del login en `AsegurarSesion3270` siguen configuradas pero
deshabilitadas y no sustituyen este resumen final.

## Evitar mensajes finales duplicados

El flujo Cloud `auto-tasacion-activar-pad` ya puede publicar un cierre genérico.
Una vez validado el mensaje directo de PAD, conserve los avisos Cloud de inicio
y error, y actualice el generador para retirar solo el cierre genérico:

```powershell
.\power-platform\scripts\Update-PadTeamsNotifications.ps1 `
  -DryRun `
  -SuccessNotificationSource Desktop

.\power-platform\scripts\Update-PadTeamsNotifications.ps1 `
  -Activate `
  -SuccessNotificationSource Desktop
```

No ejecute `-Activate` hasta comprobar visualmente que la variable contiene el
HTML correcto para un lote nuevo. El modo `Cloud` conserva el aviso final
existente mientras prepara PAD.

## Aceptación

1. El mensaje se publica una sola vez tras el éxito de `browse-lot`.
2. El lote y los conteos coinciden con el JSON del mismo lote.
3. No aparecen préstamos, casos, rutas locales, secretos ni el error técnico.
4. El cierre genérico Cloud se retira solo después de validar el mensaje directo.
5. Una falla de PAD continúa usando el aviso Cloud de error.
