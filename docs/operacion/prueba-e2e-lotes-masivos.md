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
valida la ruta de procesamiento. También se observó manualmente que la
Canvas App llega a `ENTREGADO` y deja `varMonitorearLote` en `false`. El
stepper y el contador de esta versión requieren desplegar el contrato ampliado
y aplicar la guía de Studio antes de validarlos en el entorno.

## Precondiciones para la prueba de interfaz

1. Aplicar y publicar las instrucciones de
   [`POLLING.md`](../../power-platform/canvas/autoTasacionJG/POLLING.md) en
   `autoTasacionJG`.
2. Ejecutar `deploy-mass-flows.ps1 -Activate`, que publica
   `auto-tasacion-consultar-lote` con su contrato tipado, incluidos
   `fecha_inicio`, `fecha_fin` y `duracion_segundos`.
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
9. Confirmar que el Timer deja de consultar después de `ENTREGADO`, todos los
   pasos quedan verdes y `lblTiempoLote` queda fijo.

El mismo caso debe conservar el último estado e ID conocido si una consulta
puntual falla. Una advertencia de conectividad no equivale a un estado real
`FALLIDO`.

## Verificación de entrega

Durante `COMPLETADO`, confirmar que `resultado_disponible` es `true` y que el
Timer sigue consultando. En el historial de `auto-tasacion-entregar-lote`, el
orden obligatorio es `Solicitar_ticket_resultado` -> `Descargar_resultado` ->
`Crear_excel_final` -> `Confirmar_entrega`. La interfaz solo puede mostrar
`ENTREGADO` después de que exista `Resultado_Final_<ID_LOTE>.xlsx` y la llamada
de confirmación haya sido exitosa.

## Casos adicionales de interfaz

### Dos PDFs

1. Seleccionar dos PDFs distintos y ejecutar un lote.
2. Verificar que `CARGANDO_PDFS` muestra `pdfs_cargados / total_pdfs` y que
   `EN_PROCESO` muestra `pdfs_procesados / total_pdfs`.
3. Confirmar que el paso activo pulsa, los anteriores son verdes y los futuros
   grises hasta la entrega.

### Fallo terminal simulado

Con un manifiesto sintético o un entorno de prueba, forzar `FALLIDO` y luego
`FALLIDO_ORIGEN_CAMBIO`. Confirmar que el paso 3 o 2 respectivamente se muestra
rojo, aparece el mensaje seguro del lote, el tiempo queda congelado y
`varMonitorearLote` queda en `false`.

### Reapertura

Conservar un `id_lote` conocido, volver a abrir la app e ingresarlo en
`txtIdLote`; pulsar `btnReanudarLote`. Confirmar que `fecha_inicio` y
`fecha_fin` reconstruyen el tiempo total sin usar datos de la sesión anterior.
No se crea un flujo de historial: el ID proviene del mensaje de registro o del
nombre del Excel entregado.

## Criterios de aceptación

- `auto-tasacion-consultar-lote` llama a `GET /v1/lotes/{id_lote}` y responde
  a la app los campos tipados `id_lote`, `estado`, `mensaje`, `total_pdfs`,
  `pdfs_cargados`, `pdfs_procesados`, `pdfs_fallidos`,
  `resultado_disponible`, `fecha_inicio`, `fecha_fin` y
  `duracion_segundos`.
- La app conserva el ID del lote, actualiza la etiqueta sin intervención del
  operador y muestra progreso real cuando el API lo informa. El stepper
  muestra los pasos terminados en verde, el activo pulsando en verde, los
  pendientes en gris y el fallo en rojo.
- El contador usa `fecha_inicio` y `fecha_fin`; avanza mientras no hay fecha de
  fin y queda congelado al terminar.
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
