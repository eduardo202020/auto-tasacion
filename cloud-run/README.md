# Servicio Cloud Run

Este servicio recibe un ZIP binario de tasaciones desde Power Automate y
devuelve `Resultado_Final.xlsx`.

## Contrato HTTP

- Método: `POST`
- Encabezado: `Content-Type: application/zip`
- Cuerpo: ZIP con hasta 300 archivos PDF.
- Respuesta exitosa: XLSX con las hojas `MASIVO` y `CONTROL_EXTRACCION`.

`MASIVO` conserva exactamente las 24 columnas usadas por la macro. La hoja
`CONTROL_EXTRACCION` mantiene los campos extraídos, páginas de evidencia y
observaciones. Un dato vacío significa que no hubo evidencia suficiente.

## Ejecutar localmente

```bash
cd cloud-run
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
functions-framework --target procesar_tasaciones --source main.py --debug
```

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
