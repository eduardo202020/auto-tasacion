# Inicio automático de IBM 3270 para Auto Tasaciones

## Propósito

Este procedimiento elimina la preparación manual de PCOMM antes de ejecutar el
Desktop Flow. Solo abre la sesión, inicia sesión y deja el terminal listo para
la navegación de consulta de Auto Tasaciones.

La secuencia se obtuvo de un flujo PAD corporativo de referencia y de
`login.png`. Se adapta al destino de Auto Tasaciones:

```text
Abrir PCOMM -> HLLAPI sesión A -> C -> autenticación -> QGTR -> centro 0727
-> pantalla lista -> macro_3270_runner browse-lot
```

No copie estas acciones del flujo de Emisoras:

- `CESN` y su segundo inicio de sesión.
- El centro usado por Emisoras.
- Sus acciones de Teams, PowerShell, limpieza o negocio.
- Valores de usuario o contraseña mostrados en cualquier evidencia.

`NavegarCasosSinCambios` toma la sesión lista, envía `PAUSA`, abre `I003` y
consulta cada préstamo sin escribir datos de tasación.

## Credencial requerida

Antes de editar PAD, cree en Power Automate una credencial de aplicación para
3270, por ejemplo `credencial-3270-autotasaciones`, con el usuario autorizado
para la operación. En PAD use la acción **Obtener credencial** al inicio del
subflujo. Sus valores son sensibles en tiempo de ejecución y no deben aparecer
en Excel, JSON local, PowerShell, capturas, mensajes de Teams ni Git.

Para una cuenta distinta por operador, configure un mapeo de usuario sobre esa
credencial. Consulte [credenciales seguras en PAD](https://learn.microsoft.com/en-us/power-automate/desktop-flows/actions-reference/powerautomatesecretvariables)
y [mapeo de usuario](https://learn.microsoft.com/en-us/power-automate/desktop-flows/create-user-mapping).

## Cambio en el Desktop Flow

En `auto-tasacion-procesar-3270-simulado`, cree el subflujo
`AsegurarSesion3270` y llámelo en `Main` después de `InicializarLote` y antes
de `ValidarExcel`.

```text
InicializarLote
AsegurarSesion3270
ValidarExcel
```

Mantenga `ValidarExcel` con el comando seguro `browse-lot` durante esta etapa.
No cambie a `run-lot`.

## Subflujo `AsegurarSesion3270`

Defina estas variables locales. Las rutas se configuran en BPO y no se
versionan:

| Variable | Valor |
|---|---|
| `Perfil3270` | Perfil `.WS` corporativo de PCOMM de Auto Tasaciones. |
| `Sesion3270` | `A` |
| `CentroAutoTasaciones` | `0727` |
| `Credencial3270` | Resultado de **Obtener credencial**. |
| `TerminalSession` | Resultado de **Abrir sesión de terminal**. |

Use esta secuencia de acciones. Las coordenadas provienen del procedimiento
documentado de inicio de 3270; deben verificarse una vez contra la sesión BPO.

| Paso | Acción PAD | Configuración o resultado esperado |
|---:|---|---|
| 1 | **Obtener credencial** | Recurso `credencial-3270-autotasaciones` hacia `Credencial3270`. |
| 2 | **Ejecutar aplicación** | Abra `Perfil3270`; continúe sin esperar que el proceso termine. PCOMM permanece abierto. |
| 3 | **Abrir sesión de terminal** | Proveedor `HLLAPI`, sesión `A`, adjuntar a sesión en ejecución. Use la DLL y carpeta de instalación de PCOMM de BPO. |
| 4 | **Esperar el texto en la sesión de terminal** | Espere el texto del menú inicial hasta 30 segundos. Si no aparece, termine con `3270_MENU_INICIAL_NO_DISPONIBLE`. |
| 5 | **Mover cursor** / **Establecer texto** / **Enviar tecla** | Fila `24`, columna `24`, escriba `C`, envíe **Transmitir**. |
| 6 | **Esperar el texto en la sesión de terminal** | Espere `INICIO DE SESION DE UN TERMINAL`. |
| 7 | **Mover cursor** / **Establecer texto** | Usuario: fila `4`, columna `34`. Contraseña: fila `5`, columna `34`. Use solo las propiedades sensibles de `Credencial3270`. |
| 8 | **Enviar tecla** / **Esperar texto** | Envíe **Transmitir** y espere la confirmación de terminal conectado. |
| 9 | **Obtener texto** / **Condicional** | Lea la línea de mensaje. Si incluye `BLOQUEA`, publique el error existente de PAD y termine con `3270_USUARIO_BLOQUEADO`. |
| 10 | **Establecer texto** / **Enviar tecla** | Desde la pantalla lista, escriba `QGTR` en la posición inicial y envíe **Transmitir**. |
| 11 | **Esperar texto** | Espere `CAMBIA CENTRO CONTABLE EN TERMINAL`. |
| 12 | **Mover cursor** / **Establecer texto** / **Enviar tecla** | Fila `4`, columna `34`; escriba `%CentroAutoTasaciones%` (`0727`); envíe **Transmitir**. |
| 13 | **Esperar texto** | Espere la pantalla en negro/lista. No envíe transacciones de negocio. |
| 14 | **Cerrar sesión de terminal** | Cierre solamente el manejador HLLAPI de PAD. Deje PCOMM abierto para que Excel/VBA se conecte a la sesión `A`. |

La acción de terminal con HLLAPI requiere que el emulador ya esté abierto; por
eso la apertura del perfil `.WS` precede al adjunto. IBM Personal
Communications usa normalmente `EHLAPI32.dll`; reutilice la ruta comprobada en
BPO, no una ruta inventada. Consulte [la configuración oficial HLLAPI](https://learn.microsoft.com/en-us/power-automate/desktop-flows/how-to/terminal-emulation-open-new-session)
y la [referencia de acciones de terminal](https://learn.microsoft.com/es-es/power-automate/desktop-flows/actions-reference/terminalemulation).

## Reintento e idempotencia de sesión

Antes del paso 2, intente adjuntar HLLAPI a la sesión `A`. Si funciona y la
pantalla contiene el menú inicial, omita la apertura del perfil. Si la sesión
ya está autenticada, continúe desde `QGTR`; no vuelva a enviar `C` ni
credenciales. Limite los intentos de apertura y adjunto a dos; un tercer fallo
termina con `3270_SESION_NO_DISPONIBLE`.

## Evidencia de aceptación

Pruebe primero con PCOMM completamente cerrado y un lote de consulta:

1. Inicie el flujo desde Power Apps.
2. Confirme que PAD abre el perfil, inicia sesión y deja la sesión `A` lista.
3. Mantenga `browse-lot`.
4. Confirme en el JSON del lote `CONSULTADO_SIN_CAMBIOS_3270` y que cada caso
   tenga `CONSULTA_3270_OK`.
5. Confirme que no se modificaron campos de tasación en 3270.

Un error de arranque, autenticación o centro debe terminar el lote con un
código observable y debe activar la alerta de error existente en Teams.
