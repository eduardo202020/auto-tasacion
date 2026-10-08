# Prueba E2E: lotes masivos de tasaciones

## Propósito

Validar la ruta operativa de PDFs individuales desde OneDrive hasta el Excel
que consume PAD. Esta prueba no usa la ruta ZIP heredada.

## Estado previo

- La app `autoTasacionJG` ya lista los PDFs de `/auto-tasaciones/PDFs`.
- Los flujos `auto-tasacion-iniciar-lote`, `auto-tasacion-cargar-lotes` y
  `auto-tasacion-entregar-lote` están publicados.
- El servicio y el Job de Cloud Run superaron las pruebas automatizadas locales.
- Pendiente: asociar `auto-tasacion-iniciar-lote` al `OnSelect` del botón
  **Ejecutar** de la app y publicar esa versión.

## Infraestructura verificada

Verificación realizada el 7 de octubre de 2026 en Google Cloud:

- Cloud Run `demo-tasaciones-ia`: revisión `demo-tasaciones-ia-00077-c2j` en
  estado `Ready`.
- API configurada para la carpeta `/auto-tasaciones/PDFs`, hasta 300 PDFs, 2
  GiB por lote y 90 000 000 bytes por PDF.
- Cloud Run Job `tasaciones-batch`: estado `Ready`, tiempo máximo de una hora
  y última ejecución finalizada correctamente.

## Fórmula requerida en `OnSelect`

Antes de pegarla, agrega el flujo `auto-tasacion-iniciar-lote` como origen de
datos de la aplicación. Luego usa esta fórmula en el botón **Ejecutar**:

```powerfx
With(
    {
        seleccion: ForAll(
            Filter(colPdfs, Seleccionado),
            {
                item_id: ItemId,
                nombre: Nombre,
                tamano_bytes: Tamano,
                etag: ETag
            }
        )
    },
    If(
        CountRows(seleccion) = 0,
        Notify("Seleccione al menos un PDF."; NotificationType.Warning),
        Set(
            varLote,
            'auto-tasacion-iniciar-lote'.Run(
                JSON(seleccion, JSONFormat.Compact)
            )
        );
        Notify(
            "Lote " & varLote.id_lote & " registrado. La carga se realizará en segundo plano.";
            NotificationType.Success
        )
    )
)
```

La fórmula envía solo el manifiesto de la selección; no transmite el contenido
de ningún PDF.

## Caso inicial

Usa un PDF ya visible en la carpeta, por ejemplo `D01.pdf`. El primer caso debe
tener un solo archivo para aislar fallas de integración antes de probar el lote
completo.

## Pasos

1. En `autoTasacionJG`, pulsa **Actualizar** y verifica que `D01.pdf` aparece
   con su tamaño.
2. Marca solamente ese PDF y comprueba que el contador muestra `1`.
3. Pulsa **Ejecutar**.
4. La app debe informar el identificador de lote recibido. En OneDrive aparece
   `_autotasacion_lote_<ID_LOTE>.json`.
5. Espera la siguiente ejecución de `auto-tasacion-cargar-lotes` (hasta cinco
   minutos). El flujo debe convertir el contenido binario del archivo de
   control a JSON, consultar el lote, cargar un PDF individual a GCS e iniciar
   el Job.
6. Cuando el Job termine, espera la siguiente ejecución de
   `auto-tasacion-entregar-lote` (hasta cinco minutos). Debe aparecer
   `/auto-tasaciones/Resultado_Final_<ID_LOTE>.xlsx`.
7. Abre el archivo y verifica las hojas `PARA_PROCESAR`, `REVISION_IA` y
   `CONTROL`, incluidas las tablas `tblParaProcesar`, `tblRevisionIa` y
   `tblControl`.

## Criterios de aceptación

- La app envía `item_id`, nombre, tamaño y eTag; no envía el PDF.
- `Leer control lote` termina correctamente y obtiene `id_lote` desde el JSON
  de control.
- El lote pasa por `RECIBIDO`, `CARGANDO_PDFS`, `EN_PROCESO` y `COMPLETADO`.
- Se crea un único Excel con el identificador del lote en OneDrive.
- El Excel conserva sus tres hojas y el contrato de `tblParaProcesar`.
- El archivo de control se elimina solo después de crear y confirmar el Excel.

## Ejecución de regresión: lectura del control

El 7 de octubre de 2026 se observó que `Leer control lote` recibía
`application/octet-stream` desde `GetFileContentByPath`. La definición de ambos
flujos fue corregida y publicada para convertir `body.$content` de Base64 a
JSON antes de `ParseJson`.

La verificación de la definición publicada confirmó la nueva expresión en
`auto-tasacion-cargar-lotes` y `auto-tasacion-entregar-lote`. El lote de un PDF
usado para la prueba se mantuvo en `RECIBIDO` con el archivo `PENDIENTE`, sin
iniciar el Job durante la ventana observada de recurrencia. Por ello esta prueba
no aprueba todavía la ruta E2E y no se solicitó la entrega del XLSX.

## Prueba de capacidad

Una vez aprobado el caso de un PDF, repetir con 10, 150 y hasta 300 PDFs. El
límite del manifiesto es 300 archivos, 2 GiB totales y 90 000 000 bytes por PDF.
Cada iteración debe confirmar que Power Apps y HTTP no transportan ZIPs ni el
lote completo.
