> **Estado historico:** esta auditoria refleja el estado previo al despliegue. Consulte [el cierre de migracion OneDrive](cierre-migracion-onedrive-2026-10-13.md) para el estado operativo final.

# Auditoría remota de la migración OneDrive — 2026-10-13

## Alcance y límites

Esta auditoría contrasta la rama `feature/onedrive-path-migration` con los
componentes remotos mediante consultas de solo lectura. No publicó, desactivó
ni modificó Power Platform, OneDrive, Cloud Run, Power Apps ni datos
operativos. Tampoco se registraron folder IDs, tokens, PDFs ni URLs firmadas.

La ruta objetivo es:

```text
/automatizaciones-jhglazar/auto-tasaciones
├── PDFs
├── Controles
└── Archivos
```

Los resultados se crean en la raíz de ese árbol.

## Matriz de estado comprobado

| Componente | Estado comprobado | Ruta observada o fuente | Acción pendiente |
| --- | --- | --- | --- |
| Git local | `a046cde` en `feature/onedrive-path-migration`, sin cambios locales | configuración y generador locales | Mantener fuera de `main` hasta completar validación y E2E autorizados. |
| GitHub | La misma rama y commit están en `origin`; `main` permanece en `eba6d08` | `git ls-remote` | Abrir revisión/merge solo después del despliegue controlado. |
| Configuración compartida | `config/automation-locations.json` usa la ruta nueva y declara `PDFs`, `Controles` y `Archivos` | repositorio | Correcto localmente. |
| Generador Power Automate | Construye rutas desde la configuración y `-DryRun`/sin `-Activate` no toca recursos remotos | `deploy-mass-flows.ps1` | Desplegar solo los flujos autorizados después de validar folder IDs reales. |
| Cloud Run service `demo-tasaciones-ia` | `BATCH_ALLOWED_SOURCE_FOLDER` sigue en `/auto-tasaciones/PDFs`; no tiene `AUTOTASACION_ONEDRIVE_BASE_FOLDER` | `gcloud run services describe` | Actualizar ambos valores durante un cambio autorizado. La variable explícita tiene prioridad. |
| Cloud Run Job `tasaciones-batch` | No declara ninguna de esas dos variables | `gcloud run jobs describe` | No bloquea la aceptación del manifiesto: esa validación ocurre en el servicio. Mantenerlo sin cambio salvo que el Job llegue a consumir la ruta. |
| `auto-tasacion-iniciar-lote` | Publicado; la definición remota aún crea control y manifiesto bajo `/auto-tasaciones` | `pac power-automate list-cloud-flows` | Publicar definición generada con la ruta nueva. |
| `auto-tasacion-orquestar-lote` | Publicado; conserva `/auto-tasaciones`, aunque usa `OnNewFilesV2` y `splitOn = @triggerBody()` | definición remota leída por PAC | Publicar definición generada con la ruta nueva y el `Wait` corregido. |
| `auto-tasacion-consultar-lote` | Publicado | PAC | Verificar contrato Power Apps; no guarda una ruta OneDrive propia. |
| `auto-tasacion-listar-pdfs` | Publicado | PAC | Inspeccionar en Studio la acción OneDrive y la ruta/folderId efectiva antes de editarlo. |
| `auto-tasacion-cargar-lotes` | Draft | PAC | Conservar sin publicar durante migración; contiene la ruta heredada mientras siga como contingencia. |
| `auto-tasacion-entregar-lote` | Draft | PAC | Conservar sin publicar durante migración; contiene la ruta heredada mientras siga como contingencia. |
| `autoTasacionJG` | Existe, propietario `Bbva.bpo`, modificado el 2026-10-13 | `pac canvas list` | Inspección manual de conexiones y fórmulas; su fuente no está exportada en Git. |
| OneDrive for Business | La conexión usada por la solución está en estado `Connected` para `mailbox_27530` | `pac connection list` | Confirmar la carpeta real y su metadata con esa conexión. |
| OneDrive: `PDFs`, `Controles`, `Archivos` | No comprobable con PAC: PAC no expone navegación de items o metadata de OneDrive | limitación de herramienta | Ejecutar el procedimiento de metadata siguiente, sin copiar los IDs a Git. |

## Diferencia efectiva que bloquea la migración

`batch_lotes.configured_source_folder()` resuelve la carpeta en este orden:

1. `BATCH_ALLOWED_SOURCE_FOLDER`, si contiene valor;
2. `AUTOTASACION_ONEDRIVE_BASE_FOLDER + /PDFs`;
3. el valor por defecto versionado + `/PDFs`.

La configuración remota tiene el primer valor con la ruta antigua. Por eso una
definición nueva de Power Automate enviaría
`/automatizaciones-jhglazar/auto-tasaciones/PDFs` y el backend la rechazaría
hasta actualizar Cloud Run. Cambiar solo la variable base no bastaría.

Además, la definición remota del orquestador conserva el `Wait` antiguo con
`inputs.interval`. El generador local ya usa el contrato válido de Cloud Flow:

```json
{
  "type": "Wait",
  "inputs": {
    "count": "@variables('espera_segundos')",
    "unit": "Second"
  }
}
```

## IDs: qué se debe comprobar

Un identificador opaco de OneDrive no revela por sí solo si representa un
archivo o una carpeta. Usar siempre **la misma conexión OneDrive para la
Empresa** que usará el flujo y comprobar:

