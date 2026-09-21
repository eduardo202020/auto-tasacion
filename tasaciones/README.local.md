# Desarrollo local de tasaciones

## Herramientas instaladas

- Python virtual environment: `funcions/.venv`
- Apps Script CLI: `clasp`
- Google Cloud CLI: `gcloud`

Abre una terminal nueva después de esta configuración para que `gcloud` esté disponible en el `PATH`.

## Ejecutar la función Python localmente

```bash
cd /ruta/a/auto-tasacion/tasaciones
source funcions/.venv/bin/activate
npm run cloud:local
```

En otra terminal, verifica el contrato HTTP sin acceder a Drive ni a datos reales:

```bash
curl --request POST http://localhost:8080 \
  --header 'Content-Type: application/json' \
  --data '{"filas":[["Nombre del PDF","File ID (Sistema)"]]}'
```

El resultado esperado contiene `"status": "success"` y una lista vacía de resultados.

## Conectar Apps Script sin editar en el navegador

1. En [Ajustes de Apps Script](https://script.google.com/home/usersettings), habilita la **Apps Script API** con la cuenta corporativa. Es un requisito de `clasp push`.
2. Ejecuta `clasp login` y completa la autenticación con la cuenta corporativa autorizada.
3. Copia `.clasp.json.example` a `.clasp.json` y reemplaza el valor de `scriptId`.
4. Antes de modificar o subir archivos, ejecuta `npm run apps:status` y compara el resultado con el editor web.
5. Usa `npm run apps:push` solo cuando hayas verificado el diff. El comando reemplaza el contenido remoto del proyecto.

La configuración usa `appscript/` como raíz. Conserva `PanelRevision.html` como HTML y los archivos de servidor como `.js`.

## Autenticación de Google Cloud

El entorno local está asociado al proyecto corporativo de desarrollo autorizado y a la región configurada. Para cambiarlo, usa:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project ID_DEL_PROYECTO_DE_DESARROLLO
gcloud config set run/region REGION_APROBADA
```

No uses la carpeta de producción, PDFs reales ni credenciales de servicio en las pruebas locales. Para Drive privado, la siguiente evolución es reemplazar las URL públicas por Drive API y una identidad de servicio de mínimo privilegio.

## Publicar la función

El directorio `funcions/.gcloudignore` evita que el entorno virtual local se
suba a Cloud Run. Desde esta carpeta, publica la versión validada con:

```bash
gcloud run deploy demo-tasaciones-ia --source funcions \
  --function procesar_tasaciones --base-image python311 \
  --region northamerica-northeast1
```
