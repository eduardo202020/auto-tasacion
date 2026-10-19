# Reglas validadas por el operador

Fuente: `reglas-de-negocio-ajustadas-operador.xlsx`, revisada el 2026-10-19.

## Precedencia

1. Regla general aprobada por el operador.
2. Evidencia explicita del PDF.
3. Ejemplo individual del Golden.

La columna **Estado operador** del libro conserva el estado historico
`Pendiente` en las filas revisadas. La decision efectiva esta en **Respuesta
operador**: `Correcto` valida la regla propuesta y `Corregir` incorpora el
texto de correccion. Cuando una fila `Correcto` formula una pregunta sin elegir
una conducta, se valida el requisito de resolverla, pero no se inventa una
conducta: queda fail-closed.

## Matriz de decisiones

| ID | Tema | Respuesta operador | Estado final | Regla final aprobada | Impacto |
| --- | --- | --- | --- | --- | --- |
| RN-01 | Direccion canonica | Corregir: registral -> minuta -> inspeccion | RESUELTA_OPERADOR | Esa es la prioridad de fuentes. | extractor, contrato, contexto |
| RN-02 | Pisos, sotanos y azotea | Correcto | RESUELTA_OPERADOR | Tabla legible primero; azotea no suma pisos. | extractor, pruebas |
| RN-03 | Primer Construyo y terreno | Corregir: terreno se toma como CASA | RESUELTA_OPERADOR | Primer Construyo + terreno + N pisos y azotea = N/0; terreno = CASA. | extractor, benchmark |
| RN-04 | Fecha de expedicion | Correcto | RESUELTA_OPERADOR | Expedicion prevalece sobre caducidad. | extractor |
| RN-05 | Solicitud Construyo territorial | Correcto | RESUELTA_OPERADOR | Solo respaldo territorial con terna unica DATOS. | extractor, catalogo |
| RN-06 | Lambayeque/Lambayaque | Correcto | RESUELTA_OPERADOR | Equivalencia historica autorizada. | catalogo |
| RN-07 | Ubicacion sin codigo | Correcto | RESUELTA_OPERADOR | UBICACION vacia puede continuar con geografia completa. | servicio, contrato, contexto |
| RN-08 | Importe y moneda | Correcto | RESUELTA_OPERADOR | PEN preferente, positivo y codigo DATOS. | servicio |
| RN-09 | Clase por pisos | Correcto | RESUELTA_OPERADOR | Clase desde pisos y catalogo. | catalogo |
| RN-10 | PRESTAMO | Correcto; regla Cloud antigua | SUPERSEDIDA_POR_ARQUITECTURA | Solo ControlEntrada, 20 digitos; nunca PDF/3270. | servicio, contrato |
| RN-11 | ID_CASO | Correcto | RESUELTA_OPERADOR | Nombre interno + contenido para correlacion. | servicio |
| RN-12 | Salida MASIVO | Correcto | RESUELTA_OPERADOR | Contrato A:Y + ID_CASO final se conserva. | contrato |
| RT-01 | Campos obligatorios | Corregir: lista para macro | RESUELTA_OPERADOR | Interior, referencia y ubicacion son opcionales. | servicio, contrato |
| RT-02 | Catalogos cerrados | Correcto | RESUELTA_OPERADOR | Solo DATOS autorizado. | catalogo |
| RT-03 | Tipo de inmueble IA | Correcto | RESUELTA_OPERADOR | Solo CASA o DEPARTAMENTO. | servicio |
| RT-04 | Valor de CASA | Corregir: siempre reconstruccion | RESUELTA_OPERADOR | CASA -> reconstruccion; DEPARTAMENTO -> comercial. | extractor, catalogo |
| RT-05 | Alcance IA | Correcto | RESUELTA_OPERADOR | IA solo propone campos solicitados y tipados. | servicio |
| RT-06 | Evidencia IA direccion | Correcto | RESUELTA_OPERADOR | Requiere evidencia y pagina. | servicio |
| RT-07 | Conflicto de negocio | Correcto | RESUELTA_OPERADOR | Sin regla aplicable, fail-closed. | servicio |
| RT-08 | Unicidad geografica | Correcto | RESUELTA_OPERADOR | No se elige entre duplicados. | catalogo |
| RT-09 | Via no conocida | Correcto | RESUELTA_OPERADOR | Fallback de via vigente, sin crear codigo. | parser |
| RT-10 | Valores SN por defecto | Correcto | RESUELTA_OPERADOR | SN no reemplaza ubicacion opcional. | parser |
| RT-11 | Componentes duplicados | Correcto | RESUELTA_OPERADOR | No repetir domicilio, exterior y referencia. | parser |
| RT-12 | Longitud de componentes | Correcto | RESUELTA_OPERADOR | Mantener limites de macro. | parser |
| PD-01 | Fuente definitiva de direccion | Correcto | RESUELTA_OPERADOR | Resuelto por RN-01. | documentacion |
| PD-02 | Ubicacion sin homologar | Corregir: agregar referencias si se requieren | PARCIALMENTE_RESUELTA | Vacia y no bloquea si es opcional; altas DATOS son autorizadas. | servicio, pendiente tecnica |
| PD-03 | Multiples unidades | Correcto, sin conducta seleccionada | PENDIENTE_OPERACIONES | Falta decidir fila por garantia, unidad o revision. | fail-closed |
| PD-04 | CASA / valor | Correcto | RESUELTA_OPERADOR | Resuelto por RT-04. | extractor |
| PD-05 | Edad efectiva excepcional | Correcto, sin conducta seleccionada | PENDIENTE_OPERACIONES | Faltan reglas para cero, rangos y remodelacion. | fail-closed |
| PD-06 | Conciliacion IBM | Correcto, sin conducta seleccionada | PENDIENTE_OPERACIONES | Falta llave, coincidencias y reintentos autorizados. | fuera de este cambio |
| PD-07 | OCR corporativo | Correcto, sin conducta seleccionada | PENDIENTE_TECNICA | Falta solucion aprobada y umbral. | fail-closed |

## Casos de referencia

- D01 no autoriza completar PISOS/SOTANOS con `N. Unidades`; no existe regla
  aprobada para inferir `1/0`.
- D08 conserva la terna explicita del PDF y el codigo unico de DATOS.
- D09 aplica RN-03: una azotea enumerada como nivel posterior no incrementa
  pisos.
