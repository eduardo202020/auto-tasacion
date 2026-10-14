# Instrucciones de trabajo para agentes

## Propósito y alcance

Este repositorio automatiza la extracción documental de tasaciones hipotecarias.
La arquitectura masiva procesa manifiestos de PDFs individuales cargados desde
Power Automate a Cloud Storage. La ruta ZIP HTTP de hasta 90 MB permanece como
LEGACY / TRANSICIÓN.

Fuentes de verdad:

1. [`README.md`](README.md): visión de producto.
2. [`docs/AI_CONTEXT.md`](docs/AI_CONTEXT.md): modelo de dominio y rutas.
3. [`contracts/masivo.md`](contracts/masivo.md): contrato inmutable del XLSX.
4. [`contracts/control-lote.md`](contracts/control-lote.md): proyección de
   hoja de control por PDF.
5. [`cloud-run/README.md`](cloud-run/README.md): servicio y Job.

## Invariantes no negociables

- La ruta masiva recibe manifiestos y PDFs individuales; no usa ZIP, Microsoft
  Graph, `driveId`, GCS FUSE ni un request con el lote completo.
- Power Automate es el único componente que lee contenido de OneDrive.
- El Job solo procesa objetos `CARGADO` y mantiene en memoria un PDF por vez.
- `tblParaProcesar` es la única cola operable para PAD/IBM 3270.
- `REVISION_IA` contiene excepciones y `CONTROL` una fila por PDF.
- Las primeras 24 columnas y el orden no cambian; `ID_CASO` permanece al final.
- Los lotes con control reciben `PRESTAMO` de la fila operativa autorizada y
  validada; nunca se infiere del PDF ni del 3270. Los lotes históricos sin
  control pueden conservarlo vacío, pero se derivan a revisión.
- Dirección: registral, luego minuta y finalmente inspección ocular. Terreno
  se clasifica como `CASA`. Una referencia de ubicación no homologada se deriva
  a revisión hasta ampliar `DATOS`; nunca se inventa un código.
- Un dato crítico sin evidencia, código no autorizado o conflicto no entra a
  `PARA_PROCESAR`.
- La IA es excepcional y su resultado se revalida.
- La ruta ZIP heredada no se elimina ni se mezcla con manifiestos hasta una
  aprobación E2E explícita.

## Ciclo mínimo de cambio

1. Delimitar contrato y agregar prueba sintética.
2. Implementar el cambio mínimo en el componente activo.
3. Ejecutar validación de catálogo, suite y `compileall`.
4. Validar XLSX con `tools/verify_workbook.py` cuando corresponda.
5. Actualizar contratos y documentación observable.

No desplegar sin autorización explícita. No guardar PDFs productivos, secretos,
URLs firmadas completas ni contenido documental en Git o logs.

## Límite operativo comprobado: Cloud → PAD

La integración automática Cloud → PAD está validada en `SIMULACION` hasta el
estado local y los reportes del lote. El flujo Cloud filtra exclusivamente
`Resultado_Final_TAS-<ID_LOTE>.xlsx`, entrega solo `IdLote` al Desktop Flow y
PAD ejecuta `run-lot` para ese lote; no se usa un monitor global durante esta
activación.

Conserve estos límites al modificar esta ruta:

- `Main` del Desktop Flow invoca `InicializarLote` y `ValidarExcel` solamente.
  `PrepararRegistros` queda reservado para diagnóstico manual.
- El runtime técnico (estados, locks, logs y reportes) es local y no se mueve a
  OneDrive. Una necesidad de compartir reportes requiere una copia explícita a
  una carpeta de salida dedicada.
- La idempotencia durable `(id_lote, SHA-256)` se mantiene ante eventos o
  reintentos duplicados.
- La integración de VBA, Excel, PCOMM e IBM 3270 está autorizada por el
  responsable para cerrar la presentación. Su evidencia sigue pendiente hasta
  registrar la primera ejecución atendida en BPO; no se declara completa antes
  de esa evidencia.
- La macro heredada no se invoca directamente sobre `Resultado_Final`. Usa un
  esquema posicional distinto y guarda sobre su archivo de entrada. Primero se
  debe diseñar un adaptador con copia local de trabajo, mapeo por encabezados,
  asociación estable entre la fila operativa y el PDF, `PRESTAMO` autorizado y
  trazabilidad por `ID_CASO`.

La plantilla MASIVO revisada después contiene una macro orientada a sus
columnas `A:Y`, pero tampoco es un ejecutable directo del resultado Cloud:
`Y` es su salida de seguro y Cloud usa esa posición para `ID_CASO`. El
adaptador debe crear una copia `.xlsm` local, conservar la trazabilidad fuera
de `A:Y`, exigir un préstamo autorizado de 20 caracteres y eliminar sus
diálogos antes de que PAD pueda usarla.

La evidencia y el procedimiento de diagnóstico están en
[`docs/operacion/e2e-cloud-pad-simulacion-2026-10-13.md`](docs/operacion/e2e-cloud-pad-simulacion-2026-10-13.md).
La ejecución controlada de diez PDFs desde Canvas, con su hoja de control y
PAD en BPO, está registrada en
[`docs/operacion/e2e-control-10-pdfs-2026-10-14.md`](docs/operacion/e2e-control-10-pdfs-2026-10-14.md).
La revisión de las reglas devueltas por Operaciones y de la macro está en
[`docs/operacion/revision-reglas-y-macro-2026-10-13.md`](docs/operacion/revision-reglas-y-macro-2026-10-13.md).
El contrato del último tramo y sus bloqueos están en
[`docs/operacion/contrato-cloud-a-macro-3270-2026-10-14.md`](docs/operacion/contrato-cloud-a-macro-3270-2026-10-14.md).
El flujo corregido desde la entrada del operador hasta la macro está en
[`docs/operacion/flujo-operador-cloud-macro-2026-10-14.md`](docs/operacion/flujo-operador-cloud-macro-2026-10-14.md).
La instalación de la plantilla y el cambio de Desktop Flow para el tramo
final están en
[`docs/operacion/ejecucion-macro-3270-pad-2026-10-14.md`](docs/operacion/ejecucion-macro-3270-pad-2026-10-14.md).
