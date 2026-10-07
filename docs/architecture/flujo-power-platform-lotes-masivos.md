# Flujo Power Platform para lotes masivos

> **Estado:** diseño acordado para implementar. No está desplegado.

## Propósito

Permitir que el operador procese un ZIP de tasaciones de hasta 2 GiB sin que
Power Apps ni Power Automate transmitan el archivo binario. El ZIP se deposita
en OneDrive y el backend lo copia hacia Cloud Storage para procesarlo de forma
asíncrona.

La salida se mantiene en la misma carpeta de OneDrive que contiene el ZIP. La
PC operativa sincroniza esa carpeta y Power Automate Desktop usa únicamente la
tabla `tblParaProcesar` para continuar con IBM 3270.

## Flujo objetivo

```text
Operador
  │ carga manualmente un ZIP
  ▼
OneDrive /auto-tasaciones
  │
  │ lista y selecciona; no lee el contenido
  ▼
Power Apps
  │ metadatos del ZIP seleccionado
  ▼
Power Automate: iniciar lote
  │ JSON pequeño
  ▼
API de control Cloud Run
  │ crea ID_LOTE y ejecuta el Job
  ▼
Cloud Run Job
  │ descarga OneDrive con Microsoft Graph → GCS
  │ procesa un PDF a la vez
  ▼
Cloud Storage: Resultado_Final_<ID_LOTE>.xlsx
  │
  │ estado y XLSX pequeño
  ▼
Power Automate: entrega resultado
  │
  ▼
OneDrive /auto-tasaciones
  │
  ▼
PC sincronizada → Power Automate Desktop → IBM 3270
```

El único componente que mueve el ZIP es el Job, desde OneDrive hacia Cloud
Storage. Power Apps y Power Automate intercambian identificadores, metadatos,
estado y el Excel final.

## Carpeta operativa

La carpeta operativa inicial es `/auto-tasaciones`. La galería de la app solo
mostrará elementos con extensión `.zip`; por eso el operador no podrá elegir un
resultado Excel anterior.

Como mejora operativa posterior se pueden separar `entrada/` y `salida/`, pero
no es un requisito para iniciar: el resultado se guarda en la carpeta padre del
ZIP seleccionado y se nombra `Resultado_Final_<ID_LOTE>.xlsx`. Nunca se
sobrescribe otro resultado en ejecución.

La carpeta debe mantenerse acotada. Si en el futuro se usa el selector de
archivos integrado del conector, este puede mostrar como máximo 200 elementos.
La galería consultará una carpeta de trabajo y los lotes terminados se moverán o
archivarán periódicamente.

## Aplicación Power Apps

La pantalla deja de cargar archivos. Se retiran el formulario de adjuntos,
`ControlAdjuntos`, el botón **Cargar Zip** y la variable `varZipSubido`.

Se incorporan estos controles:

| Control | Responsabilidad |
| --- | --- |
| `galZips` | Lista los ZIP de la carpeta con nombre, tamaño y fecha de modificación. |
| `btnActualizar` | Vuelve a consultar la carpeta de OneDrive. |
| `btnEjecutar` | Solo se habilita cuando existe un ZIP seleccionado y registra el lote. |
| `galLotes` o etiqueta de estado | Muestra el identificador y estado del lote enviado. |

`btnEjecutar` invoca un flujo nuevo llamado provisionalmente
`auto-tasacion-iniciar-lote`. Debe enviar el identificador del elemento
seleccionado y sus metadatos, nunca `Value`, `contentBytes` ni ningún campo que
contenga el ZIP.

La fórmula exacta se configura después de agregar el origen **OneDrive for
Business** y el flujo a la aplicación, para que Power Apps inserte los nombres
reales de columnas y parámetros. La intención funcional es equivalente a:

```text
auto-tasacion-iniciar-lote.Run(
  identificador del elemento,
  nombre,
  tamaño,
  carpeta de resultado
)
```

## Flujo `auto-tasacion-iniciar-lote`

### Entrada del disparador Power Apps (V2)

| Parámetro | Uso |
| --- | --- |
| `ItemId` | Identificador del ZIP seleccionado. |
| `Nombre` | Nombre mostrado al operador; se valida contra metadatos. |
| `TamanoBytes` | Tamaño mostrado y validado antes de registrar el lote. |
| `CarpetaResultadoId` | Carpeta padre en la que se entregará el Excel. |

### Acciones

1. **Obtener metadatos de archivo** usando `ItemId`; validar extensión `.zip`,
   tamaño máximo de 2 GiB y que pertenece a la carpeta autorizada.
