# Flujo Power Platform para lotes masivos de PDFs

> **Estado al 8 de octubre de 2026:** la ruta OneDrive → Cloud Run Job → Excel
> ya completó una prueba E2E y la Canvas App consulta el estado hasta
> `ENTREGADO`. La extensión de seguimiento visual y tiempo está versionada en
> [`POLLING.md`](../../power-platform/canvas/autoTasacionJG/POLLING.md) y debe
> aplicarse y publicarse desde Power Apps Studio junto con el nuevo contrato.

## Decisión

La ruta masiva no usa ZIP ni Microsoft Graph. El lote es un manifiesto de PDFs
existentes en `/auto-tasaciones/PDFs`. Power Automate es el único componente que lee
cada PDF desde OneDrive y lo carga individualmente a Cloud Storage.

```text
Operador carga PDFs individuales en OneDrive
  -> Power Apps lista y selecciona metadatos
  -> Power Automate registra el manifiesto
  -> API de control crea ID_LOTE
  -> Power Automate carga un PDF por vez a GCS
  -> API confirma cada PDF y arranca Cloud Run Job
  -> Job procesa PDFs individuales y genera XLSX
  -> Power Automate entrega Resultado_Final_<ID_LOTE>.xlsx a OneDrive
  -> PC sincronizada -> PAD -> IBM 3270
```

Power Apps nunca recibe contenido de PDF. Power Automate no agrupa, concatena,
convierte a Base64 ni mantiene en memoria el lote completo.

## Carpetas y resultado

- Origen operativo: `/auto-tasaciones/PDFs`.
- Objetos de ingreso: `ingresos/<ID_LOTE>/pdfs/<ID_ARCHIVO>_<nombre>.pdf`.
- Resultado: `resultados/<ID_LOTE>/Resultado_Final_<ID_LOTE>.xlsx`.
- Entrega final: `/auto-tasaciones/Resultado_Final_<ID_LOTE>.xlsx`.

La aplicación lista solamente archivos `.pdf`. Los Excel ya entregados no son
seleccionables. El operador debe archivar lotes terminados para mantener la
carpeta de trabajo manejable.

## Flujos de Power Automate

### 1. `auto-tasacion-listar-pdfs`

Lista los `.pdf` de la carpeta autorizada y devuelve a Power Apps solamente:
`ItemId`, nombre, tamaño y fecha. Si el conector expone eTag, se devuelve; de
lo contrario se obtiene de metadatos antes de registrar el manifiesto.

### 2. `auto-tasacion-iniciar-lote`

Recibe la selección de la app, vuelve a consultar metadatos y envía a
`POST /v1/lotes` un JSON pequeño:

```json
{
  "carpeta_origen": "/auto-tasaciones/PDFs",
  "archivos": [
    {
      "item_id": "<id de OneDrive>",
      "nombre": "tasacion001.pdf",
      "etag": "<versión>",
      "tamano_bytes": 5242880
    }
  ]
}
```

Responde de inmediato con `id_lote`, estado y `fecha_inicio`. No obtiene
contenido de ningún PDF y no espera la transferencia ni el procesamiento.
`fecha_inicio` queda persistida en el manifiesto y no cambia con las consultas.

### 3. `auto-tasacion-cargar-lotes`

Se ejecuta de forma separada o recurrente. Para cada archivo pendiente:

1. obtiene metadatos y conserva el eTag inicial;
2. solicita `POST /v1/lotes/{id}/archivos/{archivo}/upload-ticket`;
3. obtiene el contenido binario de **un solo PDF** desde OneDrive;
4. hace `PUT` binario a la URL firmada con `Content-Type: application/pdf`;
5. consulta otra vez los metadatos de OneDrive;
6. compara el eTag inicial y final;
7. llama a `POST /confirmar` con el eTag final.

La concurrencia inicial debe configurarse entre 1 y 3 archivos. Si el eTag
cambia, se detiene el lote con `FALLIDO_ORIGEN_CAMBIO`. Cuando todos están
confirmados, el flujo invoca `POST /v1/lotes/{id}/iniciar`.

### 4. `auto-tasacion-consultar-lote`

Consulta `GET /v1/lotes/{id_lote}`. El backend incluye el arreglo `archivos`
para que `auto-tasacion-cargar-lotes` pueda localizar registros `PENDIENTE`,
pero la respuesta del flujo hacia Power Apps se limita a campos tipados y
seguros: `id_lote`, `estado`, `mensaje`, `total_pdfs`, `pdfs_cargados`,
`pdfs_procesados`, `pdfs_fallidos`, `resultado_disponible`, `fecha_inicio`,
`fecha_fin` y `duracion_segundos`. No devuelve contenido de PDF, rutas GCS,
URLs firmadas ni metadatos por archivo a la aplicación.

