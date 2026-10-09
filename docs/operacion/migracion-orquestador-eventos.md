# Migracion segura al orquestador por evento

## Estado

Esta guia describe el orden de despliegue de la ruta nueva. No autoriza ni
ejecuta un despliegue por si misma. `auto-tasacion-cargar-lotes` y
`auto-tasacion-entregar-lote` se mantienen activos durante la validacion para
que la vuelta atras sea directa.

## Preparacion

1. Crear `/auto-tasaciones/Controles` en la misma cuenta de OneDrive que usa la
   referencia de conexion `OneDrive para la Empresa`.
2. Obtener el identificador de la carpeta con el selector del conector y
   guardarlo localmente como `AUTOTASACION_CONTROLS_FOLDER_ID`. No registrar
   ese identificador en archivos versionados si es corporativo.
3. Confirmar que la carpeta contiene solo controles del sistema. El trigger
   `OnNewFilesV2` no filtra por nombre antes de arrancar una ejecucion.
4. Ejecutar las pruebas locales indicadas en la seccion de validacion antes de
   abrir la sesion de despliegue.

## Comandos propuestos

Desde la raiz del repositorio, con autenticacion corporativa ya aprobada:

```powershell
# Backend: servicio y proyecto actualmente configurados para este repositorio.
# Se invoca gcloud.cmd para evitar la pol?tica local que bloquea gcloud.ps1.
& 'C:\Users\jhglazar\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' run deploy demo-tasaciones-ia `
  --source .\cloud-run `
  --project project-fe2e4c6a-b528-4bcf-aa1 `
  --region northamerica-northeast1

# Flujos: solo despues de comprobar que el backend nuevo responde.
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$env:AUTOTASACION_CONTROLS_FOLDER_ID = '<ID de /auto-tasaciones/Controles>'
.\power-platform\scripts\deploy-mass-flows.ps1 -Activate `
  -FlowName auto-tasacion-iniciar-lote,auto-tasacion-orquestar-lote
```

La configuracion de Cloud Run debe conservar los valores actuales de
`BATCH_STATE_BUCKET`, `BATCH_STORAGE_BUCKET`, `BATCH_SIGNING_SERVICE_ACCOUNT`,
`BATCH_JOB_NAME`, `BATCH_JOB_REGION`, `BATCH_CONTROL_API_TOKEN` y agregar,
solo si se desea cambiar el valor por defecto, `BATCH_ORCHESTRATION_LEASE_SECONDS=10800`.

## Orden de migracion

1. Desplegar el backend compatible: los endpoints de claim son aditivos y no
   cambian los contratos de los flujos recurrentes.
2. Crear y publicar el orquestador nuevo, inicialmente sin seleccionar PDFs.
3. Publicar `auto-tasacion-iniciar-lote` para que cree los nuevos controles en
   `/auto-tasaciones/Controles`.
4. Ejecutar el E2E de un PDF. Revisar el historial del nuevo orquestador y el
   manifiesto del lote, no los flujos recurrentes.
5. Repetir con varios PDFs y un evento duplicado del mismo control.
6. Cuando los criterios E2E esten aprobados, desactivar primero
   `auto-tasacion-cargar-lotes` y despues `auto-tasacion-entregar-lote` en una
   ventana controlada. No eliminarlos hasta completar la observacion acordada.

## Reversion y recuperacion

Si el orquestador falla antes de `ENTREGADO`, el control queda en
`/auto-tasaciones/Controles` y el manifiesto conserva fase, intentos y ultimo
error. Si la ca?da ocurre despu?s de confirmar `ENTREGADO` pero antes de borrar
el control, un evento duplicado solo elimina ese control residual; no vuelve a
subir PDFs, iniciar un Job ni crear el XLSX. Un timeout de espera libera el claim y registra `REINTENTO_REQUERIDO`
sin demoler estados de negocio. Para reintentar manualmente, borrar y recrear
el mismo control con solo `{"id_lote":"<ID_LOTE>"}`; mover un archivo no sirve,
porque OneDrive no considera un movimiento como una creacion.

Si debe detenerse la ruta nueva, desactivar solo
`auto-tasacion-orquestar-lote` y volver a crear el control del lote en la
carpeta antigua para que los flujos recurrentes existentes lo procesen. No se
debe ejecutar ambos mecanismos sobre el mismo JSON.

## Validacion local

```powershell
& .\cloud-run\.venv\Scripts\python.exe -m unittest discover -s cloud-run\tests -v
python -m unittest power-platform.tests.test_mass_flow_definitions -v
& .\cloud-run\.venv\Scripts\python.exe .\tools\validate_profile_catalog.py
& .\cloud-run\.venv\Scripts\python.exe -m compileall -q cloud-run tools
```

El plan E2E detallado esta en
[`prueba-e2e-lotes-masivos.md`](prueba-e2e-lotes-masivos.md).
