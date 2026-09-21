# Automatizaciones hipotecarias — Tasaciones

Repositorio privado para las automatizaciones operativas de Hipotecas. El
primer módulo, `tasaciones`, recibe PDFs de tasación desde Google Drive,
extrae sus campos estructurados en Cloud Run y presenta el resultado en Google
Sheets para revisión y exportación a Excel.

## Estructura

```text
auto-tasacion/
├── tasaciones/                 # Código ejecutable del módulo
│   ├── appscript/              # Interfaz y orquestación de Google Sheets
│   ├── funcions/               # Endpoint Python desplegable en Cloud Run
│   ├── package.json            # Comandos de desarrollo para clasp
│   └── README.local.md         # Detalle de ejecución local
└── _referencias_locales/       # Excluido por Git: PDFs, macros y material histórico
```

No se suben al repositorio PDFs de clientes, documentos de negocio, archivos
Excel con macros, Colabs heredados, claves, entornos virtuales ni dependencias
instaladas.

## Flujo funcional

1. El operador carga los PDFs en la carpeta de Google Drive autorizada.
2. Desde el menú de Google Sheets, ejecuta **Escanear PDFs**.
3. Apps Script envía los identificadores de archivo al endpoint de Cloud Run.
4. Python extrae 25 campos: dirección, tipo de inmueble, valores comercial y
   de reconstrucción en US$/S/, año, pisos, sótanos, páginas de evidencia y
   observaciones.
5. Los casos completos pasan a **Listos para el Banco**; los incompletos a
   **Bandeja de Revisión**.
6. El menú genera un archivo Excel de los casos validados. La macro NT3270 se
   mantiene en una plantilla `.xlsm` externa: un `.xlsx` no conserva VBA.

## Requisitos para desarrollo

- Python 3.11.
- Node.js 20 o superior.
- Una cuenta corporativa con acceso al Apps Script, Sheet, carpeta Drive y
  proyecto Google Cloud de desarrollo.
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) y acceso a
  Cloud Run.
- La Apps Script API habilitada en https://script.google.com/home/usersettings.

## Preparación local

```bash
git clone https://github.com/eduardo202020/auto-tasacion.git
cd auto-tasacion/tasaciones
npm install
python3 -m venv funcions/.venv
source funcions/.venv/bin/activate
pip install -r funcions/requirements.txt
```

Para vincular el proyecto Apps Script propio, crea una copia local de la
plantilla y reemplaza el identificador. Este archivo nunca debe subirse:

```bash
cp .clasp.json.example .clasp.json
npx clasp login
npm run apps:status
```

Consulta `tasaciones/README.local.md` para los comandos de ejecución local,
despliegue de Cloud Run y sincronización de Apps Script.

## Variables y seguridad

No copies claves a código fuente ni al manifest de Apps Script. Usa un `.env`
local, secretos administrados por Google Cloud para producción y cuentas de
servicio con mínimo privilegio. Las claves o documentos que hayan sido
compartidos fuera de un almacén seguro deben rotarse.

## Agregar el próximo módulo

Cada automatización debe vivir en su propio directorio de primer nivel, con
su README, pruebas y configuración aislada. Comparte solo utilidades genéricas
que no contengan reglas de negocio ni datos de clientes.
