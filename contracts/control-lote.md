# Contrato de control de lote

## Propósito

La hoja que recibe el operador contiene datos de atención y enlaces de
tasaciones. Antes de iniciar un lote, Power Apps construye una **proyección
operativa** por PDF. Esa proyección permite que Cloud Run una el PDF con su
préstamo y su moneda sin transportar DNI, nombre de cliente ni enlaces de
descarga.

El libro de control se conserva en `ControlEntrada`; los PDFs materializados
se cargan a `PDFs`. Cloud Run nunca descarga los enlaces de la hoja original.
`Controles` se reserva para los JSON técnicos que disparan la orquestación de
un lote y no debe contener libros Excel.

## Tabla que debe preparar el operador

Crear una tabla de Excel llamada `tblControlLote` con estos encabezados exactos:

| Encabezado | Requerido | Regla |
| --- | --- | --- |
| `ID_INGRESO` | Sí | Único dentro del lote. De 1 a 64 caracteres: letras, números, guion y guion bajo. |
| `ARCHIVO_PDF` | Sí | Nombre exacto del PDF que ya está en `PDFs`, por ejemplo `D01.pdf`. Solo Power Apps lo usa para unir la fila al archivo. |
| `PRESTAMO` | Sí | Texto de exactamente 20 dígitos. La celda debe ser de tipo **Texto** para conservar ceros iniciales. |
| `MONEDA_OPERADOR` | Sí | `PEN`, `SOLES`, `S/`, `USD`, `DOLAR` o `DOLARES`. Cloud normaliza a `PEN` o `USD`. |
| `SEGURO_ORIGEN` | No | Referencia operativa que se conserva en `CONTROL`; no se escribe en `PARA_PROCESAR`. |
| `NRO_EXPEDIENTE` | No | Referencia de conciliación que se conserva en `CONTROL`; no se escribe en `PARA_PROCESAR`. |

La tabla se crea a partir de la hoja operativa, pero no incluye `DNI`,
`NOMBRE_CLIENTE`, `URL_TASACION`, `LINK_TASACION` ni otra información personal o
enlaces. Esos datos no deben añadirse como columna de Power Apps ni como parte
del objeto que registra el lote.

Para la prueba con los diez casos, `ARCHIVO_PDF` es la llave explícita que
relaciona cada fila de control con los nombres de archivo disponibles. No se
infiere la relación por posición de fila, préstamo, nombre de cliente ni el
contenido del PDF.

## Objeto que llega a Cloud Run

Por cada PDF seleccionado, Power Apps debe enviar al flujo
`auto-tasacion-iniciar-lote` un objeto con esta forma:

```json
{
  "item_id": "<id-del-elemento-onedrive>",
  "etag": "<etag-del-elemento-onedrive>",
  "nombre": "<archivo-pdf>",
  "tamano_bytes": 12345,
  "id_ingreso": "<id-tecnico>",
  "prestamo": "<20-digitos>",
  "moneda_operador": "PEN",
  "seguro_origen": "<referencia-opcional>",
  "nro_expediente": "<referencia-opcional>"
}
```

El flujo existente ya transporta el JSON recibido hacia la API de lotes. No
necesita una acción nueva de Power Automate para estos cinco campos.

El registro rechaza el lote completo si ocurre cualquiera de estas condiciones:

- una fila de control falta para un PDF seleccionado;
- un `ID_INGRESO` se repite;
- el préstamo no tiene exactamente veinte dígitos;
- la moneda no es válida;
- se mezcla un PDF con control y otro sin control;
- el objeto contiene DNI, nombre de cliente, enlace u otro campo no autorizado.

La clave de idempotencia incluye la proyección de control. Si se corrige
préstamo, moneda, seguro o expediente, se crea un lote distinto aunque los PDFs
no hayan cambiado.

## Resultado esperado

Cuando la extracción del PDF está completa y la moneda coincide:

- `PARA_PROCESAR!A` recibe `PRESTAMO`.
- `PARA_PROCESAR!D:E` conservan moneda e importe extraídos de la tasación.
- `CONTROL` conserva `ID_INGRESO`, `SEGURO_ORIGEN`, `NRO_EXPEDIENTE` y
  `MONEDA_OPERADOR` para conciliación.

Si la moneda de la hoja y la moneda que se puede determinar de la tasación no
coinciden, el caso se dirige a `REVISION_IA` con estado
`REGLA_NEGOCIO_PENDIENTE`. No se cambia la moneda ni se envía la fila a la cola
operable de forma automática.

Los lotes históricos que no declaran campos de control siguen siendo válidos a
nivel de manifiesto y conservan `PRESTAMO` vacío, pero sus filas se derivan a
revisión porque el contrato actual de preparación de macro exige préstamo. Un
lote no puede combinar ambos modos.
