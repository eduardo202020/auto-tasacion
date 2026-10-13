# Migración de rutas OneDrive — `auto-tasacion`

Este documento prepara la migración; no publica ni altera un componente remoto.
La configuración versionada está en
[`config/automation-locations.json`](../../config/automation-locations.json).

## Ubicaciones

| Concepto | Antes | Preparado para la migración |
| --- | --- | --- |
| Raíz lógica OneDrive | `/auto-tasaciones` | `/automatizaciones-jhglazar/auto-tasaciones` |
| PDFs | `/auto-tasaciones/PDFs` | `/automatizaciones-jhglazar/auto-tasaciones/PDFs` |
| Controles nuevos | `/auto-tasaciones/Controles` | `/automatizaciones-jhglazar/auto-tasaciones/Controles` |
| Archivos | `/auto-tasaciones/Archivos` | `/automatizaciones-jhglazar/auto-tasaciones/Archivos` |
| Resultado XLSX | raíz anterior | raíz nueva, `Resultado_Final_<ID_LOTE>.xlsx` |
| Entrada PAD desarrollo | escritorio local anterior | carpeta compartida de `Bbva.bpo` indicada en el perfil `development` |
| Entrada PAD producción | no declarada | perfil `production` de NTTD-MKEY |
| Runtime PAD | dentro de la carpeta de entrada | `%LOCALAPPDATA%` en desarrollo y `C:\ProgramData` en producción |

Las rutas de Windows no son rutas de OneDrive Cloud. Power Automate usa solo las
rutas lógicas. PAD/Python usa solo la ruta local de entrada y su runtime local.

## Inventario afectado

| Componente | Cambio preparado | Aplicación remota |
| --- | --- | --- |
| `deploy-mass-flows.ps1` | Lee la raíz y subcarpetas desde la configuración; entrega XLSX en la misma raíz. | Requiere despliegue autorizado. |
| `auto-tasacion-iniciar-lote` | Creará controles bajo la nueva ruta al regenerar la definición. | Requiere despliegue autorizado. |
| `auto-tasacion-orquestar-lote` | Trigger y lectura usan controles de la nueva ruta, con ID verificado. | Requiere despliegue autorizado. |
| Flujos recurrentes heredados | Exigen un ID propio para sus controles históricos; no se les asigna el ID nuevo por omisión. | No se modifican hasta una decisión de migración. |
| Cloud Run `batch_lotes.py` | Deriva `<raíz>/PDFs` o conserva un override explícito. | Requiere actualizar variables y desplegar autorizado. |
| `auto-tasacion-listar-pdfs` | No tiene fuente exportada en este repositorio; debe verificarse en la interfaz. | Acción manual requerida. |
| `autoTasacionJG` | No hay fuentes Canvas editables con rutas en este repositorio; conserva el contrato de metadatos. | Solo verificar la conexión del flujo de listado. |
| PAD/Python | Perfiles de entrada y runtime separados; se rechaza runtime dentro de OneDrive compartido. | Instalación local manual en cada equipo. |

Los documentos fechados que describen la ruta anterior son evidencia histórica;
no prueban la ubicación actualmente desplegada.

## Verificar IDs reales sin suponer cambios

Con la **misma conexión `OneDrive para la Empresa` de `Bbva.bpo`** que usan los
flujos, cree temporalmente acciones de solo lectura en Power Automate:

1. **Obtener metadatos de archivo mediante ruta de acceso** para un PDF real de
   `/automatizaciones-jhglazar/auto-tasaciones/PDFs`. Anote `Id` y confirme
   `Path`.
2. **Mostrar los archivos de la carpeta** sobre
   `/automatizaciones-jhglazar/auto-tasaciones/Controles`. En la salida de la
   acción, anote el `folderId` opaco configurado por el diseñador y confirme la
   ruta mostrada por metadata.
3. Repita para `Archivos` si algún flujo futuro la utiliza.
4. Compare el `Id` de PDFs y el `folderId` de Controles con los valores previos.
   Un movimiento puede conservarlos; solo la metadata actual demuestra el
   mapeo. No deduzca la relación por el nombre de la carpeta.