`fecha_fin` se persiste una sola vez en los estados terminales `ENTREGADO`,
`FALLIDO` y `FALLIDO_ORIGEN_CAMBIO`. La duración se deriva de las dos fechas,
por lo que puede reconstruirse al volver a consultar el ID del lote.

Power Apps lo llama mediante un temporizador cada 10 segundos mientras el lote
está activo; no mantiene una solicitud abierta durante el Job. El temporizador
sigue activo en `COMPLETADO`, porque la entrega del XLSX aún debe cambiar el
lote a `ENTREGADO`, y se detiene solo en `ENTREGADO`, `FALLIDO` o
`FALLIDO_ORIGEN_CAMBIO`.

### 5. `auto-tasacion-entregar-lote`

Cuando el estado es `COMPLETADO`, descarga únicamente el XLSX final, lo crea en
la carpeta operativa de OneDrive y confirma `POST /entrega`. Solo después de
`ENTREGADO` se entrega la ruta a PAD, que procesa exclusivamente
`tblParaProcesar`.

## Power Apps

La pantalla nueva contiene:

| Control | Responsabilidad |
| --- | --- |
| `galPdfs` | Galería de PDFs existentes con nombre, tamaño, modificación y selección múltiple. |
| `btnActualizar` | Vuelve a listar los PDFs. |
| `btnSeleccionarTodos` | Selecciona o limpia los PDFs de la galería. |
| `Button5` (**Ejecutar**) | Registra el manifiesto seleccionado y comienza el seguimiento. |
| `tmrEstadoLote` | Consulta el lote cada 10 segundos mientras está activo. |
| `galPasosLote` | Muestra los cinco pasos, su avance y el paso con error. |
| `tmrVistaLote` | Alterna el pulso del paso activo y actualiza el contador local, sin llamar flujos. |
| `Label3`, `lblProgresoLote`, `lblTiempoLote` | Muestran estado amigable, conteos y tiempo transcurrido o total. |

La fuente descargada de `autoTasacionJG` no se puede actualizar ni publicar con
la CLI disponible y la exportación de la solución corporativa está bloqueada por
un flujo heredado de otro propietario. Por ello, las fórmulas versionadas en
[`POLLING.md`](../../power-platform/canvas/autoTasacionJG/POLLING.md) se deben
aplicar en Studio y publicar allí. La ruta ZIP actual permanece en un flujo de
transición separado para lotes de hasta 90 MB.

## API de control

| Operación | Responsabilidad |
| --- | --- |
| `POST /v1/lotes` | Registra o reutiliza un manifiesto de hasta 300 PDFs y 2 GiB totales. |
| `GET /v1/lotes/{id_lote}` | Devuelve estado y progreso sin contenido documental. |
| `POST /v1/lotes/{id}/archivos/{archivo}/upload-ticket` | Emite una URL firmada para un único objeto PDF del manifiesto. |
| `POST /v1/lotes/{id}/archivos/{archivo}/confirmar` | Comprueba eTag y tamaño del objeto GCS. |
| `POST /v1/lotes/{id}/iniciar` | Inicia el Job únicamente si todos los PDFs están confirmados. |
| `POST /v1/lotes/{id}/entrega` | Registra que el XLSX fue creado en OneDrive. |

La clave de idempotencia es `SHA256(carpeta + lista ordenada itemId:eTag)`. Un
eTag distinto representa una versión nueva. La API no utiliza `driveId` ni
intenta leer OneDrive.

## Estados

Lote: `RECIBIDO`, `CARGANDO_PDFS`, `LISTO_PARA_PROCESAR`, `EN_PROCESO`,
`COMPLETADO`, `ENTREGADO`, `FALLIDO`, `FALLIDO_ORIGEN_CAMBIO`.

Archivo: `PENDIENTE`, `SUBIENDO`, `CARGADO`, `FALLIDO`,
`FALLIDO_ORIGEN_CAMBIO`.

La Canvas App los traduce a: **Lote recibido**, **Cargando documentos**,
**Procesando tasaciones**, **Resultado generado** y **Entregado**. Los pasos
terminados son verdes, el activo pulsa en verde, los pendientes son grises y
el paso asociado a un estado terminal de error es rojo.

## Límites

- 300 PDFs por lote.
- 2 GiB totales por lote.
- 90 000 000 bytes por PDF, configurable mediante `BATCH_MAX_PDF_BYTES`.
- El límite se aplica a cada PDF, no al lote completo en un solo request.

## Ruta ZIP heredada

El endpoint ZIP y la carga temporal firmada de hasta 90 MB son **LEGACY /
TRANSICIÓN**. No se eliminan hasta aprobar una prueba E2E de la nueva ruta. No
se mezclan con los manifiestos de PDFs individuales.
