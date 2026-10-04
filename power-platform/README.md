# Integración Power Platform

Los artefactos de Power Apps y Power Automate se administran en el entorno
corporativo Microsoft. Este directorio documenta el contrato que deben usar.

## Power Apps

La aplicación ejecuta el flujo `auto-tasacion`. La carga del ZIP permanece en
la carpeta autorizada de OneDrive; la aplicación no transmite secretos ni
procesa PDFs directamente.

## Power Automate

El flujo debe mantener esta secuencia:

1. Obtener el contenido de `/auto-tasaciones/auto.zip` desde OneDrive.
2. Ejecutar `POST` hacia el endpoint de Cloud Run.
3. Enviar el contenido del archivo sin convertirlo a JSON o Base64.
4. Definir `Content-Type: application/zip`.
5. Crear `Resultado_Final.xlsx` en la carpeta de OneDrive usando el cuerpo de
   la respuesta HTTP como contenido del archivo.

No se debe usar el contrato anterior de Google Sheets, que enviaba JSON y
esperaba una respuesta JSON.
