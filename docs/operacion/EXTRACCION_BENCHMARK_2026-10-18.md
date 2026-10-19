# Benchmark de extraccion determinista: auditoria de precision

Fecha de corrida final: 2026-10-19.

## Alcance y resguardo de evidencia

La corrida usa `auto-tasacion-benchmark/` solo como corpus externo. El harness
lee PDFs desde los ZIP y guarda JSON de auditoria y libros de comprobacion en
`%TEMP%`. No se versionan PDFs, XLSX, XLSM, direcciones completas, prestamos,
expedientes ni texto documental.

## Auditoria focalizada D01, D07, D08 y D09

| Caso | Evidencia documental auditada | Clasificacion | Decision fail-closed |
| --- | --- | --- | --- |
| D01 | En pagina 3 de Braschi Construyo, las celdas de `N de pisos en el edificio` y `N de sotanos y/o semisotanos` estan vacias. El unico `1` de la fila pertenece a `N Unidades en el conjunto`. | `SIN_EVIDENCIA` | No se infieren pisos, sotanos ni clase. Ruta `PENDIENTE_IA`; queda fuera de `PARA_PROCESAR`. |
| D07 | La coincidencia generica con `Reposicion` tomaba `Metodo de Costos o Reposicion`, que documenta el metodo de valor comercial. El valor de reconstruccion se presenta en su seccion propia. | `BUG_EXTRACCION`, resuelto | El ancla exige `Valor(es) de reconstruccion/reposicion` o `V. Reconstruccion`. Se descarta el metodo comercial y se conserva la seleccion respaldada por la seccion de reconstruccion. |
| D08 | El PDF contiene una jerarquia geografica distinta de la fila golden. `Departamento <nombre geografico>` se interpretaba como interior. | `BUG_PARSING` y `GOLDEN_POSIBLEMENTE_INCORRECTO` | Un departamento geografico no llena `INTERIOR`; un identificador como `Departamento 101` sigue siendo interior valido. Se preserva la geografia del PDF y catalogo. |
| D09 | Paginas 3 y 9 declaran primer construyo de dos pisos y azotea. En pagina 5 la tabla de pisos esta vacia, pero la distribucion enumera hasta un tercer piso. | `CONFLICTO_DOCUMENTAL` | La extraccion mantiene la trazabilidad del valor declarado, pero la ruta pasa a `REGLA_NEGOCIO_PENDIENTE`. No genera fila operativa hasta definir que evidencia prevalece. |

La auditoria detallada con valores, paginas y coordenadas se genero fuera de Git
en `%TEMP%/auto-tasacion-benchmark-20261019/`.

## Cambios implementados con evidencia

- Se acoto el ancla de valor de reconstruccion para que el nombre de un metodo
  comercial no sea considerado un valor. La regla es semantica y reutilizable;
  no depende de archivo, proveedor ni importe.
- El parser conserva `Departamento <nombre de departamento peruano>` como nivel
  geografico y no como interior. `Departamento 101` sigue siendo un interior
  valido.
- Se detecta el conflicto entre una declaracion de primer construyo con pisos y
  azotea y una distribucion posterior con un piso de numeracion mayor. El caso
  se deriva a regla de negocio, sin decidir por una fuente documental.
- El benchmark golden informa por cada direccion estructurada `EXACT_MATCH`,
  `SEMANTIC_MATCH` o `DIFFERENT`. La equivalencia semantica se limita a
  mayusculas, tildes, espacios, signos basicos y abreviaturas de direccion
  declaradas por `DATOS`; no altera datos operativos ni unifica numeros, vias,
  urbanizaciones o distritos distintos.

## Golden 10

| Metrica | Antes de esta iteracion | Resultado final |
| --- | ---: | ---: |
| `LISTO_DETERMINISTA` | 8 | 8 |
| `PENDIENTE_IA` | 2 | 1 |
| `REGLA_NEGOCIO_PENDIENTE` | 0 | 1 |
| Ambiguedades de importe | 1 | 0 |
| Moneda conciliada | 9/10 | 10/10 |
| Importe conciliado | 9/10 | 10/10 |
| Decision final conciliada | 8/10 | 8/10 |

El total de casos listos no aumenta porque D09 pasa intencionalmente de listo a
regla de negocio ante evidencia documental contradictoria. Esa derivacion evita
una fila operativa con una decision de pisos no aprobada.

La comparacion de direccion final registra 9 `EXACT_MATCH`, 0
`SEMANTIC_MATCH` y 1 `DIFFERENT`. El unico desajuste real es D01; no se
modifica por no existir una regla operativa aprobada para reasignar componentes
estructurados de direccion. D09 conserva coincidencia de direccion aunque su
decision de pisos se mantiene bloqueada.

## Corpus comparable de 120 y corpus completo de 150

| Ruta | Baseline 120 | Antes del control D09 120 | Final 120 | Antes del control D09 150 | Final 150 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `LISTO_DETERMINISTA` | 51 | 76 | 75 | 93 | 92 |
| `PENDIENTE_IA` | 64 | 33 | 33 | 41 | 41 |
| `REGLA_NEGOCIO_PENDIENTE` | 5 | 7 | 8 | 10 | 11 |
| `DOCUMENTO_NO_TASACION` | - | 2 | 2 | 2 | 2 |
| `REVISION_HUMANA` | - | 2 | 2 | 4 | 4 |

La reduccion de un listo corresponde al mismo conflicto documental D09. Los
controles finales conservan cero listos con importe no positivo, cero prestamos
de control invalidos y cero casos listos sin geografia. D124 conserva la
seleccion PEN documentada; D130 y D131 siguen como `ESTUDIO_TITULOS` y
`DOCUMENTO_NO_TASACION`.

## Puertas de calidad y decision

- `python -m unittest discover -s cloud-run/tests -v`: 112 pruebas, OK.
- `python tools/validate_profile_catalog.py`: 0 errores.
- `python -m compileall -q cloud-run tools`: OK.
- `python tools/verify_workbook.py`: contrato XLSX OK.
- Golden 10 y corpus 150: contratos XLSX sin incidencias.

**No apto para despliegue.** D01 no tiene evidencia de pisos/sotanos. D09 tiene
un conflicto documental que requiere regla de Operaciones. La representacion
operativa de las direcciones D01 y D09, y la geografia golden de D08, requieren
validacion del propietario del dato antes de aceptar discrepancias como
resultado esperado.
