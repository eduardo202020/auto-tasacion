# Servicio Cloud Run

## Contrato Excel

El servicio produce `Resultado_Final.xlsx` con las hojas `PARA_PROCESAR`,
`REVISION_IA` y `CONTROL`. `tblParaProcesar` conserva sus 24 columnas y
`ID_CASO` al final. Solo filas completas y validadas llegan a la tabla operable.

## Ruta ZIP heredada

`POST application/zip` y las operaciones JSON `iniciar_carga` /
`procesar_carga` se conservan como **LEGACY / TRANSICIÓN**. El límite de esa
ruta es 90 MB; no sirve para la ruta masiva.

## Ruta masiva de PDFs individuales

La API de control se expone bajo `/v1/lotes`. Registra manifiestos y emite URLs
firmadas de un PDF por vez; no recibe contenido de PDFs en sus endpoints JSON.

| Variable | Uso |
| --- | --- |
| `GOOGLE_CLOUD_PROJECT` | Proyecto que invoca el Cloud Run Job. |
| `BATCH_STATE_BUCKET` | Bucket de manifiestos JSON; usa `GCS_UPLOAD_BUCKET` como respaldo. |
| `BATCH_STORAGE_BUCKET` | Bucket de PDFs y resultados; usa `GCS_UPLOAD_BUCKET` como respaldo. |
| `BATCH_SIGNING_SERVICE_ACCOUNT` | Cuenta que firma tickets PDF; usa `GCS_SIGNING_SERVICE_ACCOUNT` como respaldo. |
| `BATCH_MAX_PDFS` | Máximo de PDFs, por defecto 300. |
| `BATCH_MAX_TOTAL_BYTES` | Máximo total del manifiesto, por defecto 2 GiB. |
| `BATCH_MAX_PDF_BYTES` | Máximo por PDF, por defecto 90 000 000 bytes. |
| `BATCH_JOB_NAME`, `BATCH_JOB_REGION` | Job que procesa el manifiesto; requiere `GOOGLE_CLOUD_PROJECT`. |
| `BATCH_CONTROL_API_TOKEN` | Secreto requerido en `X-Batch-Control-Token` para habilitar la API de control. |

El Job ejecuta:

```bash
python batch_worker.py \
  --batch-id "$BATCH_ID" \
  --input-prefix "$BATCH_INPUT_PREFIX" \
  --output-xlsx "$BATCH_OUTPUT_XLSX"
```

Descarga solamente un PDF confirmado por iteración y genera
`Resultado_Final_<ID_LOTE>.xlsx` en GCS. No usa ZIP masivo, GCS FUSE ni
Microsoft Graph.

### Estado y tiempo del lote

El manifiesto conserva `fecha_inicio` desde su registro. `fecha_fin` se fija
una sola vez si el lote queda `ENTREGADO`, `FALLIDO` o
`FALLIDO_ORIGEN_CAMBIO`. `GET /v1/lotes/{id_lote}` devuelve estas fechas en
ISO-8601 UTC y `duracion_segundos`; durante la ejecución la duración se
calcula contra el reloj UTC y al terminar queda fija.

## Pruebas locales

```bash
cd cloud-run
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe ../tools/validate_profile_catalog.py
.venv/Scripts/python.exe -m compileall -q . ../tools
```

No habilites IA, no guardes secretos ni despliegues sin la aprobación
correspondiente.
