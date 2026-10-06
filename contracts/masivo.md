# Contrato de la tabla PARA_PROCESAR

Power Automate consume únicamente la tabla `tblParaProcesar` de la primera
hoja, denominada `PARA_PROCESAR`. Conserva las 24 columnas de negocio en el
mismo orden y añade `ID_CASO` como última columna técnica para relacionar la
operación con `CONTROL`. Las hojas `REVISION_IA` y `CONTROL` no deben usarse
para cargar datos contra IBM 3270.

| Columna | Campo | Origen | Regla |
|---|---|---|---|
| A | PRESTAMO | PDF / 3270 | Solo número de 20 dígitos con evidencia. Si falta, queda vacío para que Power Automate/IBM 3270 lo complete. |
| B | TIPO DE INMUEBLE | Tipo extraído | Etiqueta completa: `DEPARTAMENTO` o `CASA`. El código del bloque `MASIVO` del catálogo `DATOS` se conserva en `CONTROL`. |
| C | VALOR DEL BIEN | Reservado | Se deja vacío por compatibilidad con la salida MASIVO histórica. |
| D | MONEDA | Tasación | `PEN` si existe un valor elegido en soles; `USD` solo como respaldo si el PDF no contiene PEN. Solo se emiten códigos existentes en `DATOS`. |
| E | IMPORTE | Tasación | Valor elegido en la moneda de salida; prioriza PEN y se emite como texto con miles y dos decimales, por ejemplo `735,096.00`. |
| G:K | Dirección | Dirección del inmueble | Se estructura desde la dirección según minuta; inspección ocular es respaldo y dirección municipal/matriz el último recurso. El tipo de vía conserva la etiqueta completa, por ejemplo `CALLE`, `JIRON` o `AVENIDA`. |
| M:O | Ubicación | Dirección del inmueble | Tipo, nombre de ubicación y distrito. El tipo conserva la etiqueta completa, por ejemplo `URBANIZACION`. Si no está homologado, UBICACION y UBICACION1 quedan vacíos; la geografía válida se conserva. |
| P, R, T | Códigos geográficos | Catálogo | Solo se informa una coincidencia explícita. |
| U | CLASE | Pisos | 1: hasta 4; 2: de 5 a 10; 3: más de 10. Se toma del bloque `CLASE INMUEBLE` de `DATOS`. |
| V:W | PISOS, SOTANOS | PDF | Prioriza la tabla de características del inmueble; usa la descripción solo si no existe una tabla legible. La azotea no cuenta como piso ni incrementa PISOS. |
| X | AÑO | PDF | Año explícito de construcción/edificación. Si no existe, es `año de expedición − edad efectiva`, solo con ambas evidencias y si el resultado está entre 1900 y el año de expedición. |
| Y | ID_CASO | Servicio | Llave técnica inmutable, derivada del nombre interno del PDF y su contenido, para que Power Automate actualice el resultado de IBM 3270 en CONTROL. PDFs con el mismo contenido y distinto nombre reciben llaves distintas. No es un dato de negocio para el Mainframe. |

Las columnas F, L, Q y S se reservan para el formato heredado de integración.
Las excepciones no llegan a `PARA_PROCESAR`: se registran en `REVISION_IA`.
La evidencia por página, el origen del año, los códigos usados, el resultado
de IA, el perfil, la empresa de tasación identificada por firma, el origen de
esa identificación (`TEXTO_PDF`, `OCR_LOCAL` o `PERFIL_TECNICO`) y la ruta
final se registran en `CONTROL`. `REVISION_IA` replica esos metadatos de perfil
para revisar las excepciones. Ninguno modifica las columnas de `PARA_PROCESAR`.
