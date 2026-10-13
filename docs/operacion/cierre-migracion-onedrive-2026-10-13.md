# Cierre de migracion OneDrive - 2026-10-13

## Resultado

La migracion de la ruta masiva de OneDrive quedo validada mediante una prueba
E2E manual, iniciada desde Power Apps. La prueba recorrio la ruta de PDFs
individuales y produjo el Excel final esperado.

La ruta logica operativa es:

```text
/automatizaciones-jhglazar/auto-tasaciones
```

No se versionan identificadores de OneDrive, conexiones, URLs firmadas,
contenido de PDFs, resultados operativos ni datos de clientes.

## Evidencia E2E

La ejecucion manual confirmo, para un lote de prueba aislado, la siguiente
secuencia:

```text
Power Apps
  -> auto-tasacion-iniciar-lote
  -> JSON de control en Controles
  -> auto-tasacion-orquestar-lote
  -> carga individual de PDFs a GCS
  -> Cloud Run Job
  -> creacion y entrega idempotente del Excel final en OneDrive
```

El resultado fue satisfactorio: el Excel final esperado se genero al terminar
el lote. No se volvio a ejecutar la prueba durante este cierre documental.

## Configuracion desplegada y comprobada

| Componente | Estado final |
| --- | --- |
| Cloud Run | Acepta la carpeta de PDFs bajo la nueva raiz logica. |
| `auto-tasacion-iniciar-lote` | Publicado con las rutas nuevas de `PDFs` y `Controles`. |
| `auto-tasacion-orquestar-lote` | Publicado con trigger sobre `Controles`, `splitOn = @triggerBody()` y entrega idempotente. |
| Espera de orquestacion | La accion `Esperar_con_backoff` usa `inputs.interval.count` basado en `espera_segundos` e `inputs.interval.unit = Second`. |
| `autoTasacionJG` | Sin cambios para esta migracion; conserva Actualizar y Ejecutar. |
| Flujos recurrentes heredados | No se modificaron durante la migracion. |
| Microsoft Teams | La accion de prueba quedo fuera de la definicion publicada del orquestador. La configuracion futura se documenta por separado. |

El respaldo previo se conservo fuera del repositorio Git. No forma parte de
este commit ni de los artefactos versionados.

## Alcance y reversion

Este cierre no elimina los flujos heredados ni altera la ruta ZIP de
transicion. Si se requiere una reversion futura, debe realizarse en una ventana
operativa: detener la nueva orquestacion, restaurar las definiciones y
configuracion respaldadas, y preservar controles, manifiestos y resultados
existentes.

La documentacion de preparacion y auditoria anterior permanece como evidencia
historica. Para el estado operativo actual, este documento prevalece sobre las
secciones que indiquen que la migracion estaba pendiente.
