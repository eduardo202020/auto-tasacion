# Flujo vigente de tasaciones

```text
Power Apps
  → Power Automate
  → OneDrive: auto.zip
  → HTTP POST application/zip
  → Cloud Run: Resultado_Final.xlsx
  → OneDrive: Resultado_Final.xlsx
  → Macro MASIVO / IBM 3270
```

Cloud Run procesa únicamente archivos PDF dentro del ZIP. El servicio genera
dos hojas: `MASIVO`, compatible con la macro, y `CONTROL_EXTRACCION`, destinada
a revisión humana antes de cualquier interacción con IBM 3270.

El flujo anterior de Google Drive, Google Sheets y Apps Script fue archivado
en `legacy/google-sheets`. No comparte endpoint ni contrato con Power Platform.
