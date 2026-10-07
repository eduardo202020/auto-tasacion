# Diseño: lotes masivos de tasaciones

## Objetivo

Procesar hasta 300 PDFs por lote. La referencia operativa observada es de 150
PDFs comprimidos en aproximadamente 700 MB; por ello el diseño debe admitir
un ZIP de hasta 2 GB, sin mover ese binario por Power Apps ni Power Automate.

OneDrive conserva dos responsabilidades: recibe el ZIP por el mecanismo que
la operación elija y recibe el Excel final en la misma carpeta. Power Apps
solo inicia y consulta el proceso.

## Motivo del cambio

El transporte actual sirve para lotes pequeños y medianos:

```text
Power Apps -> Power Automate -> OneDrive -> Cloud Storage -> Cloud Run
```

No sirve para el objetivo masivo. Power Apps serializa adjuntos de flujo en
Base64 y Power Automate limita los mensajes a 100 MB. Además, el servicio
actual descarga el ZIP completo a memoria y responde de manera síncrona, lo
que no es adecuado para una ejecución de cientos de PDFs.

Habilitar la fragmentación genérica de la acción HTTP tampoco resuelve este
caso: usa el protocolo `x-ms-transfer-mode` de Logic Apps, que el endpoint de
carga de Cloud Storage no implementa.

## Arquitectura objetivo

```text
Operador
  -> OneDrive: carga el ZIP en la carpeta operativa
  -> Power Apps: envía RutaZip o ID del archivo, sin enviar el ZIP
  -> Power Automate: solicita el inicio del lote
  -> API de control Cloud Run: crea ID_LOTE y agenda el Job
  -> Cloud Run Job: descarga por rangos desde OneDrive con Microsoft Graph
  -> Cloud Storage privado: conserva el ZIP temporal, estado y resultado
  -> Cloud Storage: estado y Resultado_Final.xlsx
  -> Power Automate: consulta el estado y guarda el XLSX en la carpeta origen
  -> tblParaProcesar -> PAD / IBM 3270
```

El Job descarga el archivo de OneDrive por rangos de 8 MiB y escribe el mismo
objeto de forma reanudable en Cloud Storage. Si una descarga se corta, valida
la posición confirmada y continúa desde esa parte; no vuelve a transferir el
lote completo.

Power Automate solo intercambia metadatos pequeños (`id_lote`, estado y URL
temporal del resultado). El XLSX de 300 filas se mantiene muy por debajo de su
límite de mensaje.

## Componentes

| Componente | Responsabilidad | Límite objetivo |
| --- | --- | --- |
| API de control Cloud Run | Valida autorización, registra el lote y agenda el Job. | JSON pequeño; nunca recibe el ZIP. |
| Microsoft Graph | Autoriza el acceso de solo lectura a la carpeta operativa de OneDrive y permite descargar el archivo por rangos. | ZIP comprimido hasta 2 GB. |
| Bucket privado | Conserva `ingresos/<id>/`, `estado/<id>.json` y `resultados/<id>/`. | Acceso uniforme y prevención de acceso público. |
| Cloud Run Job | Lee el ZIP desde Cloud Storage, procesa un PDF por vez y escribe el XLSX. | 300 PDFs, 4 GiB RAM, 2 vCPU, 60 min, un lote por tarea. |
| Flujo Power Automate | Inicia, consulta estado y guarda el resultado en la carpeta origen de OneDrive. | No transmite los bytes del ZIP. |

El Job abre el ZIP desde un volumen Cloud Storage FUSE o un lector con rangos,
en vez de `download_as_bytes()`. Cada PDF se mantiene en memoria solo durante
su extracción. El límite de contenido descomprimido se define en 6 GiB y se
mantiene un límite explícito por PDF para evitar ZIP bombs.

## Estados del lote

| Estado | Significado | Acción del operador |
| --- | --- | --- |
| `RECIBIDO` | El flujo registró la ruta o ID de OneDrive. | Esperar la validación inicial. |
| `COPIANDO_A_GCS` | El Job descarga por rangos hacia el bucket privado. | Esperar o reintentar si falla. |
| `CARGADO` | El objeto está completo y validado. | El sistema inicia la extracción. |
| `EN_PROCESO` | Cloud Run Job extrae y valida los PDFs. | Consultar avance. |
| `COMPLETADO` | El XLSX está listo y Power Automate lo guardó en OneDrive. | Continuar con la cola `tblParaProcesar`. |
| `FALLIDO` | Hubo error técnico; se conserva código y mensaje sin datos del PDF. | Reintentar el lote o escalar. |

## Seguridad requerida antes de construir la integración con OneDrive

El servicio actual tiene `invoker-iam-disabled=true`. No se puede exponer una
API pública que acepte rutas o URLs arbitrarias de OneDrive y active Jobs de
2 GB: permitiría que terceros consuman almacenamiento y cómputo del proyecto.

La implementación requiere una aplicación de Microsoft Entra con permiso de
solo lectura limitado a la carpeta operativa. No se debe conceder
`Files.Read.All` para todo el tenant cuando se puede usar un permiso Selected
asignado expresamente a esa carpeta o biblioteca.

También debe protegerse la API de control mediante Microsoft Entra / API
Management, o mediante un secreto de integración custodiado en el mecanismo
corporativo aprobado y asociado a la conexión de Power Automate.

La opción recomendada es Microsoft Entra / API Management, porque identifica
al operador y permite auditar la creación de lotes sin incorporar secretos en
Power Apps.

También se requiere aprobar la retención: los ingresos continúan eliminándose
en un día y los resultados temporales deben eliminarse después de que
Power Automate confirme su copia a OneDrive, con un máximo de tres días.

## Plan de implementación

1. **Seguridad e identidad**: crear la aplicación Entra con acceso Selected,
   proteger la API de control y aprobar la retención de objetos temporales.
2. **API de control**: crear ID de lote, validar ruta/ID de OneDrive, máximo
   de 2 GB y consulta de estado.
3. **Worker asíncrono**: crear Cloud Run Job que copie desde Microsoft Graph
   por rangos a Cloud Storage, abra el ZIP remoto, genere estado transaccional
   y produzca el XLSX.
4. **Power Automate**: sustituir la carga binaria y la espera síncrona por
   inicio, sondeo de estado y creación del resultado en la carpeta origen de
   OneDrive.
5. **Prueba controlada**: ZIP sintético de 1.4 GB con 300 PDFs, interrupción
   y reanudación de la copia desde OneDrive, y validación del XLSX mediante
   `tools/verify_workbook.py`.

No se usan PDFs productivos como datos de prueba ni se registran URLs firmadas,
contenido del ZIP o evidencias documentales en logs.

## Avance de implementación

Se implementó el núcleo del worker en `cloud-run/batch_worker.py`. Este abre
el ZIP desde un path seekable y comparte la lógica de extracción y el contrato
XLSX con el endpoint actual. El ZIP no se descarga con `download_as_bytes()`;
la memoria contiene solo el PDF en procesamiento y el XLSX final.

Todavía no se creó ni desplegó un Cloud Run Job. Tampoco se incorporó la
descarga Microsoft Graph ni la API de control: ambas dependen de la identidad
Entra con permisos Selected, de la protección de la API y de las decisiones de
retención especificadas arriba. La ruta vigente de hasta 90 MB no cambia.

## Flujo de interfaz y orquestación

El detalle de la selección de ZIP desde Power Apps, los parámetros del flujo,
la consulta de estado y la migración desde el flujo binario vigente se define en
[`flujo-power-platform-lotes-masivos.md`](flujo-power-platform-lotes-masivos.md).