| Ruta | Tipo esperado | Uso |
| --- | --- | --- |
| `/automatizaciones-jhglazar/auto-tasaciones/PDFs` | folderId, `IsFolder=true` | preflight de despliegue y listado de PDFs. |
| `/automatizaciones-jhglazar/auto-tasaciones/Controles` | folderId, `IsFolder=true` | trigger `OnNewFilesV2`. |
| carpeta de controles heredados | folderId distinto del anterior | solo los flujos recurrentes heredados. |
| `/automatizaciones-jhglazar/auto-tasaciones/Archivos` | folderId, `IsFolder=true` si se crea y se reserva para uso posterior | todavía no es consumida por los flujos generados. |
| cada PDF o JSON de control | fileId, `IsFolder=false` | metadata, contenido o borrado del archivo individual. |

No guardar esos IDs en archivos versionados, commits, tickets abiertos ni
capturas. Proporcionarlos al proceso de despliegue mediante variables de sesión.

## Procedimiento manual de inspección, sin modificar

### OneDrive

1. Abrir un flujo temporal o una copia no guardada con la conexión **OneDrive
   para la Empresa** de `mailbox_27530`.
2. Agregar **Obtener metadatos de carpeta mediante ruta de acceso** para cada
   ruta de la tabla anterior.
3. Ejecutar una prueba de lectura y registrar en un canal seguro `Id`, `Path`
   e `IsFolder`. El `Path` debe coincidir exactamente, sin una ruta heredada.
4. Eliminar la acción temporal o cerrar sin guardar. No copiar los IDs al
   repositorio.

### `auto-tasacion-listar-pdfs`

1. Ir a **Soluciones → autoTasacion → Objetos → auto-tasacion-listar-pdfs**.
2. Abrir **Ver código** o cada acción de OneDrive sin guardar cambios.
3. Confirmar `shared_onedriveforbusiness`, la ruta o folderId de `PDFs` y el
   filtro exclusivo `.pdf`.
4. Comparar con la metadata de carpeta obtenida arriba. Anotar cualquier
   `/auto-tasaciones` como pendiente de corrección Canvas/Flow.

### `autoTasacionJG`

1. Abrir la app desde la misma solución y no pulsar **Guardar** ni **Publicar**.
2. En **Datos**, comprobar las conexiones de `auto-tasacion-listar-pdfs`,
   `auto-tasacion-iniciar-lote` y `auto-tasacion-consultar-lote`.
3. Buscar en las fórmulas `'/auto-tasaciones'`,
   `'/automatizaciones-jhglazar'`, `auto-tasacion-listar-pdfs`.Run y
   `auto-tasacion-iniciar-lote`.Run.
4. Registrar pantalla, control y fórmula que contengan la ruta antigua. No
   editar durante la inspección.

## Migración reversible propuesta

1. **Preflight.** Obtener los folder IDs reales y ejecutar únicamente:

   ```powershell
   $env:AUTOTASACION_ONEDRIVE_BASE_FOLDER = '/automatizaciones-jhglazar/auto-tasaciones'
   $env:AUTOTASACION_PDFS_FOLDER_ID = '<folderId validado de PDFs>'
   $env:AUTOTASACION_CONTROLS_FOLDER_ID = '<folderId validado de Controles>'
   $env:AUTOTASACION_LEGACY_CONTROLS_FOLDER_ID = '<folderId de controles heredados, distinto>'
   .\power-platform\scripts\deploy-mass-flows.ps1 -DryRun `
     -FlowName auto-tasacion-iniciar-lote,auto-tasacion-orquestar-lote
   ```

   Este comando es local: no inicia sesión, no lee secretos y no cambia un
   flujo remoto.

2. **Respaldo.** Exportar la solución sin gestionar a una ubicación segura,
   externa a Git:

   ```powershell
   pac solution export --name autoTasacion `
     --path 'D:\RespaldoSeguro\autoTasacion-pre-migracion.zip' --overwrite
   ```

3. **Cambio de backend autorizado.** Configurar explícitamente ambos valores
   de Cloud Run a la ruta nueva. No dejar el override antiguo vigente.

4. **Cambio mínimo de flujos autorizado.** Publicar solamente
   `auto-tasacion-iniciar-lote` y `auto-tasacion-orquestar-lote` con
   `-Activate`; no incluir los recurrentes.

   ```powershell
   .\power-platform\scripts\deploy-mass-flows.ps1 -Activate `
     -FlowName auto-tasacion-iniciar-lote,auto-tasacion-orquestar-lote
   ```

5. **Validación posterior.** Leer de nuevo las definiciones remotas y
   comprobar que ambas contienen la nueva raíz, que el trigger apunta al
   folderId de `Controles`, y que el `Wait` tiene `count` y `unit=Second`.

6. **E2E controlado.** Crear un lote sintético de un PDF y confirmar:
   registro, JSON en `Controles`, un solo orquestador, carga GCS, Job, XLSX
   en la raíz nueva y entrega. Mantener los recurrentes en Draft.

7. **Reversión.** Si falla, restaurar el respaldo de la solución y volver los
   dos valores de Cloud Run a los anteriores. No borrar PDFs, controles,
   manifiestos, resultados ni estados de lotes.

## Conclusión operativa

La migración está **implementada y validada localmente**, y su rama ya está en
GitHub; no está desplegada en la ruta nueva. Los componentes publicados siguen
trabajando con `/auto-tasaciones`. Los dos recurrentes heredados están en
Draft, por lo que no procesan controles nuevos mientras se mantengan así.

La única corrección local realizada en esta fase es de trazabilidad: el registro
F20 ya no afirma que la migración se encuentre desplegada. No hubo cambios
remotos ni de Power Apps.
