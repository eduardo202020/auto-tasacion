# Integración Power Platform

Los artefactos de Power Apps y Power Automate se administran en el entorno
corporativo Microsoft. Este directorio documenta el contrato que deben usar.

## Power Apps

La aplicación ejecuta el flujo `auto-tasacion`. La carga del ZIP permanece en
la carpeta autorizada de OneDrive; la aplicación no transmite secretos ni
procesa PDFs directamente.

Para ZIP grandes, el operador los carga en OneDrive desde el navegador o el
cliente de sincronización y proporciona su ruta al flujo. El botón de ejecución
debe enviar solo `RutaZip`. No se debe pasar un adjunto a
`flujoSubirDriveTasaciones.Run`: Power Apps lo serializa en Base64 y el límite
de mensaje de Power Automate se alcanza antes de que el archivo llegue a
OneDrive. `MaxAttachments = 1` explica el texto visual de que se alcanzó el
número máximo de archivos; no es el límite de tamaño.

## Power Automate

El flujo debe mantener esta secuencia:

1. Obtener el contenido del archivo ZIP indicado por `RutaZip` desde OneDrive, sin usar un nombre ni una ruta fijos.
2. Ejecutar `POST` hacia el endpoint de Cloud Run.
3. Enviar el contenido del archivo sin convertirlo a JSON o Base64.
4. Definir `Content-Type: application/zip`.
5. Crear `Resultado_Final.xlsx` en la carpeta de OneDrive usando el cuerpo de
   la respuesta HTTP como contenido del archivo.
6. Ejecutar PAD/IBM 3270 exclusivamente sobre las filas de la tabla Excel
   `tblParaProcesar`. No leer `tblRevisionIa` ni `tblControl` para operar.
7. Obtener y registrar `PRESTAMO` y `SEGURO INMUEBLE` en PAD/IBM 3270: Cloud
   Run los entrega vacíos porque no son campos extraídos del PDF.
8. Registrar el resultado de cada operación usando el `ID_CASO` de la misma
   fila de `tblParaProcesar` y actualizar la fila coincidente de `tblControl`.

No se debe usar el contrato anterior de Google Sheets, que enviaba JSON y
esperaba una respuesta JSON.


## Lotes mayores a 30 MiB

Para evitar el l?mite de entrada HTTP/1, reemplazar el POST binario por estas acciones:

1. **Iniciar carga**: `POST` con `Content-Type: application/json` y el cuerpo `{"operacion":"iniciar_carga","nombre_archivo":"<nombre del ZIP>","tamano_bytes":<tama?o del archivo>}`.
2. **Subir ZIP**: `PUT` a `url_carga` de la respuesta anterior, con `Content-Type: application/zip` y el contenido binario devuelto por OneDrive. No usar Base64 ni JSON.
3. **Procesar carga**: `POST` JSON al mismo endpoint con `solicitud_proceso` de **Iniciar carga**. El cuerpo de esta respuesta es `Resultado_Final.xlsx`; usarlo directamente en **Crear archivo** de OneDrive.

La URL de carga es temporal, solo puede escribir en un objeto privado y vence en 15 minutos. El límite del servicio para esta ruta es 90 MB. Mantener el contenido binario en el cuerpo de la acción HTTP y evitar expresiones `base64()`, `string()` o JSON.
