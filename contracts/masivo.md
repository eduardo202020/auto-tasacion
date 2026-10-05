# Contrato de la tabla PARA_PROCESAR

Power Automate consume únicamente la tabla `tblParaProcesar` de la primera
hoja, denominada `PARA_PROCESAR`. Conserva las 24 columnas de negocio en el
mismo orden y añade `ID_CASO` como última columna técnica para relacionar la
operación con `CONTROL`. Las hojas `REVISION_IA` y `CONTROL` no deben usarse
para cargar datos contra IBM 3270.

| Columna | Campo | Origen | Regla |
|---|---|---|---|
| A | PRESTAMO | PDF / 3270 | Solo número de 20 dígitos con evidencia. Si falta, queda vacío para que Power Automate/IBM 3270 lo complete. |
| B | TIPO DE INMUEBLE | Tipo extraído | `C` para departamento y `N` para casa, según el bloque `MASIVO` del catálogo `DATOS`. |
| C | VALOR DEL BIEN | Tasación | Prioriza valor elegido en US$. |
| D | MONEDA | Tasación | `USD` si se usa C; `PEN` cuando solo existe valor en soles. Solo se emiten esos códigos si existen en `DATOS`. |
| E | IMPORTE | Tasación | Igual al valor del bien hasta que el proceso operativo defina otra regla. |
| G:K | Dirección | Dirección del inmueble | Se estructura desde la dirección extraída del PDF. |
| M:O | Ubicación | Dirección del inmueble | Tipo, nombre de ubicación y distrito. |
| P, R, T | Códigos geográficos | Catálogo | Solo se informa una coincidencia explícita. |
| U | CLASE | Pisos | 1: hasta 4; 2: de 5 a 10; 3: más de 10. Se toma del bloque `CLASE INMUEBLE` de `DATOS`. |
| V:W | PISOS, SOTANOS | PDF | Números extraídos; se dejan vacíos sin evidencia. |
| X | AÑO | PDF | Año explícito de construcción/edificación. Si no existe, es `año de expedición − edad efectiva`, solo con ambas evidencias y si el resultado está entre 1900 y el año de expedición. |
| Y | ID_CASO | Servicio | Llave técnica inmutable para que Power Automate actualice el resultado de IBM 3270 en CONTROL. No es un dato de negocio para el Mainframe. |

Las columnas F, L, Q y S se reservan para el formato heredado de integración.
Las excepciones no llegan a `PARA_PROCESAR`: se registran en `REVISION_IA`.
La evidencia por página, el origen del año, los códigos usados, el resultado
de IA y la ruta final se registran en `CONTROL`.
