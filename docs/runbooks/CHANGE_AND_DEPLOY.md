# Runbook de cambio y despliegue

## 1. Clasificar el cambio

| Tipo | Ejemplos | Revisión requerida |
|---|---|---|
| Interno | Refactor sin cambio observable, mejora de mensaje. | Pruebas unitarias. |
| Extracción | Nueva etiqueta PDF, corrección de parser. | Prueba sintética y caso de regresión. |
| Negocio | Prioridad entre fuentes, códigos, columnas requeridas. | Aprobación de Operaciones y contrato actualizado. |
| Integración | Hojas, tablas, HTTP, Power Automate/PAD. | Validación conjunta con el responsable de integración. |
| IA | Modelo, campos enviados, prompt, habilitación. | Seguridad, Operaciones y prueba de rechazo de evidencia insuficiente. |

No conviertas una decisión de negocio pendiente en una heurística silenciosa.

## 2. Validar localmente

Ejecuta las puertas descritas en [`../QUALITY_GATES.md`](../QUALITY_GATES.md).
Para cambios del endpoint, comprueba además que un POST binario con un ZIP de
nombre arbitrario responde un XLSX con las tres tablas exigidas.

## 3. Revisar la compatibilidad externa

Antes de publicar, confirma que Power Automate conserva:

- `POST` con `Content-Type: application/zip`;
- el contenido de OneDrive en el cuerpo, sin serializar a JSON/Base64;
- la lectura exclusiva de `tblParaProcesar`;
- la actualización de `CONTROL` usando `ID_CASO`;
- el manejo de `REVISION_IA` fuera de IBM 3270.

Si cambia cualquiera de esos puntos, despliega y cambia el flujo externo como
una única versión coordinada; no actualices uno sin el otro.

## 4. Publicar con autorización explícita

Desde la raíz, usando el proyecto, región y cuenta corporativa autorizados:

```bash
gcloud run deploy <SERVICIO_CLOUD_RUN> \
  --source cloud-run \
  --function procesar_tasaciones \
  --base-image python311 \
  --region <REGION>
```

No copies claves a la línea de comandos. Las variables sensibles se entregan
con Secret Manager. Si se activa la IA, confirma que `AI_REVIEW_ENABLED`, el
modelo aprobado y los permisos están configurados en la revisión publicada.

## 5. Verificar y dejar evidencia

Después del despliegue:

1. Identifica la revisión con tráfico activo.
2. Ejecuta un lote de prueba autorizado desde el mismo patrón de Power
   Automate.
3. Valida el XLSX y el conteo de rutas en las tres hojas.
4. Confirma que ningún caso con conflicto aparece en `PARA_PROCESAR`.
5. Registra versión, fecha, lote de prueba no sensible, responsable y
   resultado en el sistema corporativo de cambios.

Si falla un punto de integración, enruta el tráfico a la revisión anterior
validada siguiendo el procedimiento corporativo de rollback.
