# Prueba E2E: lotes masivos de tasaciones

## Propósito

Validar la ruta operativa de PDFs individuales desde OneDrive hasta el Excel
que consume PAD y, después, el seguimiento automático visible en Power Apps.
La prueba no usa la ruta ZIP heredada.

## Estado de la ruta de procesamiento

La ejecución de referencia con un PDF completó esta secuencia:

```text
Power Apps -> iniciar lote -> control de OneDrive -> cargar lotes
-> Cloud Run Job -> entregar lote -> Resultado_Final_<ID_LOTE>.xlsx
```

El Excel se creó en `/auto-tasaciones` y el control
`_autotasacion_lote_<ID_LOTE>.json` se eliminó tras confirmar la entrega. Esto
valida la ruta de procesamiento. La validación pendiente es exclusivamente la
actualización automática que muestra la Canvas App durante ese proceso.

## Precondiciones para la prueba de interfaz

1. Aplicar y publicar las instrucciones de
   [`POLLING.md`](../../power-platform/canvas/autoTasacionJG/POLLING.md) en
   `autoTasacionJG`.
2. Ejecutar `deploy-mass-flows.ps1 -Activate`, que publica
   `auto-tasacion-consultar-lote` con su contrato tipado.
3. Confirmar que el origen de datos de la app contiene
   `auto-tasacion-listar-pdfs`, `auto-tasacion-iniciar-lote` y
   `auto-tasacion-consultar-lote`.

La Canvas App envía solamente el manifiesto (`item_id`, nombre, tamaño y eTag);
ningún PDF se transmite por la aplicación.

## Caso de prueba: `D01.pdf`

1. Abrir `autoTasacionJG` y pulsar **Actualizar**.
2. Verificar que aparece `D01.pdf` y seleccionar solamente ese archivo.
3. Pulsar **Ejecutar**.
4. Confirmar que la app muestra un `ID_LOTE` y el estado inicial `RECIBIDO`.
5. Sin pulsar otros botones ni ejecutar flujos manualmente, esperar las
   consultas automáticas de 10 segundos.
6. Verificar que la interfaz actualiza el estado y los conteos a medida que el
   backend avanza: `CARGANDO_PDFS`, `LISTO_PARA_PROCESAR`, `EN_PROCESO` y,
   transitoriamente, `COMPLETADO`.
7. Esperar la siguiente recurrencia de entrega y confirmar que la app pasa a
   `ENTREGADO`.
8. Verificar `/auto-tasaciones/Resultado_Final_<ID_LOTE>.xlsx` y comprobar sus
   hojas `PARA_PROCESAR`, `REVISION_IA` y `CONTROL`.
9. Confirmar que el Timer deja de consultar después de `ENTREGADO`.

El mismo caso debe conservar el último estado e ID conocido si una consulta
puntual falla. Una advertencia de conectividad no equivale a un estado real
`FALLIDO`.

## Criterios de aceptación

- `auto-tasacion-consultar-lote` llama a `GET /v1/lotes/{id_lote}` y responde
  a la app los campos tipados `id_lote`, `estado`, `mensaje`, `total_pdfs`,
  `pdfs_cargados`, `pdfs_procesados`, `pdfs_fallidos` y
  `resultado_disponible`.
- La app conserva el ID del lote, actualiza la etiqueta sin intervención del
  operador y muestra progreso real cuando el API lo informa.
- `COMPLETADO` no detiene el seguimiento; este se detiene solo en `ENTREGADO`,
  `FALLIDO` o `FALLIDO_ORIGEN_CAMBIO`.
- El Excel final se crea una sola vez y el control se elimina solo después de
  la entrega confirmada.
- Power Apps no recibe `archivos`, contenido de PDF, rutas GCS ni URLs firmadas.

## Regresiones ya corregidas

`GetFileContentByPath` entrega el control JSON de OneDrive como contenido
binario. Los flujos de carga y entrega convierten `body.$content` desde Base64
a JSON antes de `ParseJson`:

```text
@json(base64ToString(outputs('Obtener_control_lote')?['body']?['$content']))
```

La siguiente regresión hacía que `Filtrar_archivos_pendientes` recibiera `null`.
Se corrigió el resumen de `GET /v1/lotes/{id_lote}` para incluir el arreglo
operativo `archivos` al cargador. Ese arreglo se mantiene interno y no forma
parte del contrato de consulta de Power Apps.

## Prueba de capacidad

Tras aprobar el seguimiento de un PDF, repetir con 10, 150 y hasta 300 PDFs.
Cada iteración debe comprobar que Power Apps y HTTP no transportan ZIPs ni el
lote completo en contenido binario.
