# Seguimiento pendiente: cierre de presentación Auto Tasaciones

**Actualizado:** 2026-10-14
**Objetivo:** cerrar la demostración completa Cloud → Excel → PAD → consulta
3270 sin realizar grabaciones en el sistema bancario.

## Estado confirmado

| Tramo | Estado | Evidencia disponible |
| --- | --- | --- |
| Canvas, selección de PDFs y registro de lote | Corregido; requiere repetición E2E | `auto-tasacion-iniciar-lote` se republicó con el token de la versión montada por Cloud Run. |
| Cloud Run y entrega de Excel | Confirmado previamente | Lote de diez PDFs entregado y Excel `Resultado_Final` generado. |
| PAD, Excel MASIVO y PCOMM | Confirmado en modo de consulta | Cuatro filas llegaron a `CONSULTA_3270_OK` con `ICA9783_SEGURO_TIPO_I`. |
| Alertas Teams | Eventos E2E confirmados; salida PAD pendiente de completar | Registro, entrega, inicio y fin llegan al chat. La alerta final de PAD debe devolver estado y mensaje no vacíos. |
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

### 3. Comprobar activación automática de PAD

Cuando aparezca el Excel final, verificar que `auto-tasacion-activar-pad`
llama al Desktop Flow y que el estado local de
`pad-runtime/estado/macro_3270` termina sin `technical_error`.

Para la demostración vigente, PAD debe conservar el comando `browse-lot` y
producir `CONSULTADO_SIN_CAMBIOS_3270` por los casos completos. No debe usar
`run-lot` durante esta etapa.

**Evidencia a guardar:** mensajes de inicio y fin de PAD en Teams, JSON de
estado del lote y libro `.xlsm` publicado en `Procesados`.

### 4. Revisar la experiencia del operador

Confirmar que Power Apps muestra el `ID_LOTE`, el avance hasta `ENTREGADO` y
no presenta el mensaje genérico de error. Validar que los mensajes de Teams
contienen solo lote, estado, conteos y nombre de salida. En la alerta final de
PAD, validar específicamente que `EstadoPad` y `MensajePad` no estén vacíos;
un envío correcto con esos campos vacíos no cierra esta revisión.

### 5. Cerrar la presentación

Registrar el ID del lote de prueba, duración total, número de PDFs, filas de
`PARA_PROCESAR`, resultado de la consulta 3270 y ubicación del Excel final.
Con esa evidencia se considera cerrada la demostración sin cambios en 3270.

## Trabajo posterior a la presentación

1. Resolver los casos en `REVISION_IA` con las reglas aprobadas por
   Operaciones.
2. Validar los datos de negocio de una muestra antes de habilitar escritura en
   3270.
3. Solicitar una autorización explícita para cambiar `browse-lot` por
   `run-lot`.
4. Rotar el secreto de control expuesto durante el diagnóstico, actualizar la
   referencia de Cloud Run a la nueva versión y republicar los flujos con
   `deploy-mass-flows.ps1`.
