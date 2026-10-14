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

## Integración automática Cloud → PAD por `ID_LOTE`

La integración no usa un monitor global ni un bucle PAD. El Cloud Flow que
recibe la creación de `Resultado_Final_<ID_LOTE>.xlsx` entrega únicamente el
identificador del lote al Desktop Flow. PAD espera la sincronización de ese
archivo, valida el contrato y lo procesa de manera idempotente.

1. En la ventana **Variables** de PAD, cree una variable de **entrada**:
   - nombre: `IdLote`;
   - tipo: `Texto`;
   - valor predeterminado: vacío.
2. Mantenga `InicializarLote` para cargar `RutaConfiguracion`.
3. En `ValidarExcel`, reemplace el comando global `monitor --once` por:

   ```text
   "<instalación>\power-platform\pad\pad_simulator.py" --config "%RutaConfiguracion%" run-lot --lot "%IdLote%"
   ```

   La ruta de la aplicación sigue siendo el `python.exe` del entorno virtual
   local. Configure **Esperar a que finalice la aplicación**.
4. En `Main`, deje solo `InicializarLote` seguido por `ValidarExcel`. No llame
   `PrepararRegistros`: ese subflujo procesa todos los JSON pendientes y no es
   válido para la activación automática por lote.
5. Guarde y publique el Desktop Flow. El diseñador Cloud mostrará `IdLote`
   como parámetro de la acción **Ejecutar un flujo creado con Power Automate
   para escritorio**.

El Cloud Flow se debe activar solo para el nombre esperado, obtener el lote
con `replace(replace(<Nombre>, 'Resultado_Final_', ''), '.xlsx', '')` y pasar
ese valor a `IdLote`. La carpeta de entrada requiere el folderId de la raíz
de resultados; ese ID se suministra en el despliegue, no se versiona en Git.

`run-lot` espera hasta diez minutos a la sincronización de OneDrive. Una
ausencia, archivo aún copiándose, cambio de origen o fallo técnico termina la
ejecución con error observable. Los estados terminales de validación y una
reinvocación idempotente no reprocesan registros.

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
