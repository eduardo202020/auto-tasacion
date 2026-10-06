# Auditoría local de cobertura de tasadoras — 2026-10-06

## Alcance y método

Se inspeccionaron localmente los PDFs de `auto-150`, `auto-4` y `auto-10`.
Las cifras se deduplican por contenido binario: los tres directorios contienen
164 archivos, equivalentes a 149 documentos distintos. No se copiaron PDFs al
repositorio ni se registraron nombres, direcciones o valores de clientes.

La tasadora se asigna por la primera página que contiene una única firma
registrada. Una firma de otra empresa en anexos posteriores no cambia esa
asignación. Si la primera página con firmas contiene más de una empresa, no se
asigna tasadora.

## Resultado por empresa

| Tasadora | Documentos únicos | Operables | Revisión | Decisión |
| --- | ---: | ---: | ---: | --- |
| Braschi Tasaciones | 9 | 1 | 8 | Mantener `braschi-construyo-v1`; siete excepciones carecen de geografía utilizable. |
| EV Inmobiliaria Barrenechea | 40 | 40 | 0 | El extractor general es suficiente. |
| IMAX Ingeniería Máxima | 34 | 32 | 2 | El extractor general es suficiente; las excepciones son geográficas. |
| Layseca Asociados | 14 | 12 | 2 | Mantener el extractor general y el perfil OP-D cuando aplique; las excepciones son geográficas. |
| Quantum Valuaciones | 7 | 0 | 7 | Detectar la empresa; no crear perfil mientras falte geografía verificable. |
| Tinsa | 19 | 19 | 0 | El extractor general es suficiente. |
| Valortec Tasaciones | 3 | 3 | 0 | El extractor general es suficiente. |
| Sin firma conocida | 23 | 16 | 7 | Esperar evidencia de marca o revisar OCR local tras un despliegue autorizado. |

## Lotes solicitados

| Directorio | PDFs | Resultado |
| --- | ---: | --- |
| `auto-4` | 4 | 4 operables: tres IMAX y uno Valortec. |
| `auto-10` | 10 | 9 operables y 1 en revisión; incluye Braschi, IMAX, Layseca, Valortec y tres sin firma conocida. |

## Próximas decisiones técnicas

1. No crear perfiles para empresas cuyo extractor general ya cubre todos sus
   documentos observados.
2. Mantener en revisión los casos sin códigos geográficos o sin evidencia
   documental; una plantilla no puede inventar esos valores.
3. La revisión `demo-tasaciones-ia-00068-cv2` ya está desplegada con OCR
   local acotado a encabezados y pies para intentar identificar la marca de
   los 23 documentos sin firma textual. Revisar su resultado en los siguientes
   lotes; una coincidencia ambigua conserva `generic-v1`.
4. Crear otro perfil de extracción solo si una misma empresa y una misma
   variación de formato fallan de manera repetida, con evidencia del campo y
   una prueba sintética.
