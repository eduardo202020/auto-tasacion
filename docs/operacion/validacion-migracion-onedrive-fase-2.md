# Validación de migración OneDrive — fase 2

**Alcance:** revisión local del commit `8930a6a` en
`feature/onedrive-path-migration`. Esta fase no consulta ni cambia Power
Platform, OneDrive, Cloud Run ni Power Apps. No publica, desactiva ni migra
flujos.

## Correcciones incorporadas

### Generador de flujos seguro por defecto

`power-platform/scripts/deploy-mass-flows.ps1` ahora tiene dos modos locales:

- Sin `-Activate`: genera un **Plan** en memoria y termina. No ejecuta MSAL,
  `gcloud`, Secret Manager, Dataverse, `AddSolutionComponent`, `PATCH`, `POST`,
  activación ni desactivación.
- Con `-DryRun`: hace el mismo trabajo con el modo explícito **DryRun**. Es
  incompatible con `-Activate`.

Solo `-Activate` habilita las mutaciones remotas. Por tanto, una ejecución
accidental sin ese parámetro no puede modificar un flujo existente.

El plan usa un marcador de token únicamente en memoria para poder construir
las definiciones sin leer Secret Manager. El marcador no se persiste ni se
imprime dentro de una definición remota.

Ejemplo de inspección local del orquestador:

```powershell
$env:AUTOTASACION_CONTROLS_FOLDER_ID = '<folderId de Controles verificado>'
.\power-platform\scripts\deploy-mass-flows.ps1 -DryRun `
  -FlowName auto-tasacion-orquestar-lote
