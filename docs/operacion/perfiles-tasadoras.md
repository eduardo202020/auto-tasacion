# Perfiles de formatos de tasación

Cada PDF se procesa primero con el extractor general. El servicio busca después
una firma explícita de plantilla en los textos del documento. Si encuentra una
coincidencia, registra el perfil, su versión, confianza y términos que la
justifican en `CONTROL` y `REVISION_IA`. La hoja `PARA_PROCESAR` no cambia.

## Configuración vigente

- `cloud-run/reference-data/tasadoras.json`: catálogo versionado de firmas
  textuales de empresas. Solo agrega metadatos de trazabilidad; no concede
  prioridades de negocio ni activa alias de extracción por sí mismo.
- `cloud-run/reference-data/profiles/*.json`: una firma técnica y los alias
  de etiquetas propios de una plantilla. `generic-v1` es el respaldo fijo.
- `opd-construyo-v1`: primer perfil técnico, identificado solo por `OP-D` y
  `Solicitud Construyo` o `Primer Construyo`. Sus alias complementan las
  anclas existentes; no cambian ninguna prioridad de negocio.

Un perfil puede ampliar nombres de etiquetas, por ejemplo el texto que rotula
un valor comercial. No puede convertir un dato sin evidencia, elegir entre
fuentes contradictorias, cambiar catálogos ni enviar una excepción a IBM.

Una tasadora y una plantilla no son equivalentes: la misma empresa puede
emitir múltiples formatos, y un formato puede incluir anexos de otra plantilla.
Por ello, la empresa se identifica con firmas propias y el perfil se selecciona
con una firma técnica independiente. Si solo se conoce la empresa, se conserva
`generic-v1` hasta que exista una variación de extracción repetida y probada.

Si la firma de empresa está solo en un logo, el servicio usa OCR local de los
encabezados y pies de las primeras páginas. La coincidencia se conserva como
`Origen tasadora = OCR_LOCAL`; no se guardan los fragmentos OCR ni se envían
a servicios externos. Si la firma no es única, no se atribuye una tasadora.

## Alta de una tasadora o plantilla

1. El operador registra cada corrección del lote en
   `docs/templates/correcciones_operador.csv`, manteniendo `ID_CASO`, página,
   evidencia, motivo y responsable.
2. Se valida antes de analizarla:

   ```powershell
   python tools/validate_correcciones_operador.py <archivo.csv>
   ```

3. Con un patrón repetido y PDFs autorizados fuera de Git, se redacta un perfil
   JSON con una firma que no sea ambigua y solo los alias necesarios.
4. Se agrega una prueba con un PDF sintético que pruebe la firma y el alias.
5. Se ejecuta `python tools/validate_profile_catalog.py` para comprobar IDs,
   firmas duplicadas y referencias entre perfiles y tasadoras.
6. Operaciones revisa si el cambio altera una regla de negocio. Si la altera,
   debe aprobarse y versionarse en `reglas_operativas.json` antes del despliegue.

Las correcciones del operador son evidencia de mejora, no instrucciones que
Cloud Run ejecute ni material para entrenar o publicar reglas automáticamente.

## Excepciones y Gemini

Gemini puede revisar un caso excepcional solo si la configuración aprobada lo
habilita. Debe devolver página y evidencia, y el servicio vuelve a validar el
resultado. No crea perfiles, no incorpora tasadoras al catálogo y no publica
alias ni reglas a partir de un PDF desconocido.
