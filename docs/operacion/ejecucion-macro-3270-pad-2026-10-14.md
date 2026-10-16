# Ejecución final PAD: Resultado_Final -> MASIVO -> PCOMM 3270

**Actualización validada en PBO:** 2026-10-15
**Estado:** navegación segura por préstamos validada; la ejecución transaccional
permanece deshabilitada.

## Alcance

La ruta conserva el Excel de Cloud y trabaja en una copia local de una plantilla
`.xlsm` aprobada. Solo toma las filas de `PARA_PROCESAR`; `REVISION_IA` queda en
el Excel de origen para atención posterior.

```mermaid
flowchart LR
    A[Resultado_Final XLSX] --> B[Desktop Flow PAD]
    B --> C[AsegurarSesion3270]
    C --> D[PCOMM abierto / sesión A lista]
    D --> E[macro_3270_runner.py browse-lot]
    E --> F[Copia local MASIVO XLSM]
    F --> G[Excel VBA adjunta sesión A]
    G --> H[TRAZA_PAD + resultado local]
```

`browse-lot` ejecuta la consulta segura `PAUSA -> I003 -> opción 01 -> préstamo
-> ENTER`, valida `ICA9783`, guarda evidencia local y retorna con `PAUSA`. No
usa `FIN`, `F4`, `F8`, importe, dirección, seguro ni otro campo de negocio.
`run-lot` es el único modo transaccional y sigue fuera del alcance.

## Componentes versionados

- `macro_3270_runner.py` prepara la copia local, llena la plantilla por contrato
  y mantiene estado bajo `estado\macro_3270` para evitar duplicados.
- `vba\AutoTasacion3270.bas` contiene validación de sesión, navegación segura y
  el procedimiento transaccional histórico, con traza estructurada.
- `config.macro-3270.example.json` se copia como configuración local no
  versionada.
- `requirements-macro-3270.txt` declara la dependencia COM de Excel.

## Preparación única en BPO

1. Preparar la plantilla `.xlsm`, importar `AutoTasacion3270.bas` y guardar una
   copia local aprobada.
2. Instalar `pywin32` en el mismo Python que invoca PAD.
3. Crear `config.macro-3270.local.json` desde el ejemplo y completar solo rutas
   locales del entorno; no incorporarlo a Git.
4. Agregar la carpeta local de trabajo de PAD como ubicación de confianza de
   Excel.
5. Verificar que PCOMM, el perfil `.WS` y la biblioteca HLLAPI estén disponibles
   para la cuenta que ejecuta PAD.

## Estructura del Desktop Flow

Mantener `Main` con exactamente estos dos llamados:

```text
InicializarLote
ValidarExcel
```

`ValidarExcel` realiza, en este orden:

```text
AsegurarSesion3270
cmd.exe /d /c ... macro_3270_runner.py --config "%RutaConfiguracion%" browse-lot --lot "%IdLote%"
```

No llame `AsegurarSesion3270` también desde `Main`. La preparación abre PCOMM,
autentica, selecciona el centro y cierra solo `TerminalSession` de PAD. Excel
VBA queda libre para adjuntarse a la sesión A mediante `CONEXION.Init "A"`.

La secuencia operativa de login está documentada en
[`AUTO_TASACION_LOGIN_3270.md`](../../power-platform/pad/AUTO_TASACION_LOGIN_3270.md).

## Inicio automático desde PCOMM cerrado

1. Cloud entrega `Resultado_Final_TAS-<LOTE>.xlsx` y activa PAD con `IdLote`.
2. `AsegurarSesion3270` abre el perfil PCOMM, espera su disponibilidad y se
   adjunta a HLLAPI sesión `A`.
3. El subflujo autentica, limpia el contexto de terminal, envía `qgtr`, espera
   `BXA0147`, confirma con `Clear` y escribe `0727` en el cursor que deja el
   host.
4. PAD libera HLLAPI sin cerrar PCOMM.
5. `browse-lot` ejecuta la consulta segura sobre cada fila elegible y publica la
   copia `.xlsm` si la salida está disponible.

No mover el cursor a 1/1 antes de `qgtr` ni a 4/34 antes de escribir el centro:
las pruebas PBO mostraron que esas acciones llevan a un campo no editable.

## Evidencia confirmada

Se validó primero la lectura de sesión, después la apertura de I003 y finalmente
la consulta por préstamo. La última evidencia segura confirmó:

| Campo | Resultado |
| --- | --- |
| Estado durable | `CONSULTADO_SIN_CAMBIOS_3270` |
| Modo | `CONSULTA` |
| Filas elegibles del lote probado | 4 |
| Resultado por fila | `CONSULTA_3270_OK` / `ICA9783_SEGURO_TIPO_I` |
| Error técnico | vacío |

La nueva preparación automática añade a esa cadena que PCOMM puede partir
cerrado, abrirse y quedar listo sin preparación manual. Su aceptación E2E exige
que el mismo `browse-lot` vuelva a adjuntarse después de que PAD libere HLLAPI.

## Pendientes de operación

- Migrar la contraseña temporal de Excel compartido a un almacén de credenciales
  seguro.
- Hacer que la rama de usuario bloqueado devuelva un estado técnico de error,
  no código 0.
- Habilitar y validar las acciones Teams de login que siguen deshabilitadas en
  el Robin.
- Confirmar que la alerta final de PAD recibe estado y mensaje no vacíos.

La ejecución transaccional requiere una autorización posterior y explícita.
