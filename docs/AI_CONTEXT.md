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
- `PRESTAMO` puede quedar vacío antes del 3270.
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
