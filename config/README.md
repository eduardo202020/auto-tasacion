# Ubicaciones operativas de `auto-tasacion`

Este archivo es la fuente local de verdad para las rutas de la automatización.
No contiene credenciales ni IDs de OneDrive: los IDs son opacos, pueden
sobrevivir a un movimiento y se validan antes del despliegue con la conexión
real.

## Espacios separados

| Concepto | Configuración | Uso |
| --- | --- | --- |
| Ruta lógica OneDrive | `onedrive.base_folder` y `subfolders` | Power Automate y la API de manifiestos. |
| Carpeta local de entrada | `pad.profiles.<perfil>.input_directory` | Solo detecta `Resultado_Final_<ID_LOTE>.xlsx`. |
| Instalación local PAD/Python | `pad.profiles.<perfil>.install_directory` | Código desplegado localmente. |
| Runtime local PAD | `pad.profiles.<perfil>.runtime_directory` | Estados, locks, logs y resultados técnicos. Nunca es hijo de la carpeta OneDrive compartida. |

El resultado final se entrega en `onedrive.result_folder`, que debe ser igual a
la raíz lógica de la automatización. Las subcarpetas se deben expresar como un
solo nombre; los scripts rechazan rutas relativas, `..` y valores vacíos.

## IDs de OneDrive

No registre IDs opacos en Git. Antes de desplegar se deben proporcionar:

```powershell
$env:AUTOTASACION_PDFS_FOLDER_ID = '<ID verificado de .../PDFs>'
$env:AUTOTASACION_CONTROLS_FOLDER_ID = '<ID verificado de .../Controles>'
# Solo mientras sigan activos los flujos recurrentes heredados:
$env:AUTOTASACION_LEGACY_CONTROLS_FOLDER_ID = '<ID de los controles heredados>'
```

La migración no debe asumir que el ID de una carpeta cambió ni que permaneció
igual después del movimiento. El procedimiento de verificación está en
[`docs/operacion/migracion-rutas-onedrive.md`](../docs/operacion/migracion-rutas-onedrive.md).
