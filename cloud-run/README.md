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
  correcciones aceptadas.

La primera validación es determinista y se basa en el flujo de Colab. Los
códigos de tipo de inmueble, moneda, dirección y clase se leen del catálogo
versionado de la hoja `DATOS`. Cuando se habilita, Gemini recibe solo PDFs de
casos excepcionales y debe devolver valor, página y evidencia en JSON. La fila
solo pasa a `PARA_PROCESAR` después de una segunda validación determinista.

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
  --base-image python311 \
  --region northamerica-northeast1
```

El despliegue es una acción separada de los cambios locales y debe realizarse
solo con aprobación del entorno corporativo.
