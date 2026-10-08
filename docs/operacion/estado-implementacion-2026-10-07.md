# Estado de implementación: Auto Tasación

> **Corte:** 8 de octubre de 2026

## Flujo objetivo

```text
PDFs en OneDrive /auto-tasaciones/PDFs
  -> Power Apps: selección de metadatos y seguimiento de lote
  -> Power Automate: manifiesto y transferencia de un PDF por vez
  -> Cloud Storage privado -> Cloud Run Job
  -> Resultado_Final_<ID_LOTE>.xlsx en OneDrive
  -> Power Automate Desktop / IBM 3270
```

La ruta masiva admite hasta 300 PDFs, 2 GiB por lote y 90 000 000 bytes por
PDF. La ruta ZIP de hasta 90 MB continúa como transición y no se mezcla con
este flujo.

## Implementado y validado

### Servicio y procesamiento

| Componente | Estado | Evidencia |
| --- | --- | --- |
| API de control `/v1/lotes` | Desplegada | Controla manifiesto, eTag e idempotencia. |
| Carga por PDF mediante ticket firmado | Implementada | Power Automate carga un PDF por iteración. |
| Cloud Run Job `tasaciones-batch` | Desplegado | Procesa objetos confirmados. |
| Resultado XLSX | Implementado | Genera `PARA_PROCESAR`, `REVISION_IA` y `CONTROL`. |
| E2E de un PDF hasta Excel | Confirmado | La ejecución llegó a entrega, creó el Excel y eliminó el control. |

El endpoint de estado devuelve también `archivos` al cargador para identificar
PDFs `PENDIENTE`. Esa corrección resolvió el error en el que
`Filtrar_archivos_pendientes` recibía `null`.

### Power Automate

| Flujo | Estado después de ejecutar `deploy-mass-flows.ps1 -Activate` | Propósito |
| --- | --- | --- |
| `auto-tasacion-listar-pdfs` | Publicado | Lista PDFs de `/auto-tasaciones/PDFs`. |
| `auto-tasacion-iniciar-lote` | Publicado | Registra el manifiesto y crea el control del lote. |
| `auto-tasacion-consultar-lote` | Publicado | Devuelve estado, conteos y tiempo tipado. |
| `auto-tasacion-cargar-lotes` | Publicado | Cada cinco minutos transfiere PDFs y arranca el Job. |
| `auto-tasacion-entregar-lote` | Publicado | Cada cinco minutos entrega el XLSX. |

La definición reproducible está en
[`power-platform/scripts/deploy-mass-flows.ps1`](../../power-platform/scripts/deploy-mass-flows.ps1).
La respuesta de `auto-tasacion-consultar-lote` no devuelve `archivos`, URLs
firmadas ni rutas GCS a Power Apps; expone ID, estado, mensaje, conteos,
`fecha_inicio`, `fecha_fin` y `duracion_segundos`.

### Power Apps

La aplicación `autoTasacionJG` ya consulta el lote y se comprobó
manualmente que llega a `varEstadoLote = "ENTREGADO"` y deja
`varMonitorearLote = false`. `Button5` es el botón visible **Ejecutar**,
`Label3` presenta `varEstadoLote` y `btnActualizar` conserva la actualización
de `colPdfs`.

Las fórmulas y propiedades exactas para completar la aplicación están en
[`POLLING.md`](../../power-platform/canvas/autoTasacionJG/POLLING.md). El
Timer consulta cada 10 segundos, conserva el último estado frente a un error
transitorio y se detiene únicamente en `ENTREGADO`, `FALLIDO` o
`FALLIDO_ORIGEN_CAMBIO`. `COMPLETADO` sigue en seguimiento hasta que la entrega
del XLSX confirme `ENTREGADO`. La revisión actual agrega el stepper, el Timer
visual de 750 ms y el contador reconstruible desde fechas persistidas.

## Limitación de publicación de la Canvas App

La CLI permite descargar, desempaquetar y empaquetar la aplicación, pero no
actualizar ni publicar una Canvas App existente. Además, la exportación de la
solución corporativa `autoTasacion` está bloqueada por permisos de lectura sobre
un flujo heredado de otro propietario. Por eso el paso pendiente es aplicar el
documento `POLLING.md` en Power Apps Studio y publicar la aplicación. Los
cambios de contrato de esta revisión también requieren desplegar el servicio y
regenerar los flujos antes de actualizar el origen de datos de la app. No afecta
la recurrencia de los flujos masivos ni el procesamiento de Google Cloud.

## Validaciones del repositorio

| Validación | Resultado |
| --- | --- |
| Suite del servicio Cloud Run | 65 de 65 pruebas correctas en la validacion local del 8 de octubre de 2026. |
| Catálogo de perfiles y tasadoras | Correcto. |
| Compilación Python | Correcta. |
| Definiciones de flujos masivos | 12 de 12 pruebas correctas: control JSON, contrato tipado, ciclo de publicación, stepper y Timer visual documentados. |
| Sintaxis de `deploy-mass-flows.ps1` | Correcta. |

## Próxima validación de interfaz

1. En Studio, agregar `auto-tasacion-iniciar-lote` y
   `auto-tasacion-consultar-lote` como orígenes de datos de `autoTasacionJG`.
2. Actualizar esos orígenes para usar los campos publicados `fecha_inicio`,
   `fecha_fin` y `duracion_segundos`.
3. Aplicar `POLLING.md` a `Button5`, `tmrEstadoLote`, `tmrVistaLote`, la
   galería de pasos y las etiquetas, y publicar la aplicación.
4. Con dos PDFs, seleccionar, pulsar **Ejecutar** y observar sin acciones
   manuales `RECIBIDO` → estados intermedios → `COMPLETADO` → `ENTREGADO`.
5. Confirmar que el Excel aparece en `/auto-tasaciones`, que el Timer deja de
   consultar al llegar a `ENTREGADO` y que el tiempo queda fijo.

## Límites y seguridad

- Power Apps transmite únicamente metadatos; no transmite contenido PDF.
- Power Automate es el único componente que lee OneDrive.
- No se almacenan PDFs, resultados productivos, secretos ni URLs firmadas en
  este repositorio.
- `tblParaProcesar` es la única tabla destinada a PAD/IBM 3270.
