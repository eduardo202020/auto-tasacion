# Instrucciones de trabajo para agentes

## Propósito y alcance

Este repositorio automatiza la extracción documental de tasaciones hipotecarias.
El servicio activo recibe un ZIP binario desde Power Automate y devuelve un
XLSX que alimenta la automatización IBM 3270. El objetivo es maximizar casos
operables sin sacrificar exactitud ni trazabilidad.

La fuente de verdad del comportamiento vigente es:

1. [`README.md`](README.md): visión del producto y límites.
2. [`docs/AI_CONTEXT.md`](docs/AI_CONTEXT.md): modelo de dominio y rutas de
   cada caso.
3. [`contracts/masivo.md`](contracts/masivo.md): contrato inmutable del XLSX
   que consume Power Automate.
4. [`cloud-run/README.md`](cloud-run/README.md): ejecución y despliegue del
   servicio.

Lee esos documentos antes de modificar extracción, validación, IA, formato de
Excel o integración.

## Rutas activas y rutas archivadas

- `cloud-run/`: Python/Functions Framework que se ejecuta en Cloud Run.
- `contracts/`: contrato de integración del Excel.
- `power-platform/`: contrato funcional con Power Apps, Power Automate y PAD.
- `cloud-run/reference-data/`: catálogos y reglas versionadas que afectan
  decisiones de negocio.
- `legacy/google-sheets/`: histórico. No modificar ni desplegar salvo una
  solicitud explícita de mantenimiento del flujo legado.
- `_referencias_locales/`: material local excluido de Git; no copiar PDFs,
  datos de clientes, credenciales ni exportaciones al repositorio.

## Invariantes no negociables

- La entrada HTTP es un `POST` con `Content-Type: application/zip` y el ZIP
  binario en el cuerpo. No depende de `auto.zip`, de nombres fijos ni de rutas
  locales de entrada.
- `PARA_PROCESAR` / `tblParaProcesar` es la única cola que puede operar Power
  Automate/PAD/IBM. Contiene solo casos completos y validados.
- `REVISION_IA` / `tblRevisionIa` contiene excepciones; nunca debe usarse para
  operar contra el banco.
- `CONTROL` / `tblControl` mantiene una fila por PDF y su trazabilidad.
- Las primeras 24 columnas del contrato y su orden no cambian. `ID_CASO` es la
  última columna técnica y relaciona los tres resultados.
- `PRESTAMO` puede estar vacío antes del 3270: lo completa el flujo posterior.
- Un dato crítico sin evidencia, un código fuera de catálogo o un conflicto
  entre fuentes no puede entrar en `PARA_PROCESAR`.
- La IA es una revisión excepcional, no una fuente de verdad: debe devolver
  evidencia y página, y su resultado se revalida antes de ser operable.
- Un conflicto sin regla aprobada queda en `REVISION_IA`; no se resuelve por
  inferencia del agente ni del modelo.

## Cómo elegir instrucciones adicionales

Las skills locales están versionadas en [`skills/`](skills/README.md). Antes
de una tarea que coincida con una de ellas, lee su `SKILL.md`:

- Extracción PDF, Cloud Run, IA, pruebas o despliegue:
  `skills/tasaciones-cloud-run/SKILL.md`.
- Columnas, tablas XLSX, enrutamiento a Power Automate o controles de salida:
  `skills/tasaciones-contrato-excel/SKILL.md`.

Si el entorno ofrece skills especializadas de PDF o spreadsheets, úsalas para
inspeccionar esos formatos. No sustituyen las reglas de negocio locales.

## Ciclo mínimo de cambio

1. Delimita el contrato afectado y añade o ajusta una prueba de regresión.
2. Implementa el cambio mínimo en el componente activo.
3. Ejecuta `Tasaciones: pruebas` desde VS Code o el comando de
   `docs/DEVELOPMENT_ENVIRONMENT.md`.
4. Si se genera un XLSX, valida su estructura con
   `tools/verify_workbook.py`.
5. Actualiza el contrato y la documentación solo si cambia el comportamiento
   observable.

El despliegue es una mutación separada: nunca publicar una revisión Cloud Run
solo porque una prueba local pasó. Requiere autorización explícita y el
runbook de cambio.

## Seguridad y datos

- Nunca imprimas, subas o versionas claves, tokens, endpoints privados ni PDFs
  de clientes. Usa `.env.example` solo como plantilla sin secretos.
- No habilites `AI_REVIEW_ENABLED` ni modifiques reglas operativas sin la
  aprobación de Seguridad y Operaciones respectivamente.
- No utilices datos productivos como fixtures. Construye PDFs sintéticos en
  las pruebas.
