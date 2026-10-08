# Estado de implementación: Auto Tasación

> **Corte:** 7 de octubre de 2026

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
| `auto-tasacion-consultar-lote` | Publicado | Devuelve el estado y conteos tipados a Power Apps. |
| `auto-tasacion-cargar-lotes` | Publicado | Cada cinco minutos transfiere PDFs y arranca el Job. |
| `auto-tasacion-entregar-lote` | Publicado | Cada cinco minutos entrega el XLSX. |

La definición reproducible está en
[`power-platform/scripts/deploy-mass-flows.ps1`](../../power-platform/scripts/deploy-mass-flows.ps1).
La respuesta de `auto-tasacion-consultar-lote` no devuelve `archivos`, URLs
firmadas ni rutas GCS a Power Apps; expone solo ID, estado, mensaje y conteos.

### Power Apps

La fuente descargada de `autoTasacionJG` confirma que `Button5` es el botón
visible **Ejecutar**, `Label3` presenta `varEstadoLote` y `btnActualizar`
conserva la actualización de `colPdfs`. La causa del estado congelado en
`RECIBIDO` era que no había un Timer ni conexión al flujo
`auto-tasacion-consultar-lote`.

Las fórmulas y propiedades exactas para completar la aplicación están en
[`POLLING.md`](../../power-platform/canvas/autoTasacionJG/POLLING.md). El
Timer consulta cada 10 segundos, conserva el último estado frente a un error
transitorio y se detiene únicamente en `ENTREGADO`, `FALLIDO` o
`FALLIDO_ORIGEN_CAMBIO`. `COMPLETADO` sigue en seguimiento hasta que la entrega
del XLSX confirme `ENTREGADO`.

## Limitación de publicación de la Canvas App

La CLI permite descargar, desempaquetar y empaquetar la aplicación, pero no
actualizar ni publicar una Canvas App existente. Además, la exportación de la
solución corporativa `autoTasacion` está bloqueada por permisos de lectura sobre
un flujo heredado de otro propietario. Por eso el paso pendiente es aplicar el
documento `POLLING.md` en Power Apps Studio y publicar la aplicación. No afecta
los flujos masivos ni el procesamiento de Google Cloud.

## Validaciones del repositorio

| Validación | Resultado |
| --- | --- |
| Suite del servicio Cloud Run | 61 de 61 pruebas correctas en la última validación completa. |
| Catálogo de perfiles y tasadoras | Correcto. |
| Compilación Python | Correcta. |
| Definiciones de flujos masivos | Prueban lectura de controles y contrato tipado de consulta. |
| Sintaxis de `deploy-mass-flows.ps1` | Correcta. |

## Próxima validación de interfaz

1. En Studio, agregar `auto-tasacion-iniciar-lote` y
   `auto-tasacion-consultar-lote` como orígenes de datos de `autoTasacionJG`.
2. Aplicar `POLLING.md` a `Button5`, al nuevo `tmrEstadoLote`, `Label3` y la
   etiqueta de progreso, y publicar la aplicación.
3. Con solo `D01.pdf`, seleccionar, pulsar **Ejecutar** y observar sin acciones
   manuales `RECIBIDO` → estados intermedios → `COMPLETADO` → `ENTREGADO`.
4. Confirmar que el Excel aparece en `/auto-tasaciones` y que el Timer deja de
   consultar al llegar a `ENTREGADO`.

## Límites y seguridad

- Power Apps transmite únicamente metadatos; no transmite contenido PDF.
- Power Automate es el único componente que lee OneDrive.
- No se almacenan PDFs, resultados productivos, secretos ni URLs firmadas en
  este repositorio.
- `tblParaProcesar` es la única tabla destinada a PAD/IBM 3270.
