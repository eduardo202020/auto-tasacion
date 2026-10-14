# Flujo operador → Cloud → plantilla MASIVO → 3270

**Fecha:** 2026-10-14
**Estado:** modelo operativo corregido; inspección estática solamente

## Propósito

Este documento corrige el origen de los datos que requiere el tramo final. El
préstamo no se obtiene del PDF ni se consulta en 3270: llega en la hoja que el
operador recibe para atender el lote. El PDF aporta la tasación y el flujo debe
conservar ambas fuentes hasta preparar la plantilla `MASIVO`.

No se registran aquí identificadores de clientes, vínculos de descarga,
documentos, credenciales ni datos de una operación real.

## Entrada del operador

Cada fila de la hoja operativa contiene como mínimo:

| Campo | Uso propuesto |
| --- | --- |
| `SEGURO` | Referencia de la operación. Se conserva en traza restringida; no ocupa `MASIVO!Y`, que es salida de la macro. |
| `PRESTAMO` | Identificador autorizado de 20 caracteres. Alimenta `MASIVO!A` después de validación. |
| `DNI` | Dato de trazabilidad restringida. No es necesario para la cola de la macro final. |
| `NOMBRE_CLIENTE` | Dato de trazabilidad restringida. No es necesario para la cola de la macro final. |
| `NRO_EXPEDIENTE` | Referencia de conciliación restringida. |
| `MONEDA` | Dato de origen que debe compararse con la moneda extraída del PDF. Una discrepancia se reporta, no se resuelve silenciosamente. |
| Enlace de tasación | Referencia desde la que se materializa el PDF mediante un mecanismo autorizado. No se transporta como URL en el manifiesto de Cloud Run. |

La llave de relación entre la fila y el PDF todavía debe formalizarse. Hasta
definirla, ningún dato de la fila se puede asociar de forma segura a un
`ID_CASO`.

## Flujo histórico observado

```mermaid
flowchart TD
    A[Hoja operativa] --> B[Hoja de validación]
    B --> C[Macro de descarga]
    C --> D[PDF local]
    D --> E[Extracción externa anterior]
    E --> F[Libro preparado]
    F --> G[Macro MASIVO]
    G --> H[PCOMM / 3270]
```

La macro histórica de validación usa la hoja activa con enlaces y seguros. Sus
rutinas descargan PDFs por automatización de navegador y una de ellas consulta
una dirección mediante PCOMM usando el seguro. Trabaja con selección de filas,
diálogos y rutas locales, por lo que es referencia funcional, pero no un
componente reutilizable directamente por Cloud ni por PAD desatendido.

La inspección del VBA no encontró una invocación a `python`, `pdf_extractor.py`
ni a otro script de Python. Por tanto, la extracción que antes se realizaba en
Colab fue un paso externo a ese libro. Si existía otro script de preparación,
debe incorporarse como evidencia separada antes de reproducir su comportamiento.

## Flujo objetivo

```mermaid
flowchart LR
    A[Hoja operativa autorizada] --> B[Registro de entrada y correlación]
    C[PDF materializado en OneDrive] --> B
    B --> D[Manifiesto de PDFs individuales]
    D --> E[Power Automate carga un PDF a GCS]
    E --> F[Cloud Run]
    F --> G[Resultado_Final XLSX]
    G --> H[Evento Cloud a PAD ya validado]
    H --> I[Adaptador local a plantilla MASIVO]
    I --> J[Macro sin diálogos]
    J --> K[Resultado por fila y traza]
```

1. Un proceso autorizado materializa cada PDF referenciado por la fila
   operativa en la carpeta de entrada de OneDrive. El diseño vigente no admite
   enlaces externos en el manifiesto: solo declara `item_id`, `etag`, nombre y
   tamaño de un PDF ya presente.
2. La capa de entrada crea una relación estable entre la fila operativa y el
   PDF, conserva los campos restringidos fuera de la cola bancaria y genera o
   enlaza el futuro `ID_CASO`.
3. El flujo actual procesa un PDF por vez. `service.py` invoca
   `pdf_extractor.py`; `address_parser.py` y `catalog.py` normalizan dirección,
   territorio y códigos. Esa combinación reemplaza la etapa externa anterior
   de extracción, sin descargar enlaces públicos desde Cloud Run.
4. Cloud une el resultado extraído con la metadata de entrada. `PRESTAMO` pasa
   validado a la preparación de macro; la moneda de origen se concilia con la
   moneda documentada; `DNI`, nombre y expediente permanecen en control
   restringido.
5. El resultado Cloud activa PAD, integración ya comprobada solamente en
   `SIMULACION`.
6. PAD conserva el XLSX original, crea una copia local de la plantilla `.xlsm`
   y llena `MASIVO` por encabezados. `ID_CASO`, `ID_LOTE`, seguro de origen,
   estado y errores se guardan fuera de `A:Y`, por ejemplo en `TRAZA_PAD`.
7. La macro final recibe una sesión de terminal ya preparada como precondición,
   procesa filas no bloqueadas y produce un resultado estructurado por fila.

## Contrato para la plantilla final

`excel-procesado-listo-para-pasar-macro.xlsm` usa `MASIVO!A:Y` y exige
`PRESTAMO` en `A`. La macro `segHipoMasiv` devuelve el seguro o un texto de
pantalla en `Y`. Por ello los datos se dividen así:

| Destino | Contenido |
| --- | --- |
| `MASIVO!A` | Préstamo validado de la fila operativa. |
| `MASIVO!B:X` | Resultado Cloud normalizado y fórmulas de catálogos de la plantilla. |
| `MASIVO!Y` | Solo resultado de la macro final. |
| `TRAZA_PAD` / `CONTROL` restringido | `ID_CASO`, lote, seguro de origen, expediente, DNI, cliente, conciliaciones y errores. |

La plantilla actual debe refactorizarse antes de invocarla desde PAD: seleccionar
filas sin `InputBox`, calificar las referencias a `MASIVO`, leer el tipo por
fila y reemplazar las rutas fijas de capturas por el runtime del lote.

## Brechas para implementar, en orden

1. Acordar la llave estable de la fila operativa y el PDF.
2. Implementar el ingreso de metadata y su almacenamiento restringido por
   `ID_CASO`; el manifiesto actual no lo soporta.
3. Definir la regla de conciliación de moneda de operador frente a moneda de
   tasación y promover las reglas aclaradas a código con casos sintéticos.
4. Crear el adaptador local que copie y llene una plantilla `.xlsm` aprobada,
   sin alterar el resultado Cloud ni la plantilla maestra.
5. Refactorizar y versionar la macro para ejecución no interactiva y salida
   estructurada por fila.
6. Solo tras las validaciones anteriores, realizar una prueba aislada con
   sesión PCOMM preparada y datos autorizados.

Hasta el punto 5, no se ejecutan VBA, PCOMM ni IBM 3270. El alcance comprobado
sigue siendo Cloud → PAD en simulación.
