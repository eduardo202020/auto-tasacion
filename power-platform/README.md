# Integración Power Platform

## Ruta masiva objetivo: PDFs individuales

El operador carga PDFs individuales en `/auto-tasaciones/PDFs`. Power Apps lista
metadatos y permite seleccionar uno o varios archivos. No usa adjuntos ni
transmite `contentBytes`.

Power Automate orquesta cinco flujos:

1. `auto-tasacion-listar-pdfs`: lista solo PDFs y devuelve metadatos.
2. `auto-tasacion-iniciar-lote`: valida metadatos, eTag y registra el
   manifiesto mediante `POST /v1/lotes`.
3. `auto-tasacion-cargar-lotes`: por cada PDF, obtiene contenido, solicita un
   ticket de carga, hace `PUT` binario, compara eTag final y confirma.
4. `auto-tasacion-consultar-lote`: consulta estado y progreso.
5. `auto-tasacion-entregar-lote`: solicita un ticket temporal, descarga solo el
   XLSX final, lo guarda en OneDrive y confirma entrega.

El `Apply to each` procesa cada PDF de forma independiente, con concurrencia
inicial de 1 a 3. No se deben guardar PDFs en arrays, variables, JSON o Base64. Los HTTP hacia la
API de control incluyen `X-Batch-Control-Token` desde una variable de entorno o
conexión segura; nunca se escribe su valor en la app. Power Automate es el único componente que lee OneDrive; Cloud Run no usa
Microsoft Graph ni recibe rutas de OneDrive para descargar contenido.

## Despliegue de flujos masivos

El script [`scripts/deploy-mass-flows.ps1`](scripts/deploy-mass-flows.ps1)
crea o actualiza en la solución `autoTasacion` estos flujos:

1. `auto-tasacion-iniciar-lote`;
2. `auto-tasacion-consultar-lote`;
3. `auto-tasacion-cargar-lotes`;
4. `auto-tasacion-entregar-lote`.

El script obtiene el token de control desde Secret Manager durante su ejecución;
no lo guarda en el repositorio. Los dos flujos programados se ejecutan cada cinco
minutos y usan archivos de control `_autotasacion_lote_<ID_LOTE>.json` dentro de
`/auto-tasaciones/PDFs`. La lista de PDFs de Power Apps los excluye por extensión.

`GetFileContentByPath` devuelve el archivo de control como contenido binario.
Antes de `ParseJson`, los flujos `auto-tasacion-cargar-lotes` y
`auto-tasacion-entregar-lote` convierten `body.$content` de Base64 a texto JSON:

```text
@json(base64ToString(outputs('Obtener_control_lote')?['body']?['$content']))
```

No se debe pasar `@body('Obtener_control_lote')` directamente a `ParseJson`.

Ejecutar sin activar los flujos:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\power-platform\scripts\deploy-mass-flows.ps1
```

Para aplicar las definiciones y dejar los cuatro flujos publicados, ejecutar:

```powershell
.\power-platform\scripts\deploy-mass-flows.ps1 -Activate
```

Para recuperar o actualizar solo un flujo, se puede indicar `-FlowName`. Por
ejemplo, para actualizar el cargador sin modificar los otros tres:

```powershell
.\power-platform\scripts\deploy-mass-flows.ps1 -Activate -FlowName auto-tasacion-cargar-lotes
```

`-Activate` conserva las recurrencias y la concurrencia definidas en cada
flujo. Si un flujo publicado tiene un borrador activo sin publicar, el script lo
publica de forma dirigida, lo desactiva brevemente, actualiza la definición y
lo vuelve a publicar. Así evita el error de Dataverse `0x80040203` al
actualizar `clientdata`, sin publicar cambios ajenos del entorno. En particular,
`auto-tasacion-consultar-lote` queda disponible para que Power Apps lo invoque.

### Contrato de consulta para Power Apps

`auto-tasacion-consultar-lote` recibe el `id_lote` como texto y llama a
`GET /v1/lotes/{id_lote}`. Su respuesta hacia Power Apps está tipada y contiene
solamente:

```text
id_lote, estado, mensaje, total_pdfs, pdfs_cargados,
pdfs_procesados, pdfs_fallidos, resultado_disponible, fecha_inicio,
fecha_fin, duracion_segundos
```

El arreglo operativo `archivos`, las URLs firmadas, rutas de GCS y el contenido
documental no se devuelven a la aplicación. `archivos` queda disponible solo
para `auto-tasacion-cargar-lotes`, que lo necesita para localizar PDFs
`PENDIENTE`.

`fecha_inicio` se registra al crear el manifiesto. `fecha_fin` se fija una sola
vez cuando el lote llega a `ENTREGADO`, `FALLIDO` o
`FALLIDO_ORIGEN_CAMBIO`. Ambas fechas son ISO-8601 en UTC.
`duracion_segundos` se calcula a partir de esas marcas; mientras el lote sigue
activo usa el reloj UTC del servicio y, al terminar, queda congelada.

## Power Apps

La aplicación `autoTasacionJG` lista y selecciona PDFs con el flujo
`auto-tasacion-listar-pdfs`. **Actualizar** solamente vuelve a listar la
carpeta. El botón **Ejecutar** envía solo `ItemId`, nombre, tamaño y eTag
disponible hacia `auto-tasacion-iniciar-lote`.

La aplicación debe mantener el `id_lote` devuelto y consultar su estado cada
10 segundos mediante un control Timer. El procedimiento reproducible, con las
propiedades y fórmulas exactas para `Button5`, `tmrEstadoLote` y `Label3`, está
en [`canvas/autoTasacionJG/POLLING.md`](canvas/autoTasacionJG/POLLING.md).
El temporizador continúa durante `COMPLETADO` y se detiene únicamente en
`ENTREGADO`, `FALLIDO` o `FALLIDO_ORIGEN_CAMBIO`.

La misma guía incorpora `galPasosLote`, que traduce los estados técnicos a
cinco pasos para el operador, y `tmrVistaLote`, un temporizador local de 750 ms
para el pulso visual y el contador. Este segundo Timer no invoca flujos ni
modifica el lote.

Eliminar de esta ruta `ControlAdjuntos`, **Cargar Zip**, `contentBytes` y
`varZipSubido`. La consulta de estado debe usar temporizador y el `ID_LOTE`.

## Resultado y PAD

El resultado se llama `Resultado_Final_<ID_LOTE>.xlsx` y se crea en
`/auto-tasaciones`. PAD recibe su ruta y opera exclusivamente
`tblParaProcesar`. `PRESTAMO` y `SEGURO INMUEBLE` se completan después, en el
proceso IBM 3270. `tblRevisionIa` y `tblControl` nunca son colas para el banco.

## Ruta heredada ZIP

El flujo actual `auto-tasacion` conserva el POST ZIP y la carga temporal
firmada hasta 90 MB. Es **LEGACY / TRANSICIÓN** y no se mezcla con los
manifiestos de PDFs. Se retira solo después de aprobar el E2E masivo.
