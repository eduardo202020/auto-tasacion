# Incorporar el Desktop Flow a `autoTasacion`

## Estado de integración

El repositorio contiene el monitor, validador, simulador y pruebas locales. Un
Desktop Flow no se crea de forma soportada mediante una definición fuente que
PAC CLI pueda generar o editar como un Cloud Flow. Por ello este documento deja
el componente preparado para creación manual en la solución existente, sin
afectar los flujos actuales.

La integración solo se considera terminada cuando se vea este objeto en la
solución:

```text
auto-tasacion-procesar-3270-simulado    Tipo: Desktop flow
```

No cree una solución nueva ni use la solución predeterminada.

## Verificación de destino realizada

El 2026-10-12 se realizó una consulta de solo lectura con la sesión PAC activa.
El destino confirmado es el entorno **Personal Productivity [PS1]** y la
solución existente es:

| Campo | Valor |
| --- | --- |
| `solutionid` | `db8ae269-67c2-f111-aaaf-7ced8d92a1ed` |
| Nombre y nombre único | `autoTasacion` |
| Publicador | `JhGLazar` |
| Tipo | No administrada |
| Versión | `1.0.0.0` |

Esta consulta no creó ni modificó objetos remotos. Aún no existe una
verificación remota del Desktop Flow nuevo porque todavía no se ha creado desde
el diseñador dentro de esta solución.

## Verificar el entorno correcto

1. Inicie sesión en `make.powerautomate.com` con la cuenta empresarial que
   posee la solución.
2. Seleccione el mismo entorno donde están `auto-tasacion-iniciar-lote` y los
   demás flujos de tasaciones.
3. Abra **Soluciones** y confirme que existe `autoTasacion`, publicada por
   `JHGLazar` y de tipo **No administrada**.
4. Desde los objetos de esa solución, elija **Nuevo** → **Automatización** →
   **Flujo de escritorio**. La creación desde la solución es la que asocia el
   Desktop Flow al componente de solución correcto.

No cambie variables de entorno, referencias de conexión, Power Apps ni Cloud
Flows existentes.

## Crear el flujo de escritorio

Nombre exacto:

```text
auto-tasacion-procesar-3270-simulado
```

Abra el diseñador PAD que lanza Power Automate. Cree estos subflujos con los
nombres exactos:

1. `InicializarLote`: asigne `RutaConfiguracion` a
   `C:\Users\jhglazar\OneDrive - NTT DATA EMEAL\Escritorio\automatizaciones\auto-tasacion\power-platform\pad\config.development.json`.
2. `ValidarExcel`: use **Ejecutar aplicación** para ejecutar el Python del
   entorno local con:

   ```text
   <repo>\power-platform\pad\.venv\Scripts\python.exe
   "<repo>\power-platform\pad\pad_simulator.py" --config "%RutaConfiguracion%" monitor --once
   ```

   Espere el fin del proceso. Esta acción detecta, estabiliza, copia y valida
   los XLSX; no abre Excel.
3. `PrepararRegistros`: use **Obtener archivos en carpeta** sobre
   `C:\Users\jhglazar\OneDrive - NTT DATA EMEAL\Escritorio\tasaciones\_pad_3270_simulado\estado\pendientes`
   filtrando `*.json`. Conserve la colección de archivos para el siguiente
   subflujo.
4. `SimularOperacion3270`: para cada archivo de esa colección use **Ejecutar
   aplicación** con:

   ```text
   <repo>\power-platform\pad\.venv\Scripts\python.exe
   "<repo>\power-platform\pad\pad_simulator.py" --config "%RutaConfiguracion%" run-job --job "%CurrentItem.FullName%"
   ```

   Seleccione la variable de archivo mediante el selector de variables del
   diseñador. El script reclama el lote antes de procesarlo y escribe solo
   operaciones `ALTA_SEGURO_INMUEBLE_SIMULADA` a `IBM_3270_MOCK`.
5. `RegistrarResultado`: escriba en el registro de PAD el nombre del trabajo
   y su código de salida. Los reportes durables ya los genera el script en
   `resultados/` y `logs/`.
6. `GestionarErrores`: configure el bloque de manejo de errores para registrar
   el nombre del archivo y continuar con el siguiente trabajo. No marque un
   lote exitoso desde PAD: el simulador persiste `ERROR_TECNICO` si su propia
   ejecución falla.
7. `FinalizarLote`: espere cinco segundos antes de la siguiente iteración del
   bucle principal. No use un bucle sin espera.

El flujo principal llama los subflujos en este orden dentro de un bucle:
`InicializarLote` una vez, seguido de
`ValidarExcel → PrepararRegistros → SimularOperacion3270 → RegistrarResultado → GestionarErrores → FinalizarLote`.

No agregue acciones PAD de **Terminal**, **Ejecutar macro de Excel**, PCOMM,
autECL, navegador ni emulación 3270. No configure una conexión de nube para
este piloto: opera en la carpeta local indicada.

Guarde el flujo, vuelva a **Soluciones → autoTasacion → Objetos** y compruebe
que figura como **Desktop flow**. Registre esta comprobación junto con la fecha
y el entorno antes de afirmar que quedó integrado.

## Exportación, versionado e importación posteriores

1. Mantenga versionado este directorio (`power-platform/pad/`) en Git.
2. Después de una modificación manual del flujo PAD, exporte **la solución
   `autoTasacion` completa** desde el portal, como solución no administrada.
3. Guarde el ZIP exportado fuera del repositorio; no se versionan paquetes ni
   credenciales.
4. Para inspección de componentes de solución se puede descomprimir una copia
   con PAC CLI:

   ```powershell
   pac solution unpack --zipfile .\autoTasacion.zip --folder .\solucion-desempaquetada --allowDelete
   ```

5. Para otra instancia, importe ese ZIP desde **Soluciones** o mediante el
   proceso ALM autorizado, mapeando solo las referencias de conexión que el
   componente realmente requiera. Este piloto no requiere referencias nuevas.

PAC se usa para empaquetar, exportar, importar e inspeccionar soluciones; no
reemplaza el guardado/publicación del diseñador de Desktop Flow.
