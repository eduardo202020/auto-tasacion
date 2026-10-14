# Contrato del resultado Cloud a la plantilla MASIVO

**Fecha:** 2026-10-14
**Estado:** análisis estático; no se ejecutó Excel, VBA, PCOMM ni IBM 3270

## Alcance y evidencia

Se revisó como referencia una plantilla `.xlsm` que representa el último tramo
operativo. Contiene las hojas `MASIVO`, `PRINT_PANTALLAS` y `DATOS`. Su hoja
`MASIVO` tiene la tabla `Tabla164` en `A:Y`, el botón **EJECUTAR** asociado a
`segHipoMasiv` y el botón **LIMPIAR** asociado a
`Borrar_filas_Tabla_Masivo`.

La guía visual de operación establece una precondición: la sesión `A` de PCOMM
debe estar autenticada y en la pantalla de espera antes de iniciar la macro.
La guía contiene credenciales que no se copiaron, registraron ni usaron. Las
credenciales no formarán parte de PAD, de la plantilla ni de este repositorio.

El proyecto VBA no tiene firma digital. El libro también conserva una referencia
externa heredada. Ninguno de los dos elementos se considera apto para una
ejecución automatizada hasta que se controle su procedencia, se elimine o
resuelva la referencia externa y se compile una copia versionada.

## Qué consume y produce la macro

`segHipoMasiv` solicita al operador una fila inicial y una final. Recorre el
rango seleccionado, interactúa con PCOMM y escribe en `Y` el identificador de
seguro devuelto por la sesión. Si encuentra un mensaje de pantalla, hoy escribe
ese mensaje también en `Y`; por tanto esa columna no expresa por sí sola un
estado inequívoco.

Antes de operar, exige que `PRESTAMO` en la columna `A` tenga exactamente 20
caracteres. Sin ese valor no inicia la consulta. La macro lee estos valores de
la fila:

| Columna | Uso observado |
| --- | --- |
| `A` | Préstamo de 20 caracteres. |
| `B` | Tipo de inmueble. La versión revisada tiene un defecto: lee siempre `B2` en vez de la fila actual. |
| `C` | Código `MASIVO` derivado del tipo. |
| `E` | Importe. |
| `G` | Código de tipo de vía. |
| `H:K` | Domicilio complementario, exterior, interior y referencia. |
| `M:N` | Código y detalle de ubicación. |
| `O:P`, `R`, `T` | Distrito y códigos geográficos requeridos por la pantalla. |
| `U:X` | Clase, pisos, sótanos y año. |
| `Y` | Resultado de seguro o mensaje de error de la macro. |

La plantilla calcula `C`, `G`, `M`, `P`, `R`, `T` y `U` con fórmulas y los
catálogos de la hoja `DATOS`. Esas fórmulas parten, respectivamente, de los
valores legibles de tipo, vía, ubicación, distrito, provincia, departamento y
pisos. La macro consume los códigos calculados, no los valores legibles de
origen.

## Comparación con el resultado Cloud

La cola `PARA_PROCESAR` ya conserva las posiciones que la macro usa para
importe, dirección, domicilio, números, referencia, ubicación, distrito,
códigos, pisos, sótanos y año. Eso permite una adaptación determinista.

Hay tres diferencias que impiden invocar la macro sobre el `.xlsx` entregado
por Cloud:

1. El resultado Cloud es un `.xlsx` con `PARA_PROCESAR`, `REVISION_IA` y
   `CONTROL`; no es la plantilla `.xlsm` con `MASIVO` y no incluye su VBA.
2. Cloud conserva `ID_CASO` en `Y`; la macro reserva `Y` para el seguro o el
   error que devuelve PCOMM. `ID_CASO` no puede permanecer allí durante la
   macro.
3. Cloud deja `PRESTAMO` vacío de forma deliberada. La fuente autorizada ya se
   identificó: es la fila operativa recibida por el operador. Sin embargo, el
   manifiesto vigente no transporta ni relaciona esa fila con el PDF. La macro
   necesita el préstamo como llave de inicio y no puede obtenerlo consultando
   3270, porque lo usa antes de iniciar la consulta.

