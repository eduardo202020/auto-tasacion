# Investigación y decisión para lotes masivos

## Pregunta resuelta

¿Cómo soportar aproximadamente 150 PDFs que pueden superar 1 GiB en total sin
exceder los límites de mensajes de Power Apps y Power Automate?

## Decisión aprobada para implementación

El lote será un manifiesto de PDFs individuales ya cargados por el operador en
`/auto-tasaciones/PDFs`. Power Automate obtiene y carga cada PDF individualmente a
Cloud Storage. Cloud Run Job procesa los objetos confirmados uno por uno.

Esto mantiene el tamaño de cada mensaje dentro del límite individual del
conector y evita una transferencia única de 1 GiB.

## Decisiones descartadas

| Alternativa | Decisión | Motivo |
| --- | --- | --- |
| Adjuntar ZIP en Power Apps | Descartada | Serializa contenido y alcanza límites de mensaje. |
| ZIP único por Power Automate | Legacy hasta 90 MB | No cumple el objetivo total de 1 GiB o más. |
| Microsoft Graph / App Registration Entra | Descartada | No se autoriza ese mecanismo para esta integración. |
| ZIP remoto con GCS FUSE | Descartada | La nueva ruta no usa ZIP. |
| Concatenar PDFs o Base64 | Descartada | Aumenta memoria, tamaño y riesgo operativo. |

## Garantías del diseño

- La API recibe manifiestos, no PDFs.
- Cada URL firmada es para un único PDF declarado.
- El eTag antes/después evita procesar una versión cambiada.
- El Job no inicia con cargas parciales.
- `PARA_PROCESAR`, `REVISION_IA`, `CONTROL`, `tblParaProcesar` e `ID_CASO`
  permanecen sin cambios.
- La ruta ZIP vigente queda aislada como fallback hasta validar la nueva ruta.
- Un JSON de control pequeño en `/auto-tasaciones/Controles` activa un único
  orquestador por lote. Un claim persistido en GCS evita que eventos duplicados
  de OneDrive dupliquen cargas, Jobs o entregas.
- El orquestador espera solo su propio lote con backoff y máximo de dos horas
  después de iniciar el Job; no hay flujos recurrentes sin trabajo en la ruta
  nueva.

## Prueba pendiente

La aceptación final requiere un lote sintético de 300 PDFs y aproximadamente
1.4 GiB en total, cargas reanudables por PDF y verificación del XLSX final.
No se agregan archivos grandes ni datos productivos al repositorio.
