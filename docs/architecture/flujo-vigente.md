# Flujos de tasaciones

## Ruta masiva objetivo

```text
Power Apps (selección de PDFs)
  -> Power Automate (manifiesto y carga por PDF)
  -> API de control / Cloud Storage
  -> Cloud Run Job
  -> Resultado_Final_<ID_LOTE>.xlsx
  -> OneDrive -> PAD / IBM 3270
```

El lote es un manifiesto de PDFs individuales. Power Automate lee OneDrive y
transfiere un PDF por vez. El Job usa únicamente los objetos confirmados y
mantiene las tres hojas contractuales.

## Ruta ZIP heredada

```text
Power Apps / Power Automate
  -> ZIP application/zip o carga temporal firmada
  -> Cloud Run
  -> Resultado_Final.xlsx
```

La ruta ZIP está limitada a 90 MB y permanece como transición hasta aprobar el
E2E de PDFs individuales.
