# Manual de uso — Automatización de tasaciones

## Objetivo

Procesar los informes PDF de tasación cargados en la carpeta de Drive
autorizada, extraer sus datos estructurados y descargar un Excel con los casos
validados para el siguiente paso operativo.

El proceso no sustituye la revisión humana: cualquier dato ausente o ambiguo
queda en una bandeja de revisión antes de ser exportado.

## Antes de comenzar

El operador necesita acceso a:

- La carpeta de Google Drive designada para las tasaciones.
- El Google Sheet de la automatización.
- El menú **Automatización de Tasaciones** dentro del Sheet.

Utilice únicamente documentos autorizados y nunca copie datos de clientes en
correos, chats o archivos personales.

## Flujo de operación

### 1. Cargar los PDFs

1. Abra la carpeta de Drive de tasaciones.
2. Cargue los informes en formato PDF.
3. Confirme que cada documento tiene un nombre identificable y que abre sin
   pedir contraseña.

No modifique ni elimine archivos mientras el lote se está procesando.

### 2. Escanear la carpeta

1. Abra el Google Sheet.
2. Seleccione **Automatización de Tasaciones → 1. Escanear PDFs desde Google
   Drive**.
3. Espere el aviso que indica cuántos PDFs fueron detectados.
4. Revise la pestaña **🎛️ Panel de Entrada**. Debe contener el nombre de cada
   PDF, su identificador interno de Drive y la fecha de modificación.

Si el total no coincide con el de Drive, vuelva a escanear antes de continuar.

### 3. Procesar y clasificar

1. Seleccione **Automatización de Tasaciones → 2. Procesar y clasificar
   archivos**.
2. Espere el mensaje final; no cierre el Sheet durante el proceso.
3. El sistema crea o actualiza dos pestañas:

   - **⚡ Listos para el Banco**: casos extraídos sin observaciones.
   - **🔍 Bandeja de Revisión**: casos que requieren validación humana.

Cada fila incluye los siguientes grupos de datos:

- Identificación y metadatos del PDF.
- Dirección, tipo de inmueble y la página donde se detectó cada dato.
- Valor comercial y valor de reconstrucción, en US$ y S/.
- Año de construcción, número de pisos y sótanos.
- Observación de extracción y estado del caso.

Un dato vacío no significa cero ni un valor por defecto: debe ser revisado.

### 4. Revisar casos observados

1. Seleccione **Automatización de Tasaciones → 3. Abrir panel de revisión**.
2. Lea la dirección, el tipo detectado y la observación mostrada por el panel.
3. Abra el PDF original desde Drive y confirme el dato usando la página de
   evidencia indicada en la fila.
4. Si corresponde, corrija el tipo de inmueble desde el panel y apruebe el
   caso.

Al aprobarse, el caso se marca como validado y se agrega a **Listos para el
Banco**. No apruebe una fila si el PDF no permite confirmar sus datos.

### 5. Generar el Excel

1. Compruebe que **Listos para el Banco** contiene únicamente casos correctos.
2. Seleccione **Automatización de Tasaciones → 4. Generar Excel de casos
   validados**.
3. El sistema muestra un enlace a un archivo `.xlsx` creado en Google Drive.
4. Abra el enlace y descargue el Excel.

El Excel contiene las columnas de extracción, pero no VBA. Para ejecutar la
macro NT3270/HIPO, importe o copie los datos en la plantilla `.xlsm` aprobada
por el área; no intente agregar macros al archivo descargado.

## Controles previos a la entrega

Antes de usar el Excel en el proceso posterior, confirme:

- Todos los casos tienen estado validado.
- Los valores elegidos corresponden al tipo de inmueble.
- No hay observaciones de extracción pendientes.
- El número de filas del Excel coincide con el lote validado en el Sheet.
- El archivo se guarda solo en una ubicación corporativa autorizada.

## Problemas frecuentes

| Situación | Acción recomendada |
| --- | --- |
| No aparecen PDFs al escanear | Verifique permisos, formato PDF y carpeta configurada. Vuelva a escanear. |
| Un caso queda en revisión | Compruebe el PDF y la página de evidencia; complete o corrija solo información verificable. |
| El lote muestra un error de conexión | Espere unos minutos, recargue el Sheet y pruebe con un lote pequeño. Escale si persiste. |
| El Excel no contiene un caso | Revise que esté validado y presente en **Listos para el Banco** antes de exportar. |
| El Excel no ejecuta la macro | Es normal: `.xlsx` no conserva VBA. Use la plantilla `.xlsm` institucional. |

## Escalamiento

Registre el nombre del PDF, fecha/hora, descripción del problema y una captura
sin información sensible. Envíelo al equipo de automatización junto con el
enlace corporativo al documento, nunca como adjunto por canales no autorizados.
