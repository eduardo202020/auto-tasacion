# Análisis estático de la macro de seguros inmuebles

Fuente revisada de forma estática el 2026-10-12:

```text
C:\Users\jhglazar\Downloads\MACRO DE VALIDACION DE SEGUROS INMUEBLES V.2 1.xlsm
```

La revisión no abrió Excel, no ejecutó VBA y no inició un emulador de terminal.
La macro permanece intacta.

## Hallazgos de estructura

Se identificaron módulos de conexión, validación, descarga, limpieza y
plantillas. Entre sus procedimientos están los orquestadores masivos de
tasaciones/validación y rutinas de conexión y espera de host. El análisis
encontró referencias textuales a `PCOMM`, `autECL`, `Terminal`, `CreateObject`
y `Shell`.

Esas referencias confirman que la macro es una fuente útil para entender la
integración bancaria futura, pero no se importan, copian ni ejecutan en este
piloto. El componente nuevo conserva el límite operativo:

```text
ALTA_SEGURO_INMUEBLE_SIMULADA → IBM_3270_MOCK
```

## Revisión de compatibilidad con el resultado Cloud

El 2026-10-13 se inspeccionó una segunda copia de la macro en modo lectura. El
resultado confirma que no es un ejecutable directo de
`Resultado_Final_<ID_LOTE>.xlsx`: los procedimientos trabajan sobre la hoja
activa o sobre la primera hoja de un archivo elegido con diálogo, usan
posiciones fijas y guardan el archivo de entrada. Las consultas de terminal
además requieren que el préstamo ya esté disponible.

`PARA_PROCESAR` usa un contrato distinto: `PRESTAMO` se ubica en la columna A,
la correlación se mantiene con `ID_CASO` y el flujo Cloud puede entregarlo
vacío. La integración futura requiere un adaptador que copie el libro a un
directorio local de trabajo, haga mapeo por encabezados y publique una salida
separada. No se debe automatizar el diálogo ni ejecutar el procedimiento
heredado contra el archivo sincronizado de OneDrive.

La revisión también encontró definiciones públicas repetidas de la función de
conexión en módulos distintos. El proyecto VBA debe consolidarlas y compilarse
antes de cualquier integración. Consulte la decisión completa en
[`../../docs/operacion/revision-reglas-y-macro-2026-10-13.md`](../../docs/operacion/revision-reglas-y-macro-2026-10-13.md).

## Contrato de entrada observado

La muestra
`Resultado_Final_TAS-B1D346E63F59FE57587D.xlsx` fue inspeccionada en modo
lectura. Tiene las hojas `PARA_PROCESAR`, `REVISION_IA` y `CONTROL`, con las
tablas `tblParaProcesar`, `tblRevisionIa` y `tblControl`. La primera tabla
mantiene los encabezados definidos en `tools/verify_workbook.py`.

El piloto toma ese contrato versionado como fuente de verdad. No interpreta
instrucciones ni lógica implícita dentro de la macro como un permiso para usar
PCOMM, macros, automatización de Excel o conexiones bancarias.

## Siguiente paso para una integración real

Cuando exista autorización específica, se debe traducir cada acción bancaria
revisada y aprobada a acciones PAD trazables, con una máquina registrada,
conexión controlada, credenciales administradas y pruebas en entorno no
productivo. Ese trabajo no forma parte de esta entrega.
