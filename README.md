# Automatización de tasaciones hipotecarias

Este repositorio extrae información de tasaciones PDF y genera el Excel que
alimenta la automatización IBM 3270. El contrato de salida se conserva:

- `PARA_PROCESAR` / `tblParaProcesar`: única cola para PAD/3270.
- `REVISION_IA` / `tblRevisionIa`: excepciones no operables.
- `CONTROL` / `tblControl`: trazabilidad por PDF.
- `ID_CASO`: llave técnica final de `tblParaProcesar`.

## Arquitectura objetivo masiva

```text
PDFs individuales en OneDrive /auto-tasaciones/PDFs
  -> Power Apps selecciona metadatos
  -> Power Automate carga cada PDF individual a GCS
  -> Cloud Run Job procesa PDFs confirmados uno por uno
  -> Resultado_Final_<ID_LOTE>.xlsx
  -> OneDrive -> Power Automate Desktop -> IBM 3270
```

Un lote admite hasta 300 PDFs y aproximadamente 2 GiB totales. El límite se
aplica a cada PDF, por lo que Power Apps y Power Automate nunca transportan el
lote completo. La arquitectura no usa Microsoft Graph para leer OneDrive.

La descripción operativa está en
[flujo Power Platform de lotes masivos](docs/architecture/flujo-power-platform-lotes-masivos.md).

El estado de despliegue, pruebas y pendientes está en
[estado de implementación](docs/operacion/estado-implementacion-2026-10-07.md).

## Ruta vigente heredada

La ruta ZIP HTTP sigue disponible como **LEGACY / TRANSICIÓN** para lotes de
hasta 90 MB. Cloud Run recibe `application/zip`, genera `Resultado_Final.xlsx`
y Power Automate lo guarda en OneDrive. No se elimina hasta aprobar la ruta
masiva de PDFs individuales.

## Desarrollo

Consulta [cloud-run/README.md](cloud-run/README.md), el
[contrato Excel](contracts/masivo.md), las
[puertas de calidad](docs/QUALITY_GATES.md) y las instrucciones de
[AGENTS.md](AGENTS.md). Los PDFs de clientes, secretos, capturas y resultados
productivos permanecen fuera de Git.
