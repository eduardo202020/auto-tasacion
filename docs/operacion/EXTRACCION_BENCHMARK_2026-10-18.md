# Resultado local: mejora de extraccion determinista

Fecha de la corrida: 2026-10-18.

## Alcance y resguardo de evidencia

La corrida usa `auto-tasacion-benchmark/` solo como corpus externo. El harness
lee cada PDF directamente desde los ZIP y escribe el informe JSON bajo `%TEMP%`.
No copia PDFs, XLSX, XLSM, prestamos, expedientes ni texto documental al
repositorio. Los informes conservan solamente hash, metadatos de extraccion,
candidatos de importe, decisiones y codigos de validacion seguros.

## Cambios evaluados

- Los campos opcionales `N. INTERIOR`, `UBICACION` y `UBICACION 1` quedan
  vacios cuando no existe evidencia. `REFERENCIA` conserva su semantica `SN`.
- El servicio clasifica `TASACION`, `ESTUDIO_TITULOS` y `DESCONOCIDO` antes de
  intentar extraer una tasacion. Un estudio de titulos se registra como
  `DOCUMENTO_NO_TASACION` y nunca entra a la cola de PAD.
- `provider_id`, `template_id` y `layout_family` se trazan por separado. Se
  agregaron firmas exactas para Quota Jalvo, ASET/Appraisals y Outsourcing
  Empresarial del Peru; las firmas no fuerzan una plantilla nueva.
- Los importes se recolectan como candidatos con moneda, pagina, ancla,
  seccion y prioridad. La seleccion rechaza importes no positivos antes de
  `PARA_PROCESAR`.
- La metadata operativa autorizada continua separada de la evidencia PDF:
  `PRESTAMO` se proyecta desde el control y no desde el extractor.

## Corpus comparable de 120 casos

| Ruta | Antes | Despues |
| --- | ---: | ---: |
| `LISTO_DETERMINISTA` | 51 | 91 |
| `PENDIENTE_IA` | 64 | 17 |
| `REGLA_NEGOCIO_PENDIENTE` | 5 | 8 |
| `DOCUMENTO_NO_TASACION` | 0 | 2 |
| `REVISION_HUMANA` | 0 | 2 |

La tasa determinista sube de 42.50% (51/120) a 75.83% (91/120). Los casos que
no son tasacion se cuentan aparte: no se convierten artificialmente en listos.

## Corpus completo de 150 casos

| Ruta | Casos |
| --- | ---: |
| `LISTO_DETERMINISTA` | 114 |
| `PENDIENTE_IA` | 19 |
| `REGLA_NEGOCIO_PENDIENTE` | 11 |
| `DOCUMENTO_NO_TASACION` | 2 |
| `REVISION_HUMANA` | 4 |

Los dos estudios de titulos esperados se clasificaron como
`ESTUDIO_TITULOS`. Ninguno de los 114 casos listos tuvo importe seleccionado
menor o igual a cero. El caso de regresion de valores multiples conserva
candidatos no positivos como evidencia y selecciona el importe comercial final
positivo por su ancla prioritaria.

## Golden del operador: estado de puerta

El harness compara semantica de salida sin guardar direcciones ni valores del
golden en el informe: tipo, moneda, importe, pisos, sotanos, anio, clase,
direccion estructurada, geografia y decision final.

Resultados actuales sobre 10 documentos:

| Campo | Coincidencias |
| --- | ---: |
| Tipo | 10/10 |
| Moneda | 9/10 |
| Importe | 8/10 |
| Pisos | 7/10 |
| Sotanos | 9/10 |
| Anio | 9/10 |
| Clase | 8/10 |
| Direccion estructurada | 3/10 |
| Geografia | 7/10 |
| Decision final lista | 8/10 |

Persisten diferencias criticas de golden en D01, D07, D08 y D09. Requieren
evidencia adicional o una regla de negocio aprobada para valores, pisos,
anio de obra y direccion. No se corrigen por nombre de archivo ni se
resuelven con una inferencia generica.

## Decision de despliegue

**No desplegar.** La cobertura mejoro y el contrato de workbook pasa, pero la
puerta del golden no esta completa. El siguiente cambio debe atacar esas
diferencias mediante una estrategia de plantilla o una regla de Operaciones
documentada, con regresion especifica antes de promover servicio o Job.
