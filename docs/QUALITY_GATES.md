# Puertas de calidad

## Antes de aceptar un cambio local

1. Ejecutar la suite de `unittest` completa.
2. Ejecutar `compileall` para detectar errores de importación/sintaxis.
3. Si el cambio toca la salida, generar un XLSX de prueba y ejecutar
   `tools/verify_workbook.py`.
4. Confirmar que el contrato de las 24 columnas no cambió de orden y que
   `ID_CASO` sigue al final.
5. Comprobar que no se añadieron secretos, PDF productivos ni resultados de
   ejecución al control de versiones.

## Pruebas que deben acompañar cambios funcionales

| Cambio | Prueba mínima |
|---|---|
| Regex o extracción PDF | PDF sintético que cubra el campo y un caso negativo. |
| Regla de negocio | Caso que la acepte y conflicto que siga bloqueado sin la regla. |
| Catálogo | Código autorizado y valor desconocido que permanezca fuera de la cola. |
| IA | Corrección con página/evidencia que se revalide y corrección insegura rechazada. |
| Excel | Hojas, tablas, columnas, `ID_CASO` y ruta correcta. |
| HTTP | ZIP binario con nombre variable y respuesta XLSX válida. |

## Condiciones de bloqueo

No considerar listo ni publicar un cambio si ocurre alguno de estos casos:

- una fila incompleta entra a `tblParaProcesar`;
- un conflicto documental se interpreta sin regla aprobada;
- se emite un código que no está en el catálogo;
- una corrección IA no tiene página y evidencia;
- se modifica la interfaz de Power Automate sin actualizar el contrato;
- se depende de un nombre fijo para el ZIP de entrada.

## Antes del despliegue

La publicación necesita aprobación explícita, una revisión de la salida
generada con datos autorizados y la confirmación de compatibilidad por el
responsable de Power Automate. Sigue el runbook
[`CHANGE_AND_DEPLOY.md`](runbooks/CHANGE_AND_DEPLOY.md).
