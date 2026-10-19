# Benchmark de extraccion determinista: segunda iteracion

Fecha de corrida: 2026-10-18.

## Alcance y resguardo de evidencia

La corrida usa `auto-tasacion-benchmark/` exclusivamente como corpus externo.
El harness lee los PDF directamente desde los ZIP y deja los JSON y los XLSX de
validacion en `%TEMP%`, fuera del repositorio. No se versionan PDF, XLSX, XLSM,
prestamos, expedientes, direcciones completas ni texto documental. Este informe
conserva solo metricas, identificadores tecnicos y diferencias semanticas.

## Cambios evaluados

- La clasificacion previa distingue `TASACION`, `ESTUDIO_TITULOS` y
  `DESCONOCIDO`. Un estudio de titulos solo se acepta cuando aparece temprano,
  tiene evidencia juridica y no hay senales fuertes de tasacion. Un anexo
  juridico no convierte una tasacion en documento no tasable.
- Si no hay capa de texto suficiente y la primera clasificacion es
  `DESCONOCIDO`, se ejecuta OCR local acotado unicamente para clasificacion y
  proveedor. El OCR no completa ni elige importes, pisos, moneda ni otros datos
  criticos.
- Un perfil tecnico separa `provider_id`, `template_id` y `layout_family`.
  Las estrategias y prioridades de seccion solo se aplican a firmas documentales
  verificables.
- La seleccion de valores es fail-closed: dos importes positivos diferentes en
  la prioridad maxima quedan sin elegir si la plantilla no declara una prioridad
  de seccion. Los ceros se mantienen como evidencia y nunca se envian a
  `PARA_PROCESAR`.
- La fecha de inicio de obra se admite solo para documentos que declaran una
  obra vigente; la fecha y la condicion pueden estar en paginas distintas.
- El contrato de workbook, las primeras 24 columnas de `PARA_PROCESAR`, el
  orden de columnas y el origen autorizado de `PRESTAMO` no cambiaron.

## Perfiles tecnicos incorporados

| Perfil | Provider | Template | Layout |
| --- | --- | --- | --- |
| Braschi A | Braschi | `braschi-layout-a-v1` | `LF-BRASCHI-A` |
| Braschi Construyo | Braschi | `braschi-construyo-tabla-v1` | `LF-BRASCHI-CONSTRUYO` |
| Layseca OP-D A/B | Layseca | `layseca-opd-layout-a/b-v1` | `LF-LAYSECA-OPD-A/B` |
| Layseca Construyo | Layseca | `layseca-construyo-v1` | `LF-LAYSECA-CONSTRUYO` |
| Quota A/B | Jalvo | `quota-layout-a/b-v1` | `LF-QUOTA-A/B` |
| Layout compartido A | varios | `shared-valuation-layout-a-v1` | `LF-A` |

Los proveedores sin evidencia suficiente conservan `generic-v1`; reconocer una
empresa no fuerza una plantilla.

## Golden 10

| Metrica | Resultado |
| --- | ---: |
| Listos deterministas | 8/10 |
| Pendientes por conflicto de importe | 2/10 |
| Tipo | 10/10 |
| Moneda | 9/10 |
| Importe | 9/10 |
| Pisos | 7/10 |
| Sotanos | 9/10 |
| Anio | 10/10 |
| Clase | 8/10 |
| Direccion estructurada | 2/10 |
| Geografia | 7/10 |
| Decision final | 8/10 |

D01 ya toma el importe y moneda de la columna documentada `VALOR TOTAL`, pero
permanece pendiente por pisos y sotanos. D07 queda bloqueado por candidatos de
reconstruccion de igual prioridad sin regla documental aprobada. D08 resuelve el
importe mediante la misma estrategia Braschi; D09 conserva una diferencia de
pisos cuyo texto del PDF declara dos pisos. Las diferencias de direccion y
geografia permanecen abiertas; no se corrigieron por nombre de archivo.

## Corpus comparable de 120 casos

| Ruta | Baseline | a3358de | Segunda iteracion |
| --- | ---: | ---: | ---: |
| `LISTO_DETERMINISTA` | 51 | 91 | 74 |
| `PENDIENTE_IA` | 64 | 17 | 35 |
| `REGLA_NEGOCIO_PENDIENTE` | 5 | - | 7 |
| `DOCUMENTO_NO_TASACION` | 0 | - | 2 |
| `REVISION_HUMANA` | 0 | - | 2 |

La disminucion de listos frente a `a3358de` es intencional cuando aparece una
ambiguedad critica de importe. Es una regresion de throughput que evita copiar
un monto no sustentado.

## Corpus completo de 150 casos

| Ruta | Casos |
| --- | ---: |
| `LISTO_DETERMINISTA` | 91 |
| `LISTO_IA_VERIFICADO` | 0 |
| `PENDIENTE_IA` | 43 |
| `REGLA_NEGOCIO_PENDIENTE` | 10 |
| `DOCUMENTO_NO_TASACION` | 2 |
| `REVISION_HUMANA` | 4 |

Controles de calidad: cero listos con importe no positivo, cero prestamos de
control invalidos y cero casos sin geografia. Hay 35 ambiguedades de importe,
10 conflictos de moneda y 4 documentos `DESCONOCIDO`; se mantienen fuera de
la ruta automatica.

La cobertura de plantilla alcanza 64/150 documentos: `LF-A` 30,
`LF-LAYSECA-OPD-A` 10, `LF-BRASCHI-A` 7, `LF-QUOTA-A` 6, `LF-QUOTA-B` 5,
`LF-LAYSECA-OPD-B` 2, `LF-LAYSECA-CONSTRUYO` 2 y
`LF-BRASCHI-CONSTRUYO` 2. Los 86 restantes conservan plantilla y layout
vacios mediante `generic-v1`.

Los cuatro PDF sin texto de referencia activaron OCR local acotado. Ninguno
aporto evidencia suficiente de documento o proveedor; los cuatro fueron a
`REVISION_HUMANA`, sin inventar valores criticos. Los documentos de referencia
D130 y D131 se clasificaron como `ESTUDIO_TITULOS` y no entran a la ruta de
proceso.

## Puertas de calidad y decision

- `unittest discover -s cloud-run/tests -v`: 104 pruebas, OK.
- Catalogo de perfiles: 0 errores.
- `compileall`: OK.
- XLSX de prueba y contrato de workbook: OK.

**No apto para despliegue.** El contrato y los controles tecnicos pasan, pero
el Golden conserva diferencias criticas y el bloqueo fail-closed reduce el
throughput hasta que Operaciones documente reglas de seleccion para las tablas
de reconstruccion y se resuelvan D08 y D09 con evidencia verificable.
