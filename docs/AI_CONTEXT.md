# Contexto operativo para IA

## Qué resuelve el proyecto

`auto-tasacion` convierte un lote ZIP de informes PDF de tasación en una cola
Excel fiable para la automatización hipotecaria. No intenta operar el
Mainframe: entrega a Power Automate únicamente casos documentados y completos.

```text
Power Apps
  -> Power Automate / OneDrive
  -> HTTP POST application/zip
  -> Cloud Run (extracción y validación)
  -> Resultado_Final.xlsx en OneDrive
  -> tblParaProcesar
  -> Power Automate Desktop / IBM 3270
```

El nombre del ZIP no forma parte del contrato. Cloud Run recibe sus bytes en
el cuerpo HTTP y procesa en memoria los PDF contenidos dentro.

## Estados de un caso

| Ruta final | Significado | Destino |
|---|---|---|
| `LISTO_DETERMINISTA` | La extracción y los catálogos resolvieron todos los campos exigidos. | `PARA_PROCESAR` |
| `LISTO_IA_VERIFICADO` | Una revisión IA con evidencia corrigió una excepción y la segunda validación la aprobó. | `PARA_PROCESAR` |
| `PENDIENTE_IA` | Hay datos faltantes que podrían verificarse, pero la IA no está disponible o no puede procesar el PDF. | `REVISION_IA` |
| `REGLA_NEGOCIO_PENDIENTE` | Hay fuentes contradictorias sin una regla operativa aprobada que establezca prioridad. | `REVISION_IA` |
| `REVISION_HUMANA` | No existe una corrección permitida o la evidencia no es suficiente. | `REVISION_IA` |

Todos los casos, incluso los listos, se registran en `CONTROL`.

## Artefactos y responsabilidades

| Componente | Responsabilidad | No debe hacer |
|---|---|---|
| `cloud-run/service.py` | Recibir ZIP, clasificar casos y construir el XLSX. | Depender del nombre o de una ruta del ZIP. |
| `cloud-run/pdf_extractor.py` | Extraer evidencia determinista de PDF. | Inventar campos o silenciar conflictos. |
| `cloud-run/catalog.py` + `reference-data/` | Traducir exclusivamente valores autorizados de `DATOS`. | Aplicar equivalencias no aprobadas. |
| `cloud-run/ai_reviewer.py` | Consultar IA solo para excepciones permitidas. | Enviar casos directamente a la cola operable. |
| `contracts/masivo.md` | Definir el contrato de salida estable. | Ser reinterpretado por cada consumidor. |
| `power-platform/` | Documentar la integración del entorno Microsoft. | Reintroducir Google Sheets/App Script en el flujo activo. |

## Reglas de decisión importantes

- El tipo de inmueble se traduce a los códigos del catálogo de la hoja `DATOS`.
- El año de construcción puede derivarse de `año de expedición - edad efectiva`
  solo cuando ambos valores tienen evidencia y el resultado es razonable.
- Piso, sótano, dirección o valores que provengan de fuentes contradictorias
  son conflictos, no vacíos normales. Solo una regla versionada y aprobada
  puede definir su prioridad.
- Los campos auxiliares `COL_*` se conservan por compatibilidad de formato.
- `PRESTAMO` se completa después, durante el proceso de IBM 3270; no impide
  que una fila validada llegue a `PARA_PROCESAR`.

## Límites del sistema

- La IA está apagada por defecto y no sustituye las reglas de negocio.
- Cloud Run no descarga archivos desde OneDrive: Power Automate entrega el
  ZIP como bytes.
- Los datos personales, PDFs productivos, macros originales y exportaciones
  son referencias locales fuera de Git.
- El histórico Google Sheets está archivado en `legacy/` y no comparte el
  contrato activo.

## Lectura por tipo de tarea

| Si la tarea es… | Leer primero |
|---|---|
| Ajustar expresiones, tablas o parsers PDF | `skills/tasaciones-cloud-run/SKILL.md`, `cloud-run/tests/test_service.py` |
| Cambiar una columna, una tabla o el consumo PAD | `skills/tasaciones-contrato-excel/SKILL.md`, `contracts/masivo.md`, `power-platform/README.md` |
| Definir prioridades de negocio | `docs/REGLAS_NEGOCIO_PENDIENTES.txt`, `cloud-run/reference-data/reglas_operativas.json` |
| Preparar publicación | `docs/runbooks/CHANGE_AND_DEPLOY.md` |
