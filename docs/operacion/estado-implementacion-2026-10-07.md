# Estado de implementación: Auto Tasación

> **Corte:** 7 de octubre de 2026

## Flujo objetivo

```text
PDFs en OneDrive /auto-tasaciones/PDFs
  -> Power Apps: selección de metadatos
  -> Power Automate: manifiesto y transferencia de un PDF por vez
  -> Cloud Storage privado
  -> Cloud Run Job
  -> Resultado_Final_<ID_LOTE>.xlsx en OneDrive
  -> Power Automate Desktop / IBM 3270
```

La ruta masiva admite hasta 300 PDFs, 2 GiB por lote y 90 000 000 bytes por
PDF. La ruta ZIP de hasta 90 MB continúa como transición y no se mezcla con
este flujo.

## Implementado y desplegado

### Servicio en Google Cloud

| Componente | Estado | Evidencia |
| --- | --- | --- |
| API de control `/v1/lotes` | Desplegada | Cloud Run `demo-tasaciones-ia` está `Ready`. |
| Manifiesto, eTag e idempotencia | Implementado | El lote usa `item_id`, nombre, eTag y tamaño; se rechazan cambios de origen. |
| Carga por PDF mediante ticket firmado | Implementado | Cada archivo se carga por separado a GCS. |
| Cloud Run Job `tasaciones-batch` | Desplegado y listo | Procesa objetos confirmados uno por iteración; última ejecución exitosa. |
| Resultado XLSX | Implementado | Genera `PARA_PROCESAR`, `REVISION_IA` y `CONTROL` con sus tablas contractuales. |
| Perfiles de tasadoras | Implementado de forma acotada | Catálogo y perfiles `generic-v1`, `braschi-construyo-v1` y `opd-construyo-v1`. |

### Power Automate

| Flujo | Estado | Propósito |
| --- | --- | --- |
| `auto-tasacion-listar-pdfs` | Publicado | Lista PDFs de `/auto-tasaciones/PDFs` para la app. |
| `auto-tasacion-iniciar-lote` | Publicado | Registra el manifiesto y crea el control del lote. |
| `auto-tasacion-cargar-lotes` | Publicado | Cada cinco minutos, transfiere PDFs individuales y arranca el Job. |
| `auto-tasacion-entregar-lote` | Publicado | Cada cinco minutos, entrega el XLSX cuando el lote termina. |
| `auto-tasacion-consultar-lote` | Borrador | Consulta de progreso para la interfaz; no bloquea la ejecución del lote. |

Los flujos y su definición reproducible están en
[`power-platform/scripts/deploy-mass-flows.ps1`](../../power-platform/scripts/deploy-mass-flows.ps1).
El script apunta a la solución corporativa `autoTasacion`.

### Power Apps

`autoTasacionJG` ya muestra los PDFs de OneDrive, permite seleccionarlos y
cuenta la selección. Esta parte usa `auto-tasacion-listar-pdfs`.

## Pendiente antes de aprobar E2E

El botón visible **Ejecutar** de `autoTasacionJG` no tiene una fórmula
`OnSelect` que llame a `auto-tasacion-iniciar-lote`. Debe agregarse el flujo
como origen de datos, aplicar la fórmula de manifiesto y publicar la app.

La fórmula, el caso inicial con `D01.pdf` y los criterios de aceptación están
en [`prueba-e2e-lotes-masivos.md`](prueba-e2e-lotes-masivos.md).

La lectura de `_autotasacion_lote_<ID_LOTE>.json` recibió inicialmente el
cuerpo binario de OneDrive en `ParseJson`. La definición fue corregida para
decodificar `body.$content` con `base64ToString` antes de convertirlo a JSON y
se publicó en los flujos de carga y entrega. La prueba de un PDF aún requiere
una nueva ejecución efectiva de `auto-tasacion-cargar-lotes`: el lote observado
permanece en `RECIBIDO`, por lo que no se aprobó ni se invocó la entrega.

La actualización automática de la Canvas App no se pudo empaquetar desde PAC:
la exportación de la solución `autoTasacion` falla por falta de lectura sobre un
flujo heredado de otro propietario. El bloqueo afecta la exportación de la
solución; no afecta los flujos masivos ya publicados ni el servicio de Google
Cloud.

## Validaciones ejecutadas

| Validación | Resultado |
| --- | --- |
| Suite del servicio Cloud Run | 61 de 61 pruebas correctas. |
| Catálogo de perfiles y tasadoras | Correcto; sin errores. |
| Compilación Python | Correcta. |
| Sintaxis de `deploy-mass-flows.ps1` | Correcta. |
| Estado de Cloud Run | Servicio y Job en estado `Ready`. |
| Prueba E2E OneDrive -> Excel | Pendiente del vínculo y publicación de `Ejecutar`. |

## Siguiente secuencia operativa

1. En Power Apps Studio, agregar `auto-tasacion-iniciar-lote` a
   `autoTasacionJG`.
2. Asignar la fórmula documentada al botón **Ejecutar** y publicar.
3. Procesar solo `D01.pdf` y verificar la creación de un `ID_LOTE`.
4. Validar las ejecuciones de carga y entrega, y
   `Resultado_Final_<ID_LOTE>.xlsx`.
5. Revisar tablas y contrato del Excel.
6. Repetir con 10, 150 y hasta 300 PDFs.

## Límites y seguridad

- Power Apps transmite solo metadatos; no transmite contenido PDF.
- Power Automate es el único componente que lee OneDrive.
- El servicio no utiliza Microsoft Graph para descargar documentos.
- No se almacenan PDFs de clientes, resultados productivos, secretos o URLs
  firmadas en este repositorio.
- `tblParaProcesar` es la única tabla que puede consumir PAD/IBM 3270.
