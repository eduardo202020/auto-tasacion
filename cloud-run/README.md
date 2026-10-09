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
| `BATCH_ORCHESTRATION_LEASE_SECONDS` | Reserva renovable del orquestador, por defecto 10 800 segundos (3 horas). |
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

`POST /v1/lotes/{id}/iniciar` persiste `EN_PROCESO` antes de solicitar el
Cloud Run Job. El Job escribe el XLSX en Cloud Storage y solo entonces
persiste `COMPLETADO` con `resultado_disponible = true`. El resultado se puede
pedir con ticket en ese punto. `ENTREGADO` se reserva para `POST /entrega`, que
Power Automate llama después de crear el XLSX en OneDrive. Las transiciones del
manifiesto son monotónicas: un reintento no puede regresar un lote completado o
entregado a un estado anterior.

El manifiesto conserva `fecha_inicio` desde su registro. `fecha_fin` se fija
una sola vez si el lote queda `ENTREGADO`, `FALLIDO` o
`FALLIDO_ORIGEN_CAMBIO`. `GET /v1/lotes/{id_lote}` devuelve estas fechas en
ISO-8601 UTC y `duracion_segundos`; durante la ejecución la duración se
calcula contra el reloj UTC y al terminar queda fija.

### Orquestación por evento e idempotencia

`POST /v1/lotes/{id}/orquestacion/reclamar` recibe un `id_ejecucion` de Power
Automate y registra una reserva atómica en el manifiesto. Mientras la reserva
está vigente, otro evento del mismo control recibe `OCUPADO` y no puede cargar
PDFs, iniciar otro Job ni entregar otro XLSX. La misma ejecución puede renovar
la reserva mediante `POST /v1/lotes/{id}/orquestacion/renovar` antes de cada
PDF, antes del Job y durante la espera del resultado.

`POST /v1/lotes/{id}/orquestacion/liberar` registra un reintento requerido sin
retroceder el estado del lote. Se usa al superar la ventana de espera del flujo;
el control de OneDrive permanece para que una intervención operativa lo vuelva
a disparar. Los estados de negocio siguen siendo monotónicos y `ENTREGADO`,
`FALLIDO` y `FALLIDO_ORIGEN_CAMBIO` no vuelven a ser reclamables.

## Pruebas locales

```bash
cd cloud-run
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe ../tools/validate_profile_catalog.py
.venv/Scripts/python.exe -m compileall -q . ../tools
```

No habilites IA, no guardes secretos ni despliegues sin la aprobación
correspondiente.
