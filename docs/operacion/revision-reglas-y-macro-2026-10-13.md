# Revisión de reglas operativas y macro heredada

**Fecha:** 2026-10-13
**Estado:** análisis estático; no modifica reglas ejecutables ni ejecuta VBA

## Evidencia revisada

Se revisaron el libro devuelto por Operaciones y la macro heredada en modo
lectura. No se abrió Excel, no se ejecutó VBA, no se inició PCOMM ni se conectó
con IBM 3270.

El libro de Operaciones conserva `Pendiente` en la columna `Estado operador`.
Las respuestas utilizables están en `Observación / corrección propuesta`. Por
ello las observaciones se registran como decisiones propuestas que necesitan
promoción explícita a reglas versionadas antes de cambiar el comportamiento.

## Cambios explícitos del operador

| ID | Cambio solicitado | Estado frente al código actual | Trabajo de implementación |
| --- | --- | --- | --- |
| RN-01 | Priorizar dirección registral, después minuta y finalmente inspección ocular. | Cambia la prioridad actual `minuta → inspección → municipal/matriz`; el extractor todavía no busca una fuente registral. El orden de municipal/matriz después de este cambio no quedó especificado. | Añadir fuente registral, ordenar candidatos, conservar evidencia de fuente y crear pruebas de conflictos. |
| RN-03 | Si la tasación indica terreno, clasificar el inmueble como `CASA`. | La regla de primer construyo hoy ajusta edad, pisos y sótanos, pero no declara esa clasificación general de terreno. | Precisar el criterio textual y aplicar la clasificación antes de elegir el valor. |
| RT-01 | Para el procesamiento de la macro, exigir préstamo, tipo, moneda, importe, domicilio, domicilio 1, número exterior, distrito, provincia, departamento, pisos, sótanos y año de construcción. | El contrato actual permite `PRESTAMO` vacío y no exige `EXTERIOR`; usa los encabezados heredados `DIRECCION`, `DIRECCION1` y `EXTERIOR`. | Separar la preparación para macro de la entrega Cloud. No endurecer todavía `PARA_PROCESAR` sin resolver cómo se obtiene `PRESTAMO`. |
| RT-04 | Para `CASA`, usar siempre valor de reconstrucción aunque el catálogo lo llame valor nuevo. | La extracción ya elige valor de reconstrucción para `CASA`, pero el catálogo técnico todavía obtiene el código bajo la etiqueta `VALOR NUEVO`. | Confirmar la equivalencia de código y añadir prueba que cubra valor y código. |
| PD-02 | Si una referencia de dirección hace falta, ampliar el código para soportarla. | No define todavía la lista de referencias ni cuándo una ausencia bloquea el proceso. | Recibir catálogo o ejemplos aprobados; luego ampliar parser y pruebas con cada caso. |

## Puntos aún no decididos

Las filas PD-01 y PD-03 a PD-07 fueron marcadas como `Correcto` en la
observación, pero la respuesta no define el comportamiento final. Continúan
abiertos, entre otros, el destino de la dirección operativa cuando difieren
fuentes, múltiples unidades en un PDF, tratamiento de años/edad especiales,
la llave de conciliación contra IBM y la ruta para PDFs escaneados.

No se debe convertir `Correcto` en una regla de código cuando la fila describe
una pregunta sin respuesta operativa.

## Interfaz observada de la macro heredada

La macro contiene tres grupos de procedimientos distintos:

1. Validación y descarga de archivos desde la hoja activa con columnas `A:E`.
2. Consulta masiva que abre un archivo elegido por el operador, toma la primera
   hoja, lee el préstamo de la columna `Z` y guarda resultados en `AA:AD`.
3. Validación cruzada equivalente que además compara un nombre de cliente de
   una columna fija.

Los procedimientos de consulta crean objetos `PCOMM`, usan la sesión `A`,
envían una transacción de terminal y guardan el libro seleccionado en el mismo
archivo. No existe un punto de entrada que reciba la ruta de un lote Cloud o
un `IdLote` como parámetro.

La macro también declara varias funciones públicas con el mismo nombre de
conexión en módulos distintos. Antes de cualquier uso debe compilarse y
consolidarse esa definición; un nombre público duplicado puede impedir la
compilación del proyecto VBA.

## Brecha con `Resultado_Final_<ID_LOTE>.xlsx`

El Excel Cloud usa `PARA_PROCESAR` y `tblParaProcesar`: `PRESTAMO` está en la
columna `A`, `ID_CASO` es la clave de trazabilidad y las hojas de revisión y
control no son colas bancarias. La macro heredada toma la primera hoja,
espera el préstamo en `Z`, usa columnas fijas y guarda en el archivo de
entrada. Por tanto, no puede ejecutarse directamente sobre el resultado Cloud.

Además, el flujo actual deja `PRESTAMO` vacío de forma deliberada y el
simulador PAD puede terminar en simulación sin ese dato. Una corrección
posterior identificó la fuente autorizada: la fila operativa recibida por el
operador. Falta implementar la correlación segura entre esa fila y cada PDF.
Consultar 3270 no resuelve esa ausencia, porque las rutinas de la macro
necesitan el préstamo para iniciar la consulta. Consulte el flujo actualizado
en [`flujo-operador-cloud-macro-2026-10-14.md`](flujo-operador-cloud-macro-2026-10-14.md).

## Diseño que debe preceder a la integración de macro

La siguiente fase debe crear un adaptador versionado, sin alterar el archivo
original de la macro:

```mermaid
flowchart LR
    A[Resultado_Final en OneDrive] --> B[Validar contrato Cloud]
    B --> C[Copiar a directorio de trabajo local]
    C --> D[Adaptar tabla por encabezados]
    D --> E[Macro versionada]
    E --> F[Capturar resultado por ID_CASO]
    F --> G[Publicar solo una copia de salida]
```

El adaptador tendrá que definir de forma explícita:

- la fuente y validación del `PRESTAMO`;
- el mapeo por nombre de los campos Cloud a la interfaz de macro, sin posiciones
  fijas;
- el libro de trabajo local y la política para no modificar el Excel original
  de OneDrive;
- los campos de resultado, sus estados y su relación con `ID_CASO`;
- qué procedimiento se permite ejecutar y qué dependencia PCOMM queda fuera
  del alcance hasta contar con autorización y pruebas separadas.

Hasta entonces, PAD mantiene el límite actual: `run-lot` valida y simula el
lote, sin VBA, Excel interactivo, PCOMM ni IBM 3270.
