# Contrato de la hoja MASIVO

La macro consume la primera hoja, denominada `MASIVO`, con 24 columnas fijas.
No se debe alterar el orden. La hoja `CONTROL_EXTRACCION` es informativa y no
debe ser usada por la macro.

| Columna | Campo | Origen | Regla |
|---|---|---|---|
| A | PRESTAMO | PDF | Solo número de 20 dígitos con evidencia. Si falta, queda vacío. |
| B | TIPO DE INMUEBLE | Tipo extraído | `C` para departamento y `N` para casa, según catálogo MASIVO. |
| C | VALOR DEL BIEN | Tasación | Prioriza valor elegido en US$. |
| D | MONEDA | Tasación | `USD` si se usa C; `PEN` cuando solo existe valor en soles. |
| E | IMPORTE | Tasación | Igual al valor del bien hasta que el proceso operativo defina otra regla. |
| G:K | Dirección | Dirección del inmueble | Se estructura desde la dirección extraída del PDF. |
| M:O | Ubicación | Dirección del inmueble | Tipo, nombre de ubicación y distrito. |
| P, R, T | Códigos geográficos | Catálogo | Solo se informa una coincidencia explícita. |
| U | CLASE | Pisos | 1: hasta 4; 2: de 5 a 10; 3: más de 10. |
| V:W | PISOS, SOTANOS | PDF | Números extraídos; se dejan vacíos sin evidencia. |
| X | AÑO | PDF | Año de construcción o edificación, no fecha de inspección. |

Las columnas F, L, Q y S se reservan para el formato heredado de la macro.
Las excepciones y la evidencia por página se registran en
`CONTROL_EXTRACCION`.
