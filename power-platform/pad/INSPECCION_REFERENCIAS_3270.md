# Inspección de referencias PAD para inicio de sesión 3270

Use este procedimiento para revisar Desktop Flows existentes antes de reutilizar
su patrón de apertura, autenticación y navegación de IBM 3270.

El inventario es de **solo lectura**: no inicia, ejecuta, publica, exporta ni
modifica ningún flujo.

## Inventario desde la consola BPO

Abra PowerShell en BPO y sitúese en la raíz del repositorio:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\power-platform\scripts\Inspect-DesktopFlows.ps1 `
  -NamePattern '(?i)fuvex|emisoras|leasing' `
  -OutputPath .\artifacts\inspeccion-flujos-3270.json
```

El inicio de sesión de Microsoft que aparezca es únicamente para consultar
Dataverse. El resultado contiene por flujo:

| Campo | Uso |
|---|---|
| `State` | Confirmar si está activado, desactivado o suspendido. |
| `InputVariables` y `OutputVariables` | Identificar el contrato público del flujo. |
| `Signals3270` | Indicadores estáticos de emulador, apertura, teclado, inicio de sesión y esperas/reintentos. No expone sus valores. |

`Signals3270` confirma que el flujo contiene señales relacionadas; no confirma
por sí solo que un inicio de sesión funcione con la sesión actual.

## Obtener las acciones exactas

Para verificar la secuencia que abre PCOMM, espera la pantalla, inicia sesión y
navega, abra cada flujo en PAD y copie el subflujo correspondiente a un archivo
de texto. Power Automate copia también los parámetros, imágenes y elementos de
interfaz del subflujo, por lo que solo debe compartirse después de retirar
usuarios, contraseñas y datos de negocio.

Como alternativa, si el flujo ya pertenece a una solución, exporte una copia
no administrada de esa solución. La exportación es una copia local y permite
revisar su contenido sin ejecutar el flujo. Microsoft documenta ambas opciones:
[copiar acciones o exportar el flujo](https://learn.microsoft.com/en-us/power-automate/desktop-flows/how-to/share-export-desktop-flows).

## Criterios para adoptar el patrón

Extraiga solo componentes reutilizables y sin credenciales:

1. Abrir o adjuntarse al emulador PCOMM.
2. Esperar una pantalla identificable y con límite de tiempo.
3. Autenticarse mediante el mecanismo corporativo permitido, sin textos de
   usuario o contraseña en variables ni en el repositorio.
4. Navegar hasta el menú inicial requerido por Auto Tasaciones.
5. Registrar un estado claro y terminar de forma segura cuando no aparece la
   pantalla esperada.

La secuencia debe adaptarse como un subflujo propio de Auto Tasaciones. No se
ejecuta ni se modifica Fuvex, Emisoras o Leasing durante esta evaluación.