Cloud conserva los nombres de vía y ubicación en las columnas que usa su
contrato actual. La plantilla puede convertirlos en los códigos esperados con
sus fórmulas locales. Los códigos de provincia y departamento que ya entrega
Cloud también permiten rellenar el destino sin volver a interpretar PDFs.

Para `CASA`, el importe operativo debe seguir siendo el valor de reconstrucción
confirmado por Operaciones. El código de `C` no representa ese importe: es el
código `MASIVO` que la plantilla deriva del tipo de inmueble.

## Diseño objetivo: adaptador local, no conversión destructiva

```mermaid
flowchart LR
    A[Resultado_Final XLSX de OneDrive] --> B[Validar contrato Cloud]
    B --> C[Copiar al directorio local del lote]
    C --> D[Crear copia local de plantilla MASIVO XLSM]
    D --> E[Adaptar filas y conservar trazabilidad]
    E --> F[Macro sin diálogos]
    F --> G[Resultado estructurado del lote]
    G --> H[Publicación de salida autorizada]
```

El adaptador debe preservar el `Resultado_Final` original. Para cada fila
operable crea una copia local de la plantilla, carga `MASIVO` y mantiene la
trazabilidad en una hoja `TRAZA_PAD` o en columnas fuera de `A:Y`:

| Origen Cloud | Destino de plantilla | Regla |
| --- | --- | --- |
| `PRESTAMO` | `A` | Obligatorio, 20 caracteres y procedente de una fuente autorizada. |
| `TIPO DE INMUEBLE` | `B` | Copiar el valor normalizado. |
| Tipo, vía, ubicación, distrito, provincia, departamento y pisos | Campos de entrada de `MASIVO` | Conservar las fórmulas locales que generan `C`, `G`, `M`, `P`, `R`, `T` y `U`, o cargar los mismos códigos validados. |
| `IMPORTE`, domicilio, números, referencia, ubicación, códigos y año | Columnas equivalentes de `MASIVO` | Copiar por nombre de campo y validar antes de abrir Excel. |
| `ID_CASO` e `ID_LOTE` | `TRAZA_PAD` | Nunca ocupar `Y`; relacionar fila, estado, resultado y detalle. |
| Resultado de PCOMM | `Y` y `TRAZA_PAD` | `Y` mantiene el seguro; `TRAZA_PAD` separa `ESTADO`, error y marca temporal. |

La copia `.xlsm` se ejecuta solo en el directorio local de runtime. Una salida
sincronizada con OneDrive requiere una publicación posterior, explícita y con
un nombre de resultado distinto. No se modifica el archivo Cloud ni se guarda
la plantilla maestra sobre OneDrive durante la ejecución.

## Cambios necesarios antes de habilitar PAD + macro

1. Incorporar la fila operativa autorizada a la entrada y relacionarla de forma
   estable con cada PDF. El adaptador debe validar `PRESTAMO` por `ID_CASO` y
   exigir exactamente 20 caracteres. Es el bloqueo funcional actual.
2. Versionar una plantilla `.xlsm` aprobada, eliminar o resolver su referencia
   externa y verificar su integridad antes de cada uso.
3. Refactorizar `segHipoMasiv` para recibir el lote y las filas sin
   `InputBox` ni `MsgBox`, usar referencias calificadas a `MASIVO` y corregir
   la lectura fija de `B2` por la fila actual.
4. Sustituir la ruta fija de capturas y PDF por una ruta de runtime del lote.
   Las capturas y errores deben asociarse a `ID_CASO` en `TRAZA_PAD`.
5. Añadir un resultado estructurado por fila. No se debe interpretar el texto
   de `Y` para distinguir un seguro de un error.
6. Crear una prevalidación que detenga el lote si faltan préstamo, códigos,
   importes o campos requeridos. Un caso bloqueado queda reportado; no abre
   PCOMM.
7. Validar en una sesión `A` de prueba, ya autenticada y en espera, con datos
   sintéticos antes de operar filas reales.

Hasta completar esos puntos, el alcance validado sigue siendo Cloud → PAD en
`SIMULACION`. No hay autorización ni evidencia para ejecutar VBA, PCOMM o IBM
3270 en esta integración.
