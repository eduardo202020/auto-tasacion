# Contexto operativo para IA

`auto-tasacion` convierte documentos PDF de tasación en una cola Excel fiable
para Power Automate Desktop e IBM 3270. No opera el Mainframe directamente.

## Rutas de ingreso

- **Masiva objetivo:** PDFs individuales en OneDrive, manifiesto, carga PDF por
  PDF desde Power Automate a GCS y Cloud Run Job.
- **ZIP heredada:** HTTP ZIP o carga temporal firmada de hasta 90 MB; se
  conserva mientras se valida la ruta masiva.

Cloud Run nunca lee OneDrive en la ruta masiva. Power Automate es el único
componente que obtiene su contenido. No se usa Microsoft Graph.

## Invariantes

- `tblParaProcesar` es la única cola para PAD/IBM.
- `REVISION_IA` y `CONTROL` no se usan para operar el banco.
- Los lotes con control reciben `PRESTAMO` desde la fila operativa autorizada;
  se valida como texto de 20 dígitos y nunca se infiere del PDF ni del 3270.
  Los lotes históricos sin control pueden conservarlo vacío, pero se derivan a
  revisión y no quedan listos para la macro.
- Reglas operativas confirmadas el 2026-10-14: dirección registral → minuta →
  inspección ocular; terreno se clasifica como `CASA`; la falta de una
  referencia de ubicación necesaria exige ampliar `DATOS`, sin inventar código.
- Campos críticos sin evidencia, catálogos no autorizados o conflictos quedan
  en revisión.
- La IA es excepcional, aporta evidencia y se revalida.
- El lote masivo no reúne PDFs, no usa Base64 y no carga el lote total en
  memoria.

## Componentes

| Componente | Responsabilidad |
| --- | --- |
| Power Apps | Selecciona metadatos de PDFs y consulta progreso. |
| Power Automate | Valida eTag, carga cada PDF individual y entrega XLSX. |
| `batch_api.py` | Registra manifiesto, tickets, confirmación, estado e inicio. |
| `batch_worker.py` | Procesa solo objetos `CARGADO` de un manifiesto. |
| `service.py` | Comparte clasificación por PDF y mantiene el endpoint ZIP heredado. |
| `contracts/masivo.md` | Define el XLSX estable. |
| `contracts/control-lote.md` | Define la proyección de hoja de control por PDF. |

## Estado operativo comprobado: Cloud → PAD

El 2026-10-13 se validó, en `SIMULACION`, la integración que recibe un
`Resultado_Final_TAS-<ID_LOTE>.xlsx` nuevo en OneDrive, extrae su identificador
en `auto-tasacion-activar-pad`, invoca el Desktop Flow atendido y ejecuta
`run-lot` para ese único lote. La ejecución termina con estado durable y
reportes locales, sin modificar el XLSX de origen.

El runtime técnico es local al equipo de PAD. No se sincronizan estados, locks
ni logs con OneDrive. La simultaneidad del flujo Cloud es uno y la idempotencia
del simulador usa `(id_lote, SHA-256)`. El alcance termina antes de macro, VBA,
Excel interactivo, PCOMM e IBM 3270.

Consulte la evidencia, expresiones lógicas y diagnóstico en
[`operacion/e2e-cloud-pad-simulacion-2026-10-13.md`](operacion/e2e-cloud-pad-simulacion-2026-10-13.md).

## Reglas devueltas y macro heredada

La respuesta del operador contiene cambios explícitos en prioridad de dirección,
clasificación de terreno, condiciones de preparación para macro y valor de
reconstrucción de `CASA`. Algunas filas siguen describiendo preguntas sin una
decisión operativa; no deben convertirse en comportamiento implícito.

La macro heredada fue inspeccionada estáticamente y no es compatible de forma
directa con el resultado Cloud: usa columnas fijas, guarda sobre su entrada y
requiere un préstamo antes de iniciar una consulta. Para una integración futura
se necesita un adaptador con copia local, mapeo por encabezados y correlación
por `ID_CASO`. Los detalles están en
[`operacion/revision-reglas-y-macro-2026-10-13.md`](operacion/revision-reglas-y-macro-2026-10-13.md).

La plantilla MASIVO revisada el 2026-10-14 aclara el contrato del tramo final:
la macro opera `A:Y`, exige un `PRESTAMO` de 20 caracteres y escribe su
resultado en `Y`. Como Cloud usa `Y` para `ID_CASO` y entrega un `.xlsx`, PAD
debe construir una copia local `.xlsm` mediante un adaptador, conservar la
traza fuera de `A:Y` y ejecutar una macro sin diálogos. No se inicia PCOMM ni
VBA hasta incorporar la fila operativa autorizada, relacionarla con el PDF y
resolver los requisitos de la plantilla. Consulte
[`operacion/contrato-cloud-a-macro-3270-2026-10-14.md`](operacion/contrato-cloud-a-macro-3270-2026-10-14.md).
El flujo completo corregido está en
[`operacion/flujo-operador-cloud-macro-2026-10-14.md`](operacion/flujo-operador-cloud-macro-2026-10-14.md).