5. Si los flujos recurrentes siguen activos, obtenga además el ID de la carpeta
   que contiene **sus controles históricos**. No use el ID nuevo de Controles
   para esos flujos.

Luego, solo durante el despliegue autorizado, cargue los valores en la sesión:

```powershell
$env:AUTOTASACION_ONEDRIVE_BASE_FOLDER = '/automatizaciones-jhglazar/auto-tasaciones'
$env:AUTOTASACION_PDFS_FOLDER_ID = '<ID verificado de PDFs>'
$env:AUTOTASACION_CONTROLS_FOLDER_ID = '<ID verificado de Controles>'
$env:AUTOTASACION_LEGACY_CONTROLS_FOLDER_ID = '<ID histórico; solo para recurrentes>'
```

El generador valida que un ID requerido no esté vacío ni parezca una ruta. No
puede demostrar desde código local que un ID remoto apunta a una carpeta:
la comprobación de metadata anterior es obligatoria.

Antes de autenticarse o modificar Dataverse, se puede comprobar que los valores
de la sesión están presentes y tienen formato de ID opaco:

```powershell
.\power-platform\scripts\deploy-mass-flows.ps1 -ValidateOneDriveFolderIds
```

Esta comprobación es local y deliberadamente informa
`RemoteMappingVerified = False`: la validación de metadata del paso anterior es
la única que confirma la correspondencia ID/ruta.

## Orden de migración seguro

1. En desarrollo, ejecutar las pruebas y `Test-AutomationLocations.ps1`.
2. En Power Automate, verificar la conexión y obtener los IDs con metadata.
3. Configurar en Cloud Run, todavía sin desplegar, `AUTOTASACION_ONEDRIVE_BASE_FOLDER`
   y `BATCH_ALLOWED_SOURCE_FOLDER` con la nueva ruta de PDFs.
4. Generar un plan local con `-DryRun` para `auto-tasacion-iniciar-lote` y
   `auto-tasacion-orquestar-lote`; inspeccionar rutas y trigger. Sin
   `-Activate`, el script no autentica ni modifica un flujo remoto.
5. Publicar ambos componentes solo tras autorización y realizar un lote
   sintético de un PDF en la nueva carpeta.
6. Verificar control, carga individual, Job, XLSX en la raíz nueva y entrega.
7. Repetir con varios PDFs y un evento duplicado.
8. Solo después de una revisión, desactivar los recurrentes heredados o
   actualizar su carpeta histórica de controles de manera explícita.

## Reversión

1. Detener la activación de las definiciones nuevas antes de crear otro lote.
2. Restaurar las variables de Cloud Run al valor anterior y redeplegar solo con
   autorización.
3. Reactivar la definición anterior de `iniciar-lote`/orquestador desde la
   solución exportada antes de la migración.
4. Mantener controles antiguos y resultados intactos; no mover ni borrar JSON
   pendientes durante la reversión.
5. Usar los recurrentes solo con el ID histórico confirmado.

## PAD sin Git en NTTD-MKEY

Desde desarrollo se puede generar una copia revisable y sin datos operativos:

```powershell
.\power-platform\pad\New-PadSimulationBundle.ps1 `
  -DestinationPath .\artifacts\pad-simulation-<commit> -Zip
```

El paquete conserva la estructura que necesita `pad_simulator.py` para cargar
`tools/verify_workbook.py`. En NTTD-MKEY se instala desde ese paquete, se genera
`config.local.json` con el perfil `production` y se valida con datos sintéticos.
No se instala Git, no se copian PDFs y no se comparten estados o logs entre
máquinas.


La validacion detallada de la segunda fase, incluidos los IDs de archivo frente a
folderIds, la prioridad de `BATCH_ALLOWED_SOURCE_FOLDER`, el aislamiento de los
recurrentes y el procedimiento de inspeccion de Canvas esta en
[`validacion-migracion-onedrive-fase-2.md`](validacion-migracion-onedrive-fase-2.md).
