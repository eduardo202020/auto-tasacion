# Perfiles de formatos de tasación

Cada PDF se procesa primero con el extractor general. El servicio busca después
una firma explícita de plantilla en los textos del documento. Si encuentra una
coincidencia, registra el perfil, su versión, confianza y términos que la
justifican en `CONTROL` y `REVISION_IA`. La hoja `PARA_PROCESAR` no cambia.

## Configuración vigente

- `cloud-run/reference-data/tasadoras.json`: catálogo de empresas aprobadas.
  Inicia vacío para no atribuir documentos históricos a una empresa sin una
  evidencia confirmada.
- `cloud-run/reference-data/profiles/*.json`: una firma técnica y los alias
  de etiquetas propios de una plantilla. `generic-v1` es el respaldo fijo.
- `opd-construyo-v1`: primer perfil técnico, identificado solo por `OP-D` y
  `Solicitud Construyo` o `Primer Construyo`. Sus alias complementan las
  anclas existentes; no cambian ninguna prioridad de negocio.

Un perfil puede ampliar nombres de etiquetas, por ejemplo el texto que rotula
un valor comercial. No puede convertir un dato sin evidencia, elegir entre
fuentes contradictorias, cambiar catálogos ni enviar una excepción a IBM.

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
5. Operaciones revisa si el cambio altera una regla de negocio. Si la altera,
   debe aprobarse y versionarse en `reglas_operativas.json` antes del despliegue.

Las correcciones del operador son evidencia de mejora, no instrucciones que
Cloud Run ejecute ni material para entrenar o publicar reglas automáticamente.

## Excepciones y Gemini

Gemini puede revisar un caso excepcional solo si la configuración aprobada lo
habilita. Debe devolver página y evidencia, y el servicio vuelve a validar el
resultado. No crea perfiles, no incorpora tasadoras al catálogo y no publica
alias ni reglas a partir de un PDF desconocido.
