# Automatización de tasaciones hipotecarias

Repositorio del flujo de tasaciones que recibe informes PDF desde OneDrive,
extrae sus datos en Google Cloud Run y genera el Excel que procesa la macro de
seguros en IBM Mainframe 3270.

## Flujo vigente

1. Power Apps ejecuta el flujo `auto-tasacion` de Power Automate.
2. Power Automate obtiene `auto.zip` desde OneDrive y lo envía por `POST` como
   `application/zip` al endpoint de Cloud Run.
3. Cloud Run procesa cada PDF y devuelve `Resultado_Final.xlsx`.
4. Power Automate guarda ese archivo en OneDrive.
5. La macro utiliza la hoja `MASIVO`; antes de ejecutarla, el operador revisa
   la hoja `CONTROL_EXTRACCION` y completa los campos observados.

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

## Seguridad

- No agregues claves, datos de clientes o capturas productivas al repositorio.
- Power Automate envía el ZIP como binario; el servicio no debe descargar PDFs
  desde enlaces públicos ni guardar credenciales.
- El resultado conserva las ausencias en `CONTROL_EXTRACCION`; ningún campo
  crítico se completa con valores inventados.
