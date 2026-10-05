---
name: tasaciones-contrato-excel
description: Protege el contrato XLSX entre Cloud Run, Power Automate y IBM 3270 al modificar columnas, tablas, rutas de casos o trazabilidad de tasaciones.
---

# Contrato Excel de tasaciones

## Resultado que se protege

El archivo `Resultado_Final.xlsx` contiene exactamente estas hojas, en este
orden: `PARA_PROCESAR`, `REVISION_IA`, `CONTROL`. Power Automate solo opera la
tabla `tblParaProcesar`; las otras dos hojas no son una cola para IBM 3270.

Antes de tocar la salida, lee `AGENTS.md`, `contracts/masivo.md`,
`power-platform/README.md` y `cloud-run/tests/test_service.py`.

## Reglas de compatibilidad

- Las columnas A:X conservan nombres, significado y orden heredados.
- `ID_CASO` queda al final de `tblParaProcesar`; es la llave para relacionar
  la operación posterior con `tblControl`.
- Cada PDF tiene una fila en `tblControl`, incluso cuando falla la extracción.
- Las excepciones permanecen en `tblRevisionIa` con estado, faltantes,
  incidencias, evidencia y siguiente acción.
- `PRESTAMO` es posterior al procesamiento PDF y puede estar vacío en la cola
  lista.
- Una fila con un campo requerido vacío, código no autorizado o conflicto no
  llega a `tblParaProcesar`.

## Procedimiento ante un cambio de contrato

1. Determina si el consumidor Power Automate/PAD necesita cambiar a la vez.
2. Actualiza el contrato y agrega una prueba de encabezados, nombres de tabla,
   orden y enrutamiento.
3. Genera un XLSX sintético y ejecuta `tools/verify_workbook.py`.
4. Documenta la migración en `power-platform/README.md` si el flujo externo
   cambia.
5. No despliegues hasta contar con validación del responsable de integración.

Consulta `docs/runbooks/CHANGE_AND_DEPLOY.md` cuando el cambio cruza el
servicio y Power Automate.
