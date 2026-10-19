# Contrato de la tabla PARA_PROCESAR

Power Automate consume únicamente la tabla `tblParaProcesar` de la primera
hoja, denominada `PARA_PROCESAR`. Conserva las 24 columnas de negocio en el
mismo orden y añade `ID_CASO` como última columna técnica para relacionar la
operación con `CONTROL`. Las hojas `REVISION_IA` y `CONTROL` no deben usarse
para cargar datos contra IBM 3270.

| Columna | Campo | Origen | Regla |
|---|---|---|---|
| A | PRESTAMO | Hoja de control autorizada | En lotes con control, solo número de 20 dígitos validado antes de cargar el PDF. En lotes históricos sin control permanece vacío. Nunca se infiere del PDF ni del 3270. |
| B | TIPO DE INMUEBLE | Tipo extraído | Etiqueta completa: `DEPARTAMENTO` o `CASA`. El código del bloque `MASIVO` del catálogo `DATOS` se conserva en `CONTROL`. |
| C | VALOR DEL BIEN | Reservado | Se deja vacío por compatibilidad con la salida MASIVO histórica. |
| D | MONEDA | Tasación | `PEN` si existe un valor elegido en soles; `USD` solo como respaldo si el PDF no contiene PEN. Solo se emiten códigos existentes en `DATOS`. En lotes con control debe coincidir con `MONEDA_OPERADOR`; una discrepancia va a revisión. |
| E | IMPORTE | Tasación | Valor elegido en la moneda de salida; prioriza PEN y se emite como texto con miles y dos decimales, por ejemplo `735,096.00`. |
| G:K | Direccion | Direccion del inmueble | Se estructura desde direccion registral; minuta es el segundo respaldo e inspeccion ocular el ultimo. Una direccion municipal o matriz no sustituye esas fuentes. El tipo de via conserva la etiqueta completa, por ejemplo `CALLE`, `JIRON` o `AVENIDA`. |
| M:O | Ubicacion | Direccion del inmueble | Tipo, nombre de ubicacion y distrito. El tipo conserva la etiqueta completa, por ejemplo `URBANIZACION`. Si no existe codigo autorizado, UBICACION y UBICACION1 permanecen vacias; no se sustituyen por `SN` y la fila puede continuar si la geografia obligatoria esta completa. Una referencia realmente necesaria se incorpora a `DATOS` por el proceso autorizado; no se inventan codigos. |
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
final se registran en `CONTROL`, junto con la proyección operativa autorizada
(`ID_INGRESO`, seguro de origen, expediente y moneda de operador). `REVISION_IA`
replica los campos necesarios para revisar las excepciones. Ninguno modifica
las columnas de `PARA_PROCESAR` fuera de `PRESTAMO`.
