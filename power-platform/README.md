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

## Power Apps

La pantalla nueva usa `galPdfs`, selección múltiple, **Actualizar**,
**Seleccionar todos**, **Ejecutar** e indicador de lote. El botón **Ejecutar**
envía solo `ItemId`, nombre, tamaño y eTag disponible hacia
`auto-tasacion-iniciar-lote`.

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
