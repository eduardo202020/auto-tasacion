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
4. [`cloud-run/README.md`](cloud-run/README.md): servicio y Job.

## Invariantes no negociables

- La ruta masiva recibe manifiestos y PDFs individuales; no usa ZIP, Microsoft
  Graph, `driveId`, GCS FUSE ni un request con el lote completo.
- Power Automate es el único componente que lee contenido de OneDrive.
- El Job solo procesa objetos `CARGADO` y mantiene en memoria un PDF por vez.
- `tblParaProcesar` es la única cola operable para PAD/IBM 3270.
- `REVISION_IA` contiene excepciones y `CONTROL` una fila por PDF.
- Las primeras 24 columnas y el orden no cambian; `ID_CASO` permanece al final.
- `PRESTAMO` puede estar vacío antes del 3270.
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
