# Servicio Cloud Run

Este servicio recibe un ZIP binario de tasaciones desde Power Automate y
devuelve `Resultado_Final.xlsx`.

## Contrato HTTP

- Método: `POST`
- Encabezado: `Content-Type: application/zip`
- Cuerpo: ZIP con hasta 300 archivos PDF.
- Respuesta exitosa: XLSX con las hojas `PARA_PROCESAR`, `REVISION_IA` y
  `CONTROL`.

La respuesta contiene estas tablas de Excel:

- `PARA_PROCESAR` / `tblParaProcesar`: conserva las 24 columnas de integración
  y añade al final `ID_CASO` para la trazabilidad de Power Automate. Solo
  contiene filas completas y validadas.
- `REVISION_IA` / `tblRevisionIa`: excepciones que no pudieron entrar a la
  cola operable, con faltantes, evidencia y siguiente acción.
- `CONTROL` / `tblControl`: una fila por PDF, con evidencias, ruta final y
  correcciones aceptadas. Incluye el perfil de plantilla detectado y sus
  coincidencias para auditar diferencias de formato entre tasadoras.

La primera validación es determinista y se basa en el flujo de Colab. Los
códigos de tipo de inmueble, moneda, dirección y clase se leen del catálogo
versionado de la hoja `DATOS`. Cuando se habilita, Gemini recibe solo PDFs de
casos excepcionales y debe devolver valor, página y evidencia en JSON. La fila
solo pasa a `PARA_PROCESAR` después de una segunda validación determinista.

## Perfiles de plantilla

El extractor comienza con las reglas generales y busca una firma explícita de
plantilla en el PDF. Los perfiles declarativos están en
`reference-data/profiles/`; pueden aportar alias de etiquetas que varían por
formato. `generic-v1` es el respaldo cuando no hay una coincidencia conocida.

El catálogo `reference-data/tasadoras.json` está separado de los perfiles:
una empresa solo se identifica cuando existe un alias versionado. Ningún PDF
desconocido crea una empresa, un perfil o una regla automáticamente. Consulta
[`docs/operacion/perfiles-tasadoras.md`](../docs/operacion/perfiles-tasadoras.md)
para registrar y validar correcciones humanas.

Antes de incorporar una tasadora o un perfil, valida la configuración local:

```bash
python tools/validate_profile_catalog.py
```

La empresa detectada solo agrega trazabilidad. Los alias de extracción se
incorporan únicamente en perfiles técnicos con evidencia repetida y pruebas
sintéticas.

## Detección local de logos

Cuando una tasadora solo aparece como imagen o logo, el servicio aplica OCR
local a las franjas de encabezado y pie de las primeras tres páginas. El texto
resultante se compara únicamente con las firmas de `tasadoras.json`; no se
registra ni se envía a Gemini u otro servicio externo. Si OCR no está
disponible o no identifica una firma única, el caso conserva `generic-v1`.

La imagen de Cloud Run instala Tesseract mediante el `Dockerfile`. El origen
se despliega con ese Dockerfile cuando está presente.

## Ejecutar localmente

```bash
cd cloud-run
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
functions-framework --target procesar_tasaciones --source main.py --debug
```

## Revisión IA

Por defecto está desactivada. No pongas la clave en `.env`, código o Git. En
Cloud Run, entrega `GEMINI_API_KEY` mediante Secret Manager y configura:

```text
AI_REVIEW_ENABLED=true
GEMINI_MODEL=<modelo Gemini aprobado>
```

Antes de activarla, Seguridad debe aprobar el envío de PDFs y Operaciones debe
convertir las decisiones aprobadas del archivo
`docs/REGLAS_NEGOCIO_PENDIENTES.txt` en reglas versionadas dentro de
`reference-data/reglas_operativas.json`. Un conflicto sin regla aprobada queda
en `REVISION_IA` y nunca se completa automáticamente.

En otra terminal, envía un ZIP de prueba:

```bash
curl --request POST http://localhost:8080 \
  --header 'Content-Type: application/zip' \
  --data-binary @/ruta/al/lote.zip \
  --output Resultado_Final.xlsx
```

## Despliegue

Después de probar el lote con datos autorizados y revisar el Excel, publica
desde la raíz del repositorio:

```bash
gcloud run deploy demo-tasaciones-ia \
  --source cloud-run \
  --function procesar_tasaciones \
  --region northamerica-northeast1
```

El despliegue es una acción separada de los cambios locales y debe realizarse
solo con aprobación del entorno corporativo.


## Carga temporal mediante Cloud Storage

El POST binario directo se conserva para ZIP de hasta 30 MiB. Para ZIP de hasta 75 MiB:

1. Enviar `POST` JSON al endpoint: `{"operacion":"iniciar_carga","nombre_archivo":"auto-10.zip","tamano_bytes":49810784}`.
2. La respuesta `201` contiene `url_carga`, `objeto` y el encabezado `Content-Type: application/zip`. Hacer `PUT` del ZIP a esa URL en los siguientes 15 minutos.
3. Enviar `POST` JSON: `{"operacion":"procesar_carga","objeto":"<objeto devuelto>"}`. La respuesta es `Resultado_Final.xlsx`.

Configurar `GCS_UPLOAD_BUCKET` y `GCS_SIGNING_SERVICE_ACCOUNT` en Cloud Run. El bucket debe ser privado, con acceso uniforme y ciclo de vida de un d?a para `ingresos/`.
