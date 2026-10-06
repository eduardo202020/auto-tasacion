# Automatización de tasaciones hipotecarias

Repositorio del flujo de tasaciones que recibe informes PDF desde OneDrive,
extrae sus datos en Google Cloud Run y genera el Excel que Power Automate usa
para interactuar con IBM Mainframe 3270.

## Flujo vigente

1. Power Apps ejecuta el flujo `auto-tasacion` de Power Automate.
2. Power Automate obtiene el contenido del archivo ZIP seleccionado desde OneDrive y lo envía por `POST` como
   `application/zip` al endpoint de Cloud Run.
3. Cloud Run procesa cada PDF y devuelve `Resultado_Final.xlsx`.
4. Power Automate guarda ese archivo en OneDrive.
5. Power Automate procesa únicamente la tabla `tblParaProcesar` de la hoja
   `PARA_PROCESAR`.
6. Los casos no resueltos quedan en `REVISION_IA`; la trazabilidad completa
   queda en `CONTROL`.

## Contrato de salida

`Resultado_Final.xlsx` contiene tres hojas, en este orden:

- `PARA_PROCESAR`: tabla `tblParaProcesar` con las 24 columnas de integración
  y la llave técnica final `ID_CASO`. Solo contiene filas completas, validadas
  y aptas para IBM 3270.
- `REVISION_IA`: tabla `tblRevisionIa` con los casos que no pueden operar aún.
  Incluye faltantes, conflicto, evidencia y siguiente acción.
- `CONTROL`: tabla `tblControl`, con una fila por PDF y su ruta final,
  evidencias, correcciones IA y referencia a la fila operable cuando exista.

La revisión IA se invoca únicamente para excepciones y vuelve a validar su
respuesta antes de mover una fila a `PARA_PROCESAR`. Conflictos sin una regla
operativa aprobada nunca se resuelven por inferencia.

## Estructura

```text
auto-tasacion/
├── cloud-run/                 # Servicio Python activo y sus pruebas
│   └── reference-data/         # Catálogos de códigos usados por MASIVO
├── power-platform/             # Contrato de Power Apps y Power Automate
├── contracts/                  # Contratos de salida y reglas de mapeo
├── bank-sim/                   # Simulador IBM 3270 y robot VBA de prueba
├── docs/architecture/          # Arquitectura y decisiones vigentes
└── legacy/google-sheets/       # Flujo Google archivado; no desplegar
```

Los PDFs de clientes, exportaciones, macros originales, capturas, Colabs y
respaldos permanecen fuera de Git en `../contexto-local/`.

## Desarrollo del servicio

Consulta [cloud-run/README.md](cloud-run/README.md) para instalar dependencias,
ejecutar las pruebas y desplegar una versión validada. Antes de publicar, usa
el contrato de [contracts/masivo.md](contracts/masivo.md).

## Harness de desarrollo

El repositorio incluye instrucciones y controles para que personas y agentes
de IA trabajen con el mismo contexto sin redescubrir el flujo en cada sesión:

- [AGENTS.md](AGENTS.md): límites de seguridad e invariantes de desarrollo.
- [Contexto operativo para IA](docs/AI_CONTEXT.md): arquitectura, estados y
  responsables.
- [Entorno local](docs/DEVELOPMENT_ENVIRONMENT.md): preparación, tareas VS
  Code y pruebas sin dependencias corporativas.
- [Puertas de calidad](docs/QUALITY_GATES.md) y
  [runbook de cambio/despliegue](docs/runbooks/CHANGE_AND_DEPLOY.md).
- [Registro de features de perfiles](docs/FEATURES.md): alcance, estado y
  criterios de aceptación para la adaptación a tasadoras.
- [Skills locales](skills/README.md): instrucciones especializadas para Cloud
  Run y para el contrato Excel.

Para comprobar un Excel generado fuera de la suite de pruebas:

```bash
./cloud-run/.venv/bin/python tools/verify_workbook.py /ruta/Resultado_Final.xlsx
```

## Seguridad

- No agregues claves, datos de clientes o capturas productivas al repositorio.
- Power Automate envía el ZIP como binario; el servicio no debe descargar PDFs
  desde enlaces públicos ni guardar credenciales.
- Ningún campo crítico se completa con valores inventados. La IA debe indicar
  valor, página y evidencia, y el resultado debe superar la validación normal.
- La IA se mantiene desactivada por defecto. Antes de habilitarla, usa Secret
  Manager, aprueba el tratamiento de PDFs y configura las reglas operativas.


## ZIP mayores a 30 MiB

Cloud Run rechaza solicitudes HTTP/1 mayores a 32 MiB antes de ejecutar el servicio. Para ZIP de hasta 75 MiB, Power Automate solicita una URL temporal, carga el binario en Cloud Storage privado y env?a a Cloud Run el identificador del objeto. El bucket elimina esos objetos al d?a siguiente.
