# Evidencia E2E: hoja de control, Cloud y PAD para diez PDFs

**Fecha:** 2026-10-14  
**Estado:** completado en modo `SIMULACION`, con revisiones documentales

## Alcance ejecutado

Se ejecutó un lote controlado de diez PDFs desde la Canvas App. Cada PDF se
relacionó con una fila de `tblControlLote` que aportó el préstamo de veinte
dígitos y la moneda operativa. La ruta comprobada fue:

```mermaid
flowchart LR
    A[PDFs + tblControlLote] --> B[Canvas App]
    B --> C[auto-tasacion-iniciar-lote]
    C --> D[Cloud Run Job]
    D --> E[Resultado_Final_TAS-<ID_LOTE>.xlsx en OneDrive]
    E --> F[auto-tasacion-activar-pad]
    F --> G[PAD run-lot]
    G --> H[Reportes locales de simulación]
```

La Canvas App alcanzó `ENTREGADO` en 1 minuto y 47 segundos. El resultado
Cloud creó las tres hojas contractuales y PAD fue activado por el archivo
final sincronizado en BPO.

## Evidencia verificada

| Elemento | Resultado |
| --- | --- |
| PDFs recibidos | 10 |
| Filas `CONTROL` | 10 |
| Filas `PARA_PROCESAR` | 4 |
| Filas `REVISION_IA` | 6 |
| Operaciones PAD simuladas | 4 |
| Revisiones de IA simuladas | 6 |
| Revisiones manuales | 0 |
| Errores técnicos PAD | 0 |
| Estado de PAD | `SIMULADO_CON_INCIDENCIAS` |

El archivo entregado conserva las tablas `tblParaProcesar`, `tblRevisionIa` y
`tblControl`. El reporte de validación no encontró incidencias estructurales en
los cuatro registros enviados a PAD.

Los reportes locales de BPO quedaron bajo:

```text
C:\ProgramData\NTT DATA EMEAL\auto-tasacion\pad-runtime\resultados
```

## Corrección aplicada durante la prueba

El primer registro con control falló antes de crear el lote por una operación
de conjuntos incompatible con la tupla de campos permitidos. Se corrigió la
validación de campos de control y se desplegó la revisión de Cloud Run. Los
commits locales asociados son `86c5d9f` y `f1db7dc`.

## Límite confirmado

Esta ejecución valida el tramo hasta los reportes locales de PAD. No ejecuta
la macro heredada, Excel interactivo, PCOMM ni IBM 3270. Los seis registros de
`REVISION_IA` se deben revisar y resolver antes de diseñar el adaptador que
construirá la copia local `.xlsm` para la macro.
