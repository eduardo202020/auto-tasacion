# Registro de features: perfiles de tasadoras

Este registro hace visible el avance del sistema de adaptación documental.
Una feature se considera implementada solo cuando tiene prueba automática y no
altera el contrato de `PARA_PROCESAR` sin aprobación operativa.

| ID | Feature | Estado | Criterio de aceptación |
| --- | --- | --- | --- |
| F01 | Catálogo versionado de tasadoras | Implementado | Cada empresa tiene un ID estable y firmas textuales no ambiguas, o permanece en respaldo genérico si su marca no está disponible como texto; la detección solo agrega metadatos. El catálogo cubre Braschi, Layseca, Tinsa, Valortec, IMAX, EV Inmobiliaria Barrenechea y Quantum Valuaciones. |
| F02 | Detección de plantilla | Implementado | Una firma inequívoca selecciona un perfil; si no existe, se mantiene `generic-v1`. |
| F03 | Extracción específica por perfil | Implementado de forma acotada | `opd-construyo-v1` aporta alias técnicos para valores y `braschi-construyo-v1` habilita OCR local de una tabla técnica cuando el texto extraíble no contiene ambos valores. Las demás empresas continúan con el extractor general hasta contar con una variación repetida y probada. |
| F04 | Trazabilidad de perfil | Implementado | `CONTROL` y `REVISION_IA` registran tasadora, perfil, versión, confianza y coincidencias. |
| F05 | Bitácora de correcciones del operador | Implementado | El CSV exige `ID_CASO`, campo, valor final, página, evidencia, motivo, operador y fecha. |
| F06 | Propuesta de perfil mediante Gemini | Pendiente de aprobación | La IA debe generar un borrador con evidencia; nunca crea ni publica perfiles por sí sola. Requiere Seguridad y Operaciones. |
| F07 | Aprobación y publicación de perfiles | Proceso definido | Un perfil pasa por validación del catálogo, prueba sintética, revisión funcional y despliegue autorizado. |
| F08 | Métricas por perfil | Pendiente | Medir proporción de revisión, campos faltantes y correcciones por perfil sin guardar PDFs productivos. |
| F09 | Detección de firmas gráficas u OCR | Implementado localmente | OCR local de encabezados y pies identifica logos sin enviar PDFs fuera de Cloud Run. Si falla o no hay firma única, se conserva `generic-v1`. Desplegado en Cloud Run el 2026-10-06. |
| F10 | OCR de campo por perfil técnico | Desplegado en Cloud Run el 2026-10-06 | `braschi-construyo-v1` recorta solo las celdas de pisos y sótanos cuando ambos encabezados coinciden y el parser textual falla. Cada lectura debe ser un entero único y válido; cualquier ambigüedad mantiene el caso en revisión. |

## Ciclo de alta seguro

1. El extractor general procesa el documento y registra el perfil detectado.
2. El operador registra correcciones con evidencia en
   `docs/templates/correcciones_operador.csv`.
3. Si una misma variación se repite, se propone un perfil JSON con una firma
   técnica explícita y solamente los alias requeridos.
4. Se añade una prueba con PDF sintético. Los PDFs reales no ingresan al
   repositorio ni a las pruebas.
5. Se valida con `python tools/validate_profile_catalog.py` y la suite de
   pruebas antes de solicitar el despliegue.

## Criterio para crear una plantilla nueva

No se crea una plantilla solo porque la empresa sea diferente. Deben existir
al menos dos documentos autorizados con una misma variación técnica que el
extractor general no resuelva, junto con la evidencia del campo y una prueba
sintética. La ausencia de evidencia en el PDF se mantiene en revisión; una
plantilla no puede completarla por inferencia.
