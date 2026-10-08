# Diseño: lotes masivos de tasaciones

## Objetivo

Procesar hasta 300 PDFs individuales, con un tamaño total aproximado de 2 GiB,
sin transportar el lote entero mediante Power Apps, Power Automate o un único
request HTTP.

## Arquitectura objetivo

```text
OneDrive /auto-tasaciones/PDFs (PDFs individuales)
  -> Power Apps (metadatos y selección)
  -> Power Automate (un PDF por iteración)
  -> Cloud Storage privado
  -> Cloud Run Job (un PDF por iteración)
  -> Resultado_Final_<ID_LOTE>.xlsx
  -> OneDrive -> PAD/IBM 3270
```

Power Automate obtiene el contenido de cada PDF desde OneDrive, solicita una
URL firmada restringida al objeto esperado y carga ese PDF a GCS. Cloud Run no
lee OneDrive y no usa Microsoft Graph.

## Manifiesto, integridad e idempotencia

El manifiesto conserva `item_id`, nombre, eTag, tamaño, estado y objeto GCS por
PDF. No contiene el PDF, credenciales ni URLs firmadas.

La clave de idempotencia del lote se deriva de la carpeta autorizada y de la
lista ordenada `itemId:eTag`. Cada archivo también conserva su propia identidad
`itemId:eTag`.

Power Automate compara los metadatos antes y después de la carga. La API vuelve
a comprobar que el objeto GCS exista, sea PDF y tenga el tamaño declarado. Un
eTag cambiado marca el archivo y el lote como `FALLIDO_ORIGEN_CAMBIO`; el Job
no puede iniciarse.

## Persistencia y ejecución

Los manifiestos se guardan como JSON bajo `estado/lotes/<ID_LOTE>.json`, usando
precondiciones de generación de GCS para evitar que cargas concurrentes pierdan
actualizaciones. Los resultados usan
`resultados/<ID_LOTE>/Resultado_Final_<ID_LOTE>.xlsx`.

Cada manifiesto registra `fecha_inicio` al crearse. Cuando alcanza
`ENTREGADO`, `FALLIDO` o `FALLIDO_ORIGEN_CAMBIO`, registra `fecha_fin` una sola
vez. `GET /v1/lotes/{id_lote}` expone ambas marcas y `duracion_segundos`, sin
exponer contenido documental; los lotes antiguos sin estas propiedades usan
`creado_en` y `actualizado_en` como respaldo de lectura.

El Job recibe `BATCH_ID`, `BATCH_INPUT_PREFIX` y `BATCH_OUTPUT_XLSX`. Lee solo
los objetos declarados como `CARGADO`, descarga un PDF a memoria, lo procesa y
lo libera antes de continuar. Al finalizar conserva el contrato XLSX actual y
marca el lote `COMPLETADO`.

## Seguridad y retención

La API de control y el Job deben usar identidades de Google Cloud con privilegios
mínimos. La URL firmada permite escribir solo un objeto PDF de un manifiesto y
vence en 15 minutos. No se escriben URLs completas, contenidos documentales ni
credenciales en logs.

La política de ciclo de vida debe eliminar ingresos y estados temporales después
de la entrega confirmada, según la retención corporativa aprobada.

## Implementación y pendientes de infraestructura

El código local incluye el manifiesto, las APIs de control y el worker. Falta:

1. crear el bucket/roles y configurar `BATCH_STATE_BUCKET`,
   `BATCH_STORAGE_BUCKET`, `BATCH_SIGNING_SERVICE_ACCOUNT`, `BATCH_JOB_NAME`,
   `BATCH_JOB_REGION` y `GOOGLE_CLOUD_PROJECT`;
2. crear el Cloud Run Job con el mismo contenedor y permisos para leer/escribir
   el bucket;
3. proteger la API de control según el mecanismo corporativo aprobado;
4. construir y publicar los cinco flujos de Power Automate y la pantalla de
   Power Apps;
5. ejecutar y aprobar la prueba E2E sintética masiva.

No hay despliegue incluido en este cambio.

## Histórico descartado

La alternativa de un ZIP de 2 GiB descargado desde OneDrive mediante Microsoft
Graph y abierto con GCS FUSE fue descartada. La ruta ZIP de hasta 90 MB sigue
solo como transición heredada.
