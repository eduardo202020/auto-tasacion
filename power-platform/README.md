# Integración Power Platform

Los artefactos de Power Apps y Power Automate se administran en el entorno
corporativo Microsoft. Este directorio documenta el contrato que deben usar.

## Power Apps

La aplicación ejecuta el flujo `auto-tasacion`. La carga del ZIP permanece en
la carpeta autorizada de OneDrive; la aplicación no transmite secretos ni
procesa PDFs directamente.

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
7. Registrar el resultado de cada operación usando el `ID_CASO` de la misma
   fila de `tblParaProcesar` y actualizar la fila coincidente de `tblControl`.

No se debe usar el contrato anterior de Google Sheets, que enviaba JSON y
esperaba una respuesta JSON.
