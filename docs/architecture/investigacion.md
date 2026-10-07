Sí. Con tu aclaración, el objetivo queda mucho más preciso, y volví a contrastarlo con el estado actual de `auto-tasacion`.

Hoy el repo está bastante cerca funcionalmente, pero **la arquitectura de transporte de archivos tiene que cambiar si la condición real es “ZIP de un poco más de 1 GB”**. El resto —extracción, perfiles, OCR, Excel contractual y preparación para PAD/3270— se puede conservar.

### Lo que existe hoy vs. lo que necesitas

| Etapa | Repo actual | Objetivo |
|---|---|---|
| ZIP llega a OneDrive | ✅ | ✅ |
| Power Apps inicia el procesamiento | ✅ | ✅ |
| Power Apps envía solo referencia/ruta | Documentado, pero debe asegurarse en la implementación | ✅ obligatorio |
| OneDrive → GCS | ✅ mediante Power Automate + URL firmada | ✅ |
| Máximo ZIP backend | **90 MB** | **> 1 GB** |
| GCS → procesador | `download_as_bytes()` | Debe procesarse sin cargar todo a RAM |
| Ejecución | HTTP síncrona | Preferible asíncrona |
| Resultado Excel | ✅ devuelto y guardado en OneDrive | ✅ misma carpeta o carpeta elegida |
| PC sincroniza OneDrive | Parte del diseño operativo | ✅ |
| PAD procesa Excel | Contrato ya definido | ✅ |
| IBM 3270 | Simulado/documentado + integración PAD | ✅ |

El último commit incluso dejó:

```python
MAX_ZIP_BYTES = 90 * 1_000_000
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
```

y el procesamiento de GCS sigue haciendo:

```python
raw_data = blob.download_as_bytes()

process_zip(raw_data)
```

para después:

```python
zipfile.ZipFile(io.BytesIO(raw_data))
```

Por tanto, **hoy no soporta 1 GB**, aunque el ZIP ya llegue correctamente al bucket.

---

## El punto que cambia todo: Power Automate no debe transportar el ZIP de >1 GB

