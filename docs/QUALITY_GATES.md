# Puertas de calidad

## Antes de aceptar un cambio local

1. Ejecutar `python tools/validate_profile_catalog.py` y la suite `unittest`.
2. Ejecutar `compileall` para detectar errores de importación y sintaxis.
3. Si cambia la salida, generar un XLSX sintético y ejecutar
   `tools/verify_workbook.py`.
4. Confirmar las 24 columnas heredadas y `ID_CASO` al final.
5. Confirmar que no se agregaron secretos, PDFs productivos ni resultados.

## Pruebas de la ruta masiva de PDFs

Antes de publicar se requiere un lote sintético de 300 PDFs individuales y
aproximadamente 1.4 GiB en total que compruebe:

1. los 300 PDFs se listan y el total supera 1 GiB;
2. ningún request contiene el lote completo;
3. cada PDF se carga independientemente;
4. una interrupción en el PDF N permite reintentar ese PDF sin repetir los
   ya confirmados;
5. cambio de eTag produce `FALLIDO_ORIGEN_CAMBIO`;
6. manifiestos idénticos devuelven el mismo lote;
7. un PDF individual sobre el límite se rechaza sin subirlo;
8. un archivo no PDF se rechaza;
9. un lote parcial no inicia el Job;
10. el Job procesa solo PDFs confirmados y su memoria no depende del tamaño
    total del lote;
11. `Resultado_Final_<ID_LOTE>.xlsx` pasa `tools/verify_workbook.py`;
12. `tblParaProcesar` y el contrato Excel no cambian.

El generador de carga crea datos temporales fuera de Git. No se suben PDFs de
clientes ni lotes de prueba masivos al repositorio.

## Condiciones de bloqueo

No considerar listo ni publicar si una fila incompleta entra a
`tblParaProcesar`, un conflicto se infiere sin regla aprobada, un código no
pertenece al catálogo, la IA no tiene evidencia, un flujo envía el lote entero,
o el Job acepta un PDF no confirmado.

## Antes del despliegue

La publicación requiere aprobación explícita, revisión con datos autorizados,
validación del responsable de Power Automate y el runbook de cambio.
