---
name: tasaciones-cloud-run
description: Mantiene la función Cloud Run de tasaciones al cambiar extracción PDF, validación, catálogos, revisión IA, pruebas o despliegue. Úsala solo para el flujo Microsoft activo, no para Google Sheets legado.
---

# Tasaciones Cloud Run

## Resultado que se protege

El servicio recibe bytes de un ZIP por HTTP y produce un XLSX auditable. La
precisión financiera prima sobre la cobertura: un caso dudoso se deriva a
revisión y no a la operación IBM 3270.

Antes de editar, lee `AGENTS.md`, `docs/AI_CONTEXT.md`,
`cloud-run/README.md` y las pruebas de `cloud-run/tests/`. Para una decisión
que afecte columnas, lee también `contracts/masivo.md` y la skill de contrato
Excel.

## Flujo de cambio

1. Identifica si el cambio es extracción, catálogo, regla operativa, IA o
   integración. No cambies más de una frontera sin una razón explícita.
2. Parte de una prueba sintética reproducible. Para un defecto, escribe una
   regresión que falle antes del arreglo.
3. Conserva la entrada in-memory: `request.get_data(cache=False)` y
   `zipfile.ZipFile(io.BytesIO(...))`. Nunca dependas de un nombre exterior
   como `auto.zip`.
4. Mantén la separación: extracción determinista -> validación/catálogos ->
   revisión IA opcional -> segunda validación -> enrutamiento.
5. Ejecuta la suite completa y, si cambia el resultado, valida el XLSX con
   `tools/verify_workbook.py`.

## Límites de seguridad del dominio

- Solo el catálogo versionado autoriza códigos de tipo, moneda, ubicación y
  clase.
- `REGLA_NEGOCIO_PENDIENTE` es una salida correcta para conflictos sin una
  regla aprobada. No la ocultes con una heurística o IA.
- La IA solo puede proponer campos solicitados con valor, página y evidencia.
  Su salida es no confiable hasta que `apply_ai_corrections` y la validación
  normal la acepten.
- No habilites la IA, cambies secretos ni despliegues sin autorización.
- No uses PDFs productivos como fixtures ni los registres en logs.

## Referencias por necesidad

- Reglas pendientes: `docs/REGLAS_NEGOCIO_PENDIENTES.txt`.
- Reglas aprobadas para IA: `cloud-run/reference-data/reglas_operativas.json`.
- Calidad y publicación: `docs/QUALITY_GATES.md` y
  `docs/runbooks/CHANGE_AND_DEPLOY.md`.
