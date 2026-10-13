# Incorporar el Desktop Flow a `autoTasacion`

## Estado y alcance

El operador informó que ya creó manualmente
`auto-tasacion-procesar-3270-simulado` dentro de la solución no administrada
`autoTasacion`, en **Personal Productivity [PS1]**. Esta guía no vuelve a
consultar ni modifica ese componente remoto.

El Desktop Flow es un invocador local mínimo. La validación del XLSX, la
idempotencia, los bloqueos, el procesamiento de trabajos y los reportes se
mantienen en `pad_simulator.py`; PAD no replica reglas de negocio ni abre IBM
3270, Excel o VBA.

## Configuración local por equipo

Las rutas se declaran en
[`config/automation-locations.json`](../../config/automation-locations.json).
La ruta Cloud de OneDrive y las rutas Windows son conceptos distintos.

| Equipo | Perfil | Entrada local | Runtime local |
| --- | --- | --- | --- |
| Jhunior-pc-auto | `development` | Carpeta compartida `Bbva.bpo` de `auto-tasaciones` | `%LOCALAPPDATA%\NTT DATA EMEAL\auto-tasacion\pad-runtime` |
| NTTD-MKEY | `production` | Carpeta compartida de producción | `C:\ProgramData\NTT DATA EMEAL\auto-tasacion\pad-runtime` |

Desde `power-platform/pad`, genere una configuración local para el perfil del
equipo. No use una carpeta de OneDrive como runtime:

```powershell
.\New-PadSimulationConfig.ps1 -Profile development -OutputPath .\config.local.json
```

`config.local.json`, los estados, locks, logs y resultados técnicos permanecen
fuera de la carpeta compartida. El simulador rechaza de forma explícita una
configuración que ponga el runtime dentro de la entrada OneDrive.

## Acción visual mínima

En `InicializarLote` agregue una única acción **Ejecutar aplicación** que espere
el final del proceso y ejecute el Python del entorno local:

```text
<instalación>\power-platform\pad\.venv\Scripts\python.exe
"<instalación>\power-platform\pad\pad_simulator.py" --config "<instalación>\power-platform\pad\config.local.json" run-cycle
```

`run-cycle` detecta únicamente libros llamados
`Resultado_Final_TAS-<ID_LOTE>.xlsx`, registra los trabajos nuevos y consume
solo los JSON pendientes. La reserva persistida `(id_lote, SHA-256)` impide que
una segunda ejecución haga una operación simulada duplicada. Un estado
`SIMULADO_CON_INCIDENCIAS` es una salida válida de la simulación, no una
conexión bancaria.

La futura automatización de bloques pegables debe partir de un texto copiado
desde la misma versión de PAD; la sintaxis Robin no se inventa ni se aplica sin
esa muestra verificable.

No agregue acciones PAD de **Terminal**, **Ejecutar macro de Excel**, PCOMM,
autECL, navegador o emulación 3270. No configure conexiones de nube en este
piloto.

## Preparar NTTD-MKEY sin Git

En desarrollo, desde un commit revisado, genere un paquete local:

```powershell
.\New-PadSimulationBundle.ps1 -DestinationPath .\artifacts\pad-simulation -Zip
```

El paquete no incluye `.venv`, estados, archivos de entrada, credenciales,
PDFs ni resultados. Copie solo el contenido a la ruta de instalación de
producción, instale Python/dependencias y ejecute el generador con
`-Profile production`. No copie un runtime desde desarrollo.

## Validación local antes de PAD

```powershell
.\Test-AutomationLocations.ps1
.\Test-PadSimulation.ps1
```

Use datos sintéticos. La prueba local con un Excel real solo procede después de
la revisión del operador. El flujo nunca se presenta como integrado hasta que
el usuario confirme que aparece como **Desktop flow** dentro de
**Soluciones → autoTasacion → Objetos**.
