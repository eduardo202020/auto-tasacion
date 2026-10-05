# Flujo vigente de tasaciones

```text
Power Apps
  → Power Automate
  → OneDrive: archivo ZIP seleccionado
  → HTTP POST application/zip
  → Cloud Run: Resultado_Final.xlsx
  → OneDrive: Resultado_Final.xlsx
  → tabla PARA_PROCESAR / Power Automate Desktop / IBM 3270
```

Cloud Run procesa únicamente archivos PDF dentro del ZIP. El servicio genera
tres hojas: `PARA_PROCESAR`, que contiene exclusivamente casos operables;
`REVISION_IA`, para excepciones no resueltas; y `CONTROL`, para auditoría de
cada PDF. Power Automate solo debe operar la tabla `tblParaProcesar`.

Los campos faltantes pasan por IA solo si la etapa está habilitada y puede
aportar evidencia de página. La respuesta se valida de nuevo antes de mover la
fila. Los conflictos sin una regla operativa aprobada quedan en `REVISION_IA`.

El flujo anterior de Google Drive, Google Sheets y Apps Script fue archivado
en `legacy/google-sheets`. No comparte endpoint ni contrato con Power Platform.


## Ruta para lotes grandes

Cuando el ZIP supera 30 MiB, Power Automate obtiene una URL firmada de Cloud Run, carga el ZIP en el bucket privado y solicita `procesar_carga`. Cloud Run descarga solo el objeto indicado bajo `ingresos/`, mantiene las mismas validaciones y devuelve el mismo XLSX contractual.
