# Registro de features: perfiles e ingesta de tasaciones

Una feature se considera implementada solo cuando tiene prueba automática y no
altera el contrato de `PARA_PROCESAR` sin aprobación operativa.

| ID | Feature | Estado | Criterio de aceptación |
| --- | --- | --- | --- |
| F01 | Catálogo versionado de tasadoras | Implementado | Cada empresa tiene un ID estable y firmas no ambiguas, o se mantiene el respaldo genérico. |
| F02 | Detección de plantilla | Implementado | Una firma inequívoca selecciona un perfil; si no existe, se mantiene `generic-v1`. |
| F03 | Extracción específica por perfil | Implementado de forma acotada | OP-D y Braschi agregan aliases/OCR local validado; otras diferencias repetidas requieren prueba sintética. |
| F04 | Trazabilidad de perfil | Implementado | `CONTROL` y `REVISION_IA` registran tasadora, perfil, versión, confianza y coincidencias. |
| F05 | Bitácora de correcciones del operador | Implementado | El CSV exige `ID_CASO`, evidencia, motivo, operador y fecha. |
| F06 | Propuesta de perfil mediante Gemini | Pendiente de aprobación | La IA genera borradores con evidencia; nunca publica perfiles. |
| F07 | Aprobación y publicación de perfiles | Proceso definido | Catálogo, prueba sintética, revisión funcional y despliegue autorizado. |
| F08 | Métricas por perfil | Pendiente | Medir revisión, faltantes y correcciones sin guardar PDFs productivos. |
| F09 | Detección de firmas gráficas u OCR | Implementado localmente | OCR local de encabezados y pies identifica logos sin enviar PDFs fuera de Cloud Run. |
| F10 | OCR de campo por perfil técnico | Implementado | Braschi recorta celdas técnicas solo ante evidencia y ambigüedad controlada. |
| F11 | Registro de lote de PDFs | Implementado localmente | `POST /v1/lotes` valida manifiesto, límites e idempotencia y devuelve un `ID_LOTE` sin contenido documental. |
| F12 | Ingesta OneDrive a GCS por PDF | Backend implementado; flujo pendiente | La API emite ticket por PDF y confirma eTag/tamaño; falta construir el flujo Power Automate que los use. |
| F13 | Procesamiento asíncrono desde PDFs individuales | Implementado localmente; Job pendiente | `batch_worker.py` procesa únicamente objetos `CARGADO`, uno por iteración, y conserva el XLSX contractual. |
| F14 | Estado y entrega diferida | Backend implementado; flujo pendiente | API expone progreso, resultado y confirmación de entrega; falta Power Automate para consultar y crear el XLSX en OneDrive. |
| F15 | Integridad e idempotencia por manifiesto | Implementado localmente | SHA-256 de carpeta + `itemId:eTag`, validación eTag antes/después y verificación de tamaño en GCS. |

## Ciclo de alta seguro

1. El extractor general procesa y registra perfil detectado.
2. El operador registra correcciones con evidencia.
3. Variaciones repetidas generan un perfil técnico explícito.
4. Se agrega una prueba sintética sin PDFs productivos.
5. Se valida catálogo y suite antes de solicitar despliegue.