Microsoft mantiene un máximo de 100 MB por mensaje normal y **1 GB con chunking**, solo para acciones compatibles. [Microsoft Learn](https://learn.microsoft.com/en-us/power-automate/limits-and-config?utm_source=chatgpt.com)

Como tu requerimiento es:

> puede pesar un poco más de 1 GB

yo descartaría desde ya una arquitectura donde los bytes hagan esto:

```text
OneDrive
   ↓
Get file content
   ↓
Power Automate
   ↓
HTTP PUT
   ↓
GCS
```

Aunque consigamos que 700 MB funcione con chunking, volveríamos a rompernos en cuanto llegue un archivo de 1.05 GB o 1.2 GB.

### Power Automate debe orquestar, no transportar

Tu arquitectura objetivo debería pasar a ser:

```text
                    POWER APPS
                         │
                         │ RutaZip / DriveItemId
                         ▼
                  POWER AUTOMATE
                         │
                         │ solicitud pequeña
                         ▼
                BACKEND / CLOUD RUN
                         │
              obtiene ZIP de OneDrive
                         │
                         ▼
                GOOGLE CLOUD STORAGE
                         │
                    ZIP > 1 GB
                         │
                         ▼
                  CLOUD RUN JOB
                         │
                    PDF por PDF
                         │
             extracción / perfiles
                  OCR / reglas
                         │
                         ▼
              Resultado_Final.xlsx
                         │
                         ▼
                 Cloud Storage
                         │
                         ▼
                  POWER AUTOMATE
                         │
                   Excel pequeño
                         │
                         ▼
                     ONEDRIVE
                         │
                   sincronización
                         │
                         ▼
                    PC OPERADOR
                         │
                         ▼
              POWER AUTOMATE DESKTOP
                         │
                         ▼
                     IBM 3270
```

Eso sí cumple tu objetivo real.

---

# ¿Cómo llevar OneDrive → GCS sin pasar el GB por Power Automate?

Aquí hay dos alternativas serias.

### Opción 1 — Cloud Run descarga el ZIP directamente de OneDrive

Esta sería mi preferida.

Power Apps solamente manda:

```text
RutaZip
o
DriveItemId
```

Power Automate manda al backend algo pequeño:

```json
{
  "driveItemId": "...",
  "nombre": "tasaciones.zip",
  "carpetaResultado": "..."
}
```

Después Cloud Run utiliza Microsoft Graph para leer el archivo desde OneDrive y transferirlo hacia GCS.

Quedaría:

```text
OneDrive
      │
      │ Microsoft Graph
      ▼
Cloud Run
      │
      │ stream
      ▼
GCS
```

**Power Automate nunca contiene 1 GB de datos.**

Eso elimina de raíz:

```text
Power Apps Base64
Power Automate 100 MB
Power Automate 1 GB chunking
HTTP action limits
```

El coste es que necesitamos autenticar el backend contra Microsoft 365 mediante una App Registration/service principal con el acceso corporativo apropiado.

Arquitectónicamente es la mejor solución.

---

# Opción 2 — Darle a Cloud Run una URL temporal de descarga de Microsoft

También podríamos hacer:

```text
Power Automate
   ↓
obtiene referencia/URL temporal
   ↓
Cloud Run
   ↓
descarga directamente
   ↓
GCS
```

Así Power Automate sigue orquestando pero tampoco mueve el archivo.

Puede ser más sencillo inicialmente, dependiendo de qué permisos Microsoft permita en vuestro tenant.

La condición sería cuidar muy bien la URL temporal porque da acceso al archivo durante su vigencia.

---

# Una vez en GCS, ahí ya no tenemos problema con 1 GB

Google Cloud Storage permite objetos de hasta **5 TiB**, por lo que 1–2 GB no es una cifra problemática para GCS. [Google Cloud Documentation](https://docs.cloud.google.com/storage/docs/uploads?utm_source=chatgpt.com)

Además Google recomienda cargas reanudables para archivos grandes. [Google Cloud Documentation](https://docs.cloud.google.com/storage/docs/access-control/signed-urls?hl=es-419\&utm_source=chatgpt.com)

Así que cambiaría la filosofía actual de:

```text
Signed PUT de un solo request
```

hacia:

```text
resumable upload
```

si el backend va a transferir archivos de ese tamaño.

---

# Segundo cambio: no descargar 1 GB a `bytes`

En el backend actual tenemos que retirar esto:

```python
blob.download_as_bytes()
```

para la ruta grande.

No debemos hacer:

```text
GCS
 ↓
1.2 GB en bytes Python
 ↓
BytesIO
 ↓
zipfile
```

Para ese tamaño lo correcto sería que el procesador tenga acceso al objeto de GCS como archivo y lea las entradas del ZIP según las necesite.

Una posibilidad especialmente compatible con Cloud Run es montar el bucket como volumen Cloud Storage y trabajar sobre:

```text
/mnt/tasaciones/ingresos/job123/lote.zip
```

en lugar de convertir el objeto entero en bytes.

Entonces:

```python
with zipfile.ZipFile("/mnt/tasaciones/.../lote.zip") as archive:
    for entry in archive.infolist():
        with archive.open(entry) as pdf:
            pdf_bytes = pdf.read()
            procesar_pdf(pdf_bytes)
```

Así mantienes aproximadamente:

```text
ZIP grande → GCS

RAM:
PDF actual
+ PyMuPDF
+ OCR actual
+ resultados
```

en vez de:

```text
ZIP completo
+ PDF
+ OCR
+ resultados
```

---

# Tercer cambio: no mantener Power Automate esperando

Aquí también cambiaría algo importante.

Actualmente:

```text
procesar_carga
     ↓
Cloud Run procesa todo
     ↓
HTTP espera
     ↓
devuelve XLSX
```

Para 150 PDFs puede funcionar algunas veces, pero deja de ser robusto con 1 GB.

Cloud Run Service puede tener requests de hasta 60 minutos, pero el cliente puede tener límites inferiores y Google advierte del riesgo de conexiones largas. [Google Cloud Documentation](https://docs.cloud.google.com/run/docs/configuring/request-timeout?utm_source=chatgpt.com)

Por eso usaría:

```text
POST /jobs
```

y devolvería inmediatamente:

```json
{
  "job_id": "TAS-20261007-000123",
  "estado": "PROCESANDO"
}
```

El procesamiento pesado pasa a **Cloud Run Job**.

Cloud Run Jobs permite que cada tarea tenga un timeout configurable hasta **168 horas**, mucho más apropiado para procesamiento batch. [Google Cloud Documentation](https://docs.cloud.google.com/run/docs/configuring/task-timeout?utm_source=chatgpt.com)

---

# Y Power Automate solo esperaría el estado

Por ejemplo:

```text
Power Apps
    ↓
Ejecutar tasaciones
    ↓
Power Automate
    ↓
POST /jobs
    ↓
jobId
```

Luego:

```text
Do until:

GET /jobs/{jobId}

estado:
PROCESANDO
PROCESANDO
PROCESANDO
COMPLETADO
```

Cuando esté:

```json
{
  "estado": "COMPLETADO",
  "resultado": "resultados/TAS-.../Resultado_Final.xlsx"
}
```

Power Automate descarga **solo el Excel**, que va a ser muchísimo menor que el ZIP, y lo deja donde corresponde en OneDrive.

---

# Y ahí empieza la segunda mitad de tu automatización

Ese Excel es el contrato que ya tienes bien definido:

```text
Resultado_Final.xlsx
│
├── PARA_PROCESAR
├── REVISION_IA
└── CONTROL
```

La PC que tiene:

```text
OneDrive sincronizado
+
Power Automate Desktop
+
cliente IBM 3270
```

recibe automáticamente el archivo.

Después tienes dos formas de disparar PAD:

```text
Power Automate Cloud
   ↓
Run desktop flow
   ↓
máquina registrada

```

o un mecanismo local que detecte que apareció el Excel.

Yo preferiría que el propio flujo Cloud:

```text
guarda Resultado_Final.xlsx
        ↓
confirma que está listo
        ↓
ejecuta Desktop Flow
```

Así no dependes de un watcher improvisado.

El Desktop Flow recibe como parámetro:

```text
ruta Excel
ID del lote
```

y opera únicamente:

```text
tblParaProcesar
```

como ya establece tu contrato actual.

---

# Algo importante de tu repo actual

Hay una pequeña inconsistencia documental que arreglaría.

El `README.md` principal todavía describe:

```text
Power Automate
→ obtiene contenido ZIP
→ POST application/zip Cloud Run
```

como flujo vigente.

Mientras que:

```text
power-platform/README.md
docs/architecture/flujo-vigente.md
```

ya documentan el camino de GCS para archivos grandes.

Con el requisito definitivo de **>1 GB**, yo eliminaría conceptualmente las dos arquitecturas como alternativas de producción.

No haría:

```text
< 30MB → directa
> 30MB → GCS
```

Para tasaciones dejaría **una sola ruta productiva**:

```text
CUALQUIER ZIP
      ↓
OneDrive
      ↓
referencia
      ↓
GCS
      ↓
Job
```

Aunque pese 10 MB.

Eso simplifica muchísimo pruebas, soporte y observabilidad.

---

# Mi propuesta final para `auto-tasacion`

El objetivo del proyecto quedaría formalmente así:

```text
1. INGESTA
   Usuario deposita ZIP en OneDrive

2. ORQUESTACIÓN
   Power Apps selecciona el ZIP
   Power Apps envía únicamente la referencia
   Power Automate crea JOB

3. TRANSFERENCIA
   Backend lee OneDrive directamente
   Backend copia ZIP → GCS
   Soporte >1 GB

4. PROCESAMIENTO
   Cloud Run Job
   ZIP permanece en GCS
   PDF por PDF
   perfiles
   OCR
   reglas
   IA excepcional

5. RESULTADO
   Resultado_Final.xlsx → GCS
   estado JOB = COMPLETADO

6. ENTREGA
   Power Automate obtiene XLSX
   lo guarda en la carpeta OneDrive elegida

7. RPA
   PC sincroniza OneDrive
   Power Automate Cloud dispara PAD
   PAD procesa tblParaProcesar
   IBM Mainframe 3270

8. TRAZABILIDAD
   ID_CASO
   CONTROL
   resultados IBM
```

Para mí esta debería ser ya la **arquitectura objetivo oficial del repo**.

Y lo bueno es que aproximadamente **80–90 % de tu lógica actual de extracción no cambia**. Los cambios fuertes están concentrados en ingesta/orquestación: retirar el límite de 90 MB, no transportar el ZIP a través de Power Automate, sustituir `download_as_bytes()`, introducir el concepto de `JOB`, y desacoplar generación/entrega del Excel.

Con eso ya no diseñamos para “que funcione con 84.9 MB” o “que aguante 700 MB”; diseñamos el sistema directamente para **1 GB+**, que es tu requisito real.
---

## Verificacion tecnica del enfoque

**Conclusion: aprobado como arquitectura objetivo, con ajustes obligatorios antes de implementarla.**

| Tema | Veredicto | Ajuste necesario |
| --- | --- | --- |
| Power Apps y Power Automate como orquestadores | Correcto | Deben enviar solo metadatos, nunca el contenido del ZIP. |
| OneDrive a GCS mediante backend | Correcto y preferido | El Job debe usar Microsoft Graph con acceso de lectura limitado a la carpeta operativa. |
| URL temporal de OneDrive | Solo alternativa transitoria | Es un bearer token: no se registra, no se persiste y la API debe validar el host para evitar SSRF. Graph es mas robusto. |
| Cloud Run Job asincrono | Correcto | La API devuelve ID_LOTE de inmediato; Power Automate no espera el procesamiento. |
| ZIP desde GCS por entradas | Correcto, sujeto a prueba de carga | No usar `download_as_bytes()`. Abrir el ZIP mediante GCS FUSE y cargar un PDF por vez. |
| Una sola ruta productiva | Correcto como destino | Mantener temporalmente la ruta actual de hasta 90 MB y retirarla solo luego de una prueba E2E masiva aprobada. |

El inicio no debe conservar solo `RutaZip`. Power Automate debe resolver la
ruta en OneDrive y enviar `driveId`, `itemId`, `eTag`, nombre, tamano y carpeta
destino. El Job valida el `eTag` antes y despues de copiar. Si el ZIP cambia,
termina como `FALLIDO_ORIGEN_CAMBIO`; nunca procesa un archivo mezclado.

La llave de idempotencia es `driveId:itemId:eTag`, evitando dos Jobs para el
mismo contenido. El resultado se llama `Resultado_Final_<ID_LOTE>.xlsx` en la
misma carpeta de OneDrive; asi no sobrescribe otro lote concurrente.

La capacidad objetivo queda en 300 PDFs, ZIP de hasta 2 GB, contenido
 descomprimido de hasta 6 GiB y limite individual de PDF. El Job inicia con 4
GiB, 2 vCPU y 60 minutos, valores sujetos a la prueba sintetica de 1.4 GB.

La integracion necesita dos identidades separadas: una API de control que
puede ejecutar Jobs y otra para el Job, que lee y escribe en GCS y lee la
carpeta autorizada de OneDrive. La aplicacion Entra debe usar permisos
Selected sobre esa carpeta o biblioteca, nunca acceso global al tenant.