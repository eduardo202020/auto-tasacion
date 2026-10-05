# Entorno local de desarrollo

## Requisitos

- Linux o entorno compatible con shell POSIX.
- Python 3.11 o la versión admitida por la imagen base de Cloud Run.
- `pip` y `venv`.
- Google Cloud CLI únicamente para inspeccionar o publicar cuando exista
  autorización. No es necesaria para ejecutar pruebas locales.
- VS Code con la extensión Python. Las tareas del repositorio están en
  [`.vscode/tasks.json`](../.vscode/tasks.json).

No se necesita Excel, Power Automate, acceso a OneDrive, Gemini ni IBM 3270
para las pruebas unitarias del servicio.

## Preparación inicial

Desde la raíz del repositorio:

```bash
cd cloud-run
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`.venv/` está ignorado por Git. Usa una copia de `.env.example` solo para
configuración local no sensible; no añadas credenciales reales al archivo.

## Comandos de trabajo

```bash
# Desde la raíz del repositorio
./cloud-run/.venv/bin/python -m unittest discover -s cloud-run/tests -v

# Comprobación de sintaxis
./cloud-run/.venv/bin/python -m compileall -q cloud-run

# Servidor local compatible con Cloud Run
cd cloud-run
.venv/bin/functions-framework --target procesar_tasaciones --source main.py --debug
```

Para probar el contrato HTTP en otra terminal, usa solo un ZIP de prueba
autorizado:

```bash
curl --request POST http://localhost:8080 \
  --header 'Content-Type: application/zip' \
  --data-binary @/ruta/al/lote-prueba.zip \
  --output /tmp/Resultado_Final.xlsx

./cloud-run/.venv/bin/python tools/verify_workbook.py /tmp/Resultado_Final.xlsx
```

El cuerpo se transmite como binario, no como JSON ni Base64.

## Variables de entorno

| Variable | Valor local seguro | Uso |
|---|---|---|
| `AI_REVIEW_ENABLED` | `false` | Mantiene la IA deshabilitada. |
| `GEMINI_API_KEY` | No configurar en archivos versionados. | Solo Secret Manager/entorno autorizado. |
| `GEMINI_MODEL` | No configurar hasta aprobar IA. | Modelo corporativo aprobado. |

La combinación de clave, PDF y una IA externa requiere revisión de Seguridad.
La habilitación de IA no autoriza resolver conflictos de negocio sin reglas.

## Alcance de los datos locales

Los insumos con información de negocio viven fuera del repositorio en
`_referencias_locales/` o en ubicaciones corporativas autorizadas. Los tests
deben crear documentos sintéticos y no deben depender de esos insumos para
pasar.