```

## Auditoría de rutas e IDs

| Concepto | Ruta lógica configurada | Identificador que corresponde | Uso actual |
| --- | --- | --- | --- |
| PDFs | `/automatizaciones-jhglazar/auto-tasaciones/PDFs` | **folderId** para listar la carpeta; cada manifiesto transporta el **Id de archivo** como `item_id` | `$PdfFolderId` se valida como preflight; el generador no lo inserta en una acción nueva. |
| Controles de evento | `/automatizaciones-jhglazar/auto-tasaciones/Controles` | **folderId** de carpeta | `OnNewFilesV2` del orquestador. Cada evento expone `triggerBody()?['Id']`, que es un **Id de archivo** del JSON. |
| Controles históricos | la carpeta PDFs de la ruta histórica/migrada, donde los recurrentes guardaban `_autotasacion_lote_*.json` | **folderId** de esa carpeta, `AUTOTASACION_LEGACY_CONTROLS_FOLDER_ID` | `ListFolderV2` solo en `cargar-lotes` y `entregar-lote`. |
| Archivos | `/automatizaciones-jhglazar/auto-tasaciones/Archivos` | folderId si un componente futuro lo necesita | Declarada en configuración; ningún flujo generado la consume aún. |
| Resultado | raíz `/automatizaciones-jhglazar/auto-tasaciones` | ruta lógica, no folderId en la definición actual | `FindFilesByPath` y `CreateFile`. |

Un valor opaco con formato válido puede ser un ID de archivo o de carpeta. La
validación local solo evita valores vacíos, rutas y formatos claramente
incorrectos. El tipo real se valida con metadata de **la misma conexión
OneDrive para la Empresa**: `IsFolder = true` y `Path` exactamente igual a la
ruta de la tabla.

El generador rechaza que
`AUTOTASACION_CONTROLS_FOLDER_ID` y
`AUTOTASACION_LEGACY_CONTROLS_FOLDER_ID` sean iguales. Esta separación evita
que los dos flujos recurrentes procesen controles del orquestador por evento.

## Consistencia con Cloud Run

La configuración local declara la raíz y `deploy-mass-flows.ps1` deriva de ella
PDFs, Controles, Archivos y destino del XLSX. `batch_lotes.configured_source_folder`
usa esta prioridad efectiva:

1. `BATCH_ALLOWED_SOURCE_FOLDER`, si no está vacía;
2. `AUTOTASACION_ONEDRIVE_BASE_FOLDER + /PDFs`;
3. la raíz versionada por defecto + `/PDFs`.

Por tanto, un `BATCH_ALLOWED_SOURCE_FOLDER` antiguo tiene prioridad y puede
invalidar la migración aunque la raíz nueva sea correcta. Antes de cualquier
Cloud Run autorizado se debe **eliminar** esa variable o fijarla exactamente a:

```text
/automatizaciones-jhglazar/auto-tasaciones/PDFs
```

La prueba de unidad cubre los tres niveles y el caso de override explícito.
La verificación de variables reales de Cloud Run queda pendiente porque no se
realizó ninguna llamada remota en esta fase.

## Inspección remota pendiente, sin modificar componentes

### `auto-tasacion-listar-pdfs`

1. Abrir **Soluciones → autoTasacion → Objetos → auto-tasacion-listar-pdfs**.
2. En modo de solo lectura o **Ver código**, registrar el `operationId`, la
   referencia de conexión y el parámetro de carpeta de la acción que lista.
3. Confirmar que la acción es de **OneDrive para la Empresa**, que apunta a la
   ruta/folderId de `.../PDFs`, y que el filtro conserva solo `.pdf`.
4. Consultar metadata de esa carpeta con la misma conexión; registrar
   `Path`, `Id` y `IsFolder=true`. No guardar valores opacos en Git.

### `autoTasacionJG`

1. Abrir la app desde **Soluciones → autoTasacion** sin guardar ni publicar.
2. En **Datos**, comprobar que `auto-tasacion-listar-pdfs` es la conexión usada
   por **Actualizar** y que `auto-tasacion-iniciar-lote` recibe solo metadatos.
3. Buscar en las fórmulas `'/auto-tasaciones'`,
   `'auto-tasacion-listar-pdfs'.Run` y `'/automatizaciones-jhglazar'`.
4. Registrar el nombre de la referencia de conexión y cualquier ruta
   codificada. Si aparece una ruta antigua, corregirla en una revisión separada
   de Canvas y publicar solo después de una prueba aprobada.

Las fuentes editables de esos dos componentes no están exportadas en este
repositorio. Su estado remoto todavía no puede confirmarse desde Git.

## Aislamiento de flujos heredados

En la definición preparada, el orquestador no tiene recurrencia ni `ListFolderV2`:
recibe un solo control desde `Controles`. Los recurrentes filtran
`_autotasacion_lote_` y solo listan el folderId histórico. No comparten ID de
carpeta, por validación del generador. Antes del despliegue debe comprobarse
que las definiciones remotas actuales tienen esa misma separación; hasta
entonces no se debe afirmar que el entorno ya está aislado.

## PAD en NTTD-MKEY

El perfil `production` declara:

- entrada sincronizada:
  `C:\Users\mailbox_27530\OneDrive - NTT DATA EMEAL\automatizaciones-jhglazar\auto-tasaciones`;
- instalación del paquete:
  `C:\ProgramData\NTT DATA EMEAL\auto-tasacion\pad`;
- runtime aislado:
  `C:\ProgramData\NTT DATA EMEAL\auto-tasacion\pad-runtime`.

En NTTD-MKEY se requieren Windows con Power Automate Desktop, Python 3.13,
permisos de lectura en la carpeta OneDrive, permisos de escritura en
`C:\ProgramData\NTT DATA EMEAL`, sincronización de OneDrive finalizada y
`openpyxl` instalado desde `power-platform\pad\requirements.txt`. El
simulador usa solo biblioteca estándar y `openpyxl`; continúa en modo
`SIMULACION` e `IBM_3270_MOCK`.

Validar localmente en ese equipo, sin usar un Excel operativo:

```powershell
cd C:\ProgramData\NTT DATA EMEAL\auto-tasacion\power-platform\pad
.\Test-AutomationLocations.ps1 -Profile production -CheckLocalPaths
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\Test-PadSimulation.ps1
```

`-CheckLocalPaths` no se ejecutó aquí porque las rutas son exclusivas de
NTTD-MKEY. El paquete se genera con `New-PadSimulationBundle.ps1`; no contiene
PDFs, credenciales, runtime ni resultados.

## Plan reversible de despliegue posterior

1. Exportar o respaldar los `clientdata` de los cinco flujos y registrar sus
   estados antes de cualquier cambio.
2. Ejecutar `-DryRun` con folderIds obtenidos desde metadata y revisar rutas,
   trigger y separación de IDs.
3. Verificar las variables reales de Cloud Run, especialmente el override
   `BATCH_ALLOWED_SOURCE_FOLDER`.
4. Actualizar y publicar únicamente `iniciar-lote` y el orquestador con
   `-Activate`, bajo una autorización separada.
5. Ejecutar un E2E sintético de un PDF. Mantener los recurrentes activos pero
   apuntando solo a controles históricos durante esa prueba.
6. Si falla, desactivar únicamente la ruta nueva, restaurar los `clientdata`
   respaldados y dejar intactos controles, PDFs, resultados y los recurrentes.
7. Solo tras E2E aprobado, decidir en otra autorización si se desactivan los
   recurrentes heredados.
