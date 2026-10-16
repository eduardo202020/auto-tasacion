# Seguimiento pendiente: cierre de presentación Auto Tasaciones

**Actualizado:** 2026-10-15
**Objetivo:** cerrar la demostración Cloud → Excel → PAD → consulta 3270 sin
realizar grabaciones en el sistema bancario.

## Estado confirmado

| Tramo | Estado | Evidencia disponible |
| --- | --- | --- |
| Canvas, selección de PDFs y registro de lote | Corregido; requiere repetición E2E | `auto-tasacion-iniciar-lote` se republicó con el token de la versión montada por Cloud Run. |
| Cloud Run y entrega de Excel | Confirmado previamente | Lote de diez PDFs entregado y Excel `Resultado_Final` generado. |
| PAD, Excel MASIVO y PCOMM | Confirmado en modo de consulta | Cuatro filas llegaron a `CONSULTA_3270_OK` con `ICA9783_SEGURO_TIPO_I`. |
| Inicio 3270 desde cerrado | Configurado en PAD | `AsegurarSesion3270` abre PCOMM, inicia sesión, deja centro `0727` y libera HLLAPI. Requiere su prueba E2E integrada con el lote. |
| Resumen directo de PAD en Teams | Configurado; pendiente de evidencia E2E | `ValidarExcel` evalúa `AppExitCode`, usa `RESUMEN_RESULTADO_3270` para éxito técnico y publica error directo en la rama contraria. |
| Cierre genérico Cloud | Sigue activo | Se retira solo después de comprobar el resumen directo de PAD, para evitar duplicidad de cierre. |
| Escritura transaccional en 3270 | Pendiente | No está autorizada en esta fase. |
| Revisión por IA de excepciones | Pendiente posterior | Se atiende después de cerrar el flujo de presentación. |

## Orden de seguimiento

### 1. Repetir el inicio de lote con el token alineado

Desde Power Apps, pulsar **Actualizar** y luego **Ejecutar** con un conjunto de
PDFs de prueba. Confirmar que `auto-tasacion-iniciar-lote` deja de responder
`NO_AUTORIZADO`, devuelve un `ID_LOTE` nuevo y crea su control en OneDrive.

**Evidencia a guardar:** historial correcto de `HTTP Registrar Lote`, ID de
lote y mensaje de registro en Teams.

### 2. Comprobar el ciclo Cloud y el Excel final

Seguir el mismo ID en `auto-tasacion-orquestar-lote` hasta `ENTREGADO` y
confirmar que se publica `Resultado_Final_<ID_LOTE>.xlsx`.

**Evidencia a guardar:** ejecución correcta del orquestador y alerta de
resultado final en Teams.

### 3. Comprobar PAD, 3270 y el artefacto funcional

Cuando aparezca el Excel final, verificar que `auto-tasacion-activar-pad`
llama al Desktop Flow una sola vez. PAD debe abrir y preparar PCOMM desde
cerrado, ejecutar `browse-lot` y conservar `AppExitCode = 0`.

El JSON `<ID_LOTE>_<SHA>_macro_3270.json` debe pertenecer al mismo lote y
terminar en `CONSULTADO_SIN_CAMBIOS_3270` o su variante con incidencias. El
libro `.xlsm` publicado debe contener `TRAZA_PAD`.

**Evidencia a guardar:** historial Cloud de activación, código técnico PAD,
JSON del lote, libro publicado y evidencia de consulta. PCOMM puede permanecer
abierto al terminar; es un estado intencional.

### 4. Validar el resumen final directo de PAD

En la misma ejecución, comprobar que `RESUMEN_RESULTADO_3270` publica una sola
vez en Teams. El mensaje debe coincidir con el JSON del lote y mostrar lote,
estado, modo, conteos, categorías de resultado, duración y nombre del libro,
sin datos por caso ni rutas locales.

Si `AppExitCode` es distinto de `0`, debe llegar la alerta roja y PAD no debe
intentar interpretar el resultado funcional.

**Evidencia a guardar:** captura del mensaje estilizado y JSON del mismo lote.

### 5. Retirar el cierre genérico Cloud y cerrar la presentación

Solo después del paso anterior, ejecutar primero:

```powershell
.\power-platform\scripts\Update-PadTeamsNotifications.ps1 `
  -DryRun `
  -SuccessNotificationSource Desktop
```

Luego aplicar el mismo comando con `-Activate`. Conservar el ID del lote de
prueba, duración total, número de PDFs, filas `PARA_PROCESAR`, resultado 3270 y
ubicación del Excel final como evidencia de cierre.

## Trabajo posterior a la presentación

1. Resolver los casos en `REVISION_IA` con las reglas aprobadas por
   Operaciones.
2. Migrar las credenciales temporales de 3270 a un almacén seguro.
3. Hacer que la rama de usuario bloqueado devuelva un estado técnico de error.
4. Validar los datos de negocio de una muestra antes de habilitar escritura en
   3270.
5. Solicitar una autorización explícita para cambiar `browse-lot` por
   `run-lot`.