2. **Resolver referencia de Microsoft Graph**: obtener `driveId`, `itemId` y
   `eTag` del mismo archivo. Si el conector OneDrive no expone alguno de estos
   valores, esta resolución se hará en la API de control a partir del
   identificador validado; no se sustituye por una URL pública ni por una ruta
   no validada.
3. **HTTP POST a la API de control** con JSON pequeño:

   ```json
   {
     "drive_id": "<driveId>",
     "item_id": "<itemId>",
     "etag": "<eTag>",
     "nombre": "lote-tasaciones.zip",
     "tamano_bytes": 734003200,
     "carpeta_resultado_id": "<folderId>"
   }
   ```

4. **Responder a Power Apps** de inmediato con `id_lote`, `estado=RECIBIDO` y
   el nombre del ZIP. No espera a que termine la extracción.

Este flujo no debe contener **Obtener contenido de archivo**, **HTTP: Subir
ZIP**, una URL firmada para que Power Automate cargue el ZIP, ni la acción
actual **Procesar carga**. Esas acciones trasladan el binario por Power
Automate y son incompatibles con el objetivo de 1 GiB o más.

## Consulta y entrega del resultado

La ejecución no mantiene una llamada de Power Apps abierta. Un segundo flujo,
`auto-tasacion-consultar-lote`, recibe `id_lote`, consulta `GET
/v1/lotes/{id_lote}` y devuelve estado, avance y mensaje seguro para el
operador. La aplicación lo invoca mediante un temporizador mientras haya un
lote activo.

Al llegar a `COMPLETADO`, un flujo de entrega obtiene el XLSX desde el resultado
privado autorizado y usa **Crear archivo** de OneDrive para escribir:

```text
<carpeta del ZIP>/Resultado_Final_<ID_LOTE>.xlsx
```

La entrega marca el lote como confirmado. Recién entonces la retención puede
eliminar los objetos temporales de GCS. La posterior ejecución de PAD recibe la
ruta de ese Excel y procesa solo `tblParaProcesar`.

## Contrato de la API de control

| Operación | Método | Respuesta mínima |
| --- | --- | --- |
| Crear lote | `POST /v1/lotes` | `id_lote`, `estado`, `clave_idempotencia` |
| Consultar lote | `GET /v1/lotes/{id_lote}` | `estado`, `avance`, `mensaje`, `resultado_disponible` |
| Confirmar entrega | `POST /v1/lotes/{id_lote}/entrega` | `estado=ENTREGADO` |

La clave de idempotencia es `driveId:itemId:eTag`. Si el mismo archivo se envía
dos veces sin cambios, se devuelve el mismo lote en vez de crear dos Jobs. El
Job valida el `eTag` antes y después de la descarga; un cambio produce
`FALLIDO_ORIGEN_CAMBIO` y no se procesa una versión parcial del ZIP.

## Estados visibles

| Estado | Significado para operación |
| --- | --- |
| `RECIBIDO` | El lote fue registrado. |
| `COPIANDO_A_GCS` | El Job descarga el ZIP desde OneDrive. |
| `EN_PROCESO` | Se extraen y validan los PDFs. |
| `COMPLETADO` | El Excel está listo para entrega. |
| `ENTREGADO` | El Excel fue creado en OneDrive. |
| `FALLIDO` | Hay un error técnico recuperable o escalable. |
| `FALLIDO_ORIGEN_CAMBIO` | El ZIP cambió mientras se copiaba; debe reenviarse. |

## Migración desde el flujo vigente

El flujo actual contiene estas acciones: **Obtener contenido de archivo**,
**HTTP - Iniciar carga**, **HTTP: Subir ZIP**, **HTTP - Procesar carga** y
**Crear archivo**. Se conserva sin cambios para el servicio vigente de hasta
90 MB mientras se construye y valida la ruta asíncrona.

La ruta de lotes masivos se publica como un flujo y botones separados. Después
de una prueba E2E aprobada con un ZIP sintético de 1.4 GB y 300 PDFs, la
aplicación puede dirigir todos los ZIP a la ruta nueva y el flujo binario actual
se retira.

## Dependencias antes de editar Power Platform

1. Implementar y proteger la API de control y los endpoints de estado.
2. Crear el Cloud Run Job y su estado persistente.
3. Aprobar una aplicación Microsoft Entra con lectura limitada a la carpeta o
   biblioteca operativa mediante permisos Selected.
4. Configurar las identidades del Job y de la API con privilegios mínimos en
   Cloud Storage y Cloud Run Jobs.
5. Definir la política de retención de ZIP, resultado y estado.

Hasta cumplir esas dependencias, la aplicación no debe apuntar a este nuevo
flujo: registraría lotes que todavía no pueden procesarse.

