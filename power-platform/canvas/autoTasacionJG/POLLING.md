# Seguimiento visual y tiempo de lote en `autoTasacionJG`

## Alcance y fuente de verdad

La ruta masiva ya conserva el estado técnico del lote y la aplicación consulta
`auto-tasacion-consultar-lote` periódicamente. Esta guía extiende esa consulta:
no agrega flujos, no cambia las recurrencias y no envía contenido de PDF a
Power Apps.

Los cambios de backend persisten `fecha_inicio` al registrar el lote y
`fecha_fin` una sola vez cuando alcanza `ENTREGADO`, `FALLIDO` o
`FALLIDO_ORIGEN_CAMBIO`. La respuesta tipada de consulta contiene además
`duracion_segundos`.

La CLI disponible no puede actualizar ni publicar una Canvas App existente.
Por ello las propiedades de esta guía se aplican en Power Apps Studio y deben
publicarse allí. Usa el Timer de polling existente; en la guía anterior se
llama `tmrEstadoLote`. Si su nombre difiere en Studio, aplica las propiedades
al control que ya invoca `auto-tasacion-consultar-lote`.

Las fórmulas usan `;` para argumentos y `;;` para encadenar acciones, que es
la sintaxis de la aplicación con locale `es-ES`.

## Contrato y estados

Power Apps recibe estos campos sin rutas GCS, archivos ni URLs firmadas:

```text
id_lote, estado, mensaje, total_pdfs, pdfs_cargados, pdfs_procesados,
pdfs_fallidos, resultado_disponible, fecha_inicio, fecha_fin,
duracion_segundos
```

| Estado técnico | Paso visible | Tratamiento |
| --- | --- | --- |
| `RECIBIDO` | Lote recibido | Paso activo 1. |
| `CARGANDO_PDFS` | Cargando documentos | Paso activo 2. |
| `LISTO_PARA_PROCESAR`, `EN_PROCESO` | Procesando tasaciones | Paso activo 3. |
| `COMPLETADO` | Resultado generado | Paso activo 4; la entrega sigue pendiente. |
| `ENTREGADO` | Entregado | Los cinco pasos quedan completados. |
| `FALLIDO_ORIGEN_CAMBIO` | Cargando documentos | Paso 2 en rojo. |
| `FALLIDO` | Cargando documentos o Procesando tasaciones | Rojo en el paso 2 si aún faltaban cargas; de otro modo en el paso 3. |

## Inicialización de pantalla

En `Screen1.OnVisible`, **agrega** estas acciones al final de la fórmula actual;
no reemplaces la lógica que lista PDFs:

```powerfx
ClearCollect(
    colPasosLote;
    Table(
        {Orden: 1; Texto: "Lote recibido"};
        {Orden: 2; Texto: "Cargando documentos"};
        {Orden: 3; Texto: "Procesando tasaciones"};
        {Orden: 4; Texto: "Resultado generado"};
        {Orden: 5; Texto: "Entregado"}
    )
);;
Set(varPasoActivo; 0);;
Set(varPasoError; Blank());;
Set(varBlinkPasoActivo; true);;
Set(varInicioProceso; Blank());;
Set(varFinProceso; Blank());;
Set(varAhoraProceso; Now())
```

Conserva `btnActualizar` exclusivamente para actualizar `colPdfs`.

## Boton **Ejecutar** (`Button5.OnSelect`)

Reemplaza la propiedad `OnSelect` por esta formula. Mantiene la seleccion
multiple existente, crea solo el manifiesto y deja la transferencia de cada PDF
al flujo programado.

```powerfx
If(
    CountRows(Filter(colPdfs; Seleccionado)) = 0;
    Notify("Seleccione al menos un PDF."; NotificationType.Warning);
    Set(
        varLote;
        IfError(
            'auto-tasacion-iniciar-lote'.Run(
                JSON(
                    ForAll(
                        Filter(colPdfs; Seleccionado);
                        {
                            item_id: ItemId;
                            nombre: Nombre;
                            tamano_bytes: Tamano;
                            etag: ETag
                        }
                    );
                    JSONFormat.Compact
                )
            );
            Blank()
        )
    );;
    If(
        IsBlank(varLote.id_lote);
        Notify("No se pudo registrar el lote. Intentelo nuevamente."; NotificationType.Error);
        Set(varIdLote; varLote.id_lote);;
        Set(varEstadoLote; varLote.estado);;
        Set(varTotalPdfs; CountRows(Filter(colPdfs; Seleccionado)));;
        Set(varPdfsCargados; 0);;
        Set(varPdfsProcesados; 0);;
        Set(varPdfsFallidos; 0);;
        Set(varMensajeLote; Blank());;
        Set(varResultadoDisponible; false);;
        Set(varFechaInicioProceso; varLote.fecha_inicio);;
        Set(varFechaFinProceso; Blank());;
        Set(varInicioProceso; DateTimeValue(varFechaInicioProceso));;
        Set(varFinProceso; Blank());;
        Set(varAhoraProceso; Now());;
        Set(varDuracionProceso; 0);;
        Set(varPasoActivo; 1);;
        Set(varPasoError; Blank());;
        Set(varBlinkPasoActivo; true);;
        Set(varErrorConsultaReportado; false);;
        Set(varMonitorearLote; true);;
        Notify(
            "Lote " & varIdLote & " registrado. El seguimiento se actualizara automaticamente.";
            NotificationType.Success
        )
    )
)
```

Despues de publicar el flujo actualizado, vuelve a agregar
`auto-tasacion-iniciar-lote` como origen de datos si `fecha_inicio` no aparece
en IntelliSense. Si `Button5.DisplayMode` ya evita iniciar dos lotes mientras
`varMonitorearLote` esta activo, conservalo.

## Timer de polling (`tmrEstadoLote.OnTimerEnd`)

Mantén las propiedades de polling existentes: `Duration = 10000`, `Repeat =
true`, `Start = varMonitorearLote && !IsBlank(varIdLote)`, `Reset =
!varMonitorearLote` y `Visible = false`.

Reemplaza `OnTimerEnd` por la fórmula siguiente. Conserva el último estado ante
un fallo transitorio de consulta y no confunde ese fallo con un estado real
`FALLIDO`.

```powerfx
If(
    varMonitorearLote && !IsBlank(varIdLote);
    Set(
        varConsultaIntento;
        IfError(
            'auto-tasacion-consultar-lote'.Run(varIdLote);
            Blank()
        )
    );;
    If(
        IsBlank(varConsultaIntento.id_lote);
        If(
            !varErrorConsultaReportado;
            Notify(
                "No se pudo actualizar el estado. Se reintentará automáticamente.";
                NotificationType.Warning
            );;
            Set(varErrorConsultaReportado; true)
        );
        Set(varConsultaLote; varConsultaIntento);;
        Set(varEstadoLote; varConsultaLote.estado);;
        Set(varMensajeLote; varConsultaLote.mensaje);;
        Set(varTotalPdfs; varConsultaLote.total_pdfs);;
        Set(varPdfsCargados; varConsultaLote.pdfs_cargados);;
        Set(varPdfsProcesados; varConsultaLote.pdfs_procesados);;
        Set(varPdfsFallidos; varConsultaLote.pdfs_fallidos);;
        Set(varResultadoDisponible; varConsultaLote.resultado_disponible);;
        Set(varFechaInicioProceso; varConsultaLote.fecha_inicio);;
        Set(varFechaFinProceso; varConsultaLote.fecha_fin);;
        Set(varInicioProceso; DateTimeValue(varFechaInicioProceso));;
        Set(
            varFinProceso;
            If(
                IsBlank(varFechaFinProceso);
                Blank();
                DateTimeValue(varFechaFinProceso)
            )
        );;
        Set(varDuracionProceso; varConsultaLote.duracion_segundos);;
        Set(varAhoraProceso; Now());;
        Set(
            varPasoActivo;
            Switch(
                varEstadoLote;
                "RECIBIDO"; 1;
                "CARGANDO_PDFS"; 2;
                "LISTO_PARA_PROCESAR"; 3;
                "EN_PROCESO"; 3;
                "COMPLETADO"; 4;
                "ENTREGADO"; 5;
                "FALLIDO_ORIGEN_CAMBIO"; 2;
                "FALLIDO"; If(varPdfsCargados < varTotalPdfs; 2; 3);
                0
            )
        );;
        Set(
            varPasoError;
            If(
                varEstadoLote = "FALLIDO_ORIGEN_CAMBIO";
                2;
                varEstadoLote = "FALLIDO";
                If(varPdfsCargados < varTotalPdfs; 2; 3);
                Blank()
            )
        );;
        Set(varErrorConsultaReportado; false);;
        If(
            Or(
                varEstadoLote = "ENTREGADO";
                varEstadoLote = "FALLIDO";
                varEstadoLote = "FALLIDO_ORIGEN_CAMBIO"
            );
            Set(varMonitorearLote; false)
        );;
        If(
            varEstadoLote = "ENTREGADO";
            Notify("El Excel final ya está disponible en OneDrive."; NotificationType.Success)
        );;
        If(
            Or(varEstadoLote = "FALLIDO"; varEstadoLote = "FALLIDO_ORIGEN_CAMBIO");
            Notify(
                Coalesce(varMensajeLote; "El lote terminó con error.");
                NotificationType.Error
            )
        )
    )
)
```

`COMPLETADO` no detiene el polling: el paso 4 permanece activo hasta que el
flujo de entrega persista `ENTREGADO` y `fecha_fin`.

## Stepper visual

Inserta una galería vertical llamada `galPasosLote` y asígnale:

| Propiedad | Valor |
| --- | --- |
| `Items` | `colPasosLote` |
| `TemplateSize` | `52` |
| `ShowScrollbar` | `false` |

Dentro de la galería inserta un círculo `cirPaso`, un texto `lblIconoPaso` y
un texto `lblTextoPaso`. Configura:

### `cirPaso.Fill`

```powerfx
If(
    ThisItem.Orden = varPasoError;
    RGBA(196; 49; 75; 1);
    ThisItem.Orden < varPasoActivo ||
    (varEstadoLote = "ENTREGADO" && ThisItem.Orden = varPasoActivo);
    RGBA(16; 124; 16; 1);
    ThisItem.Orden = varPasoActivo;
    If(
        varBlinkPasoActivo;
        RGBA(16; 124; 16; 1);
        RGBA(107; 175; 107; 1)
    );
    RGBA(166; 166; 166; 1)
)
```

### `lblIconoPaso.Text`

```powerfx
If(
    ThisItem.Orden = varPasoError;
    "×";
    ThisItem.Orden < varPasoActivo ||
    (varEstadoLote = "ENTREGADO" && ThisItem.Orden = varPasoActivo);
    "✓";
    ThisItem.Orden = varPasoActivo;
    "●";
    "○"
)
```

### `lblTextoPaso.Text`

```powerfx
ThisItem.Texto
```

### `lblTextoPaso.Color`

```powerfx
If(
    ThisItem.Orden = varPasoError;
    RGBA(196; 49; 75; 1);
    ThisItem.Orden <= varPasoActivo;
    RGBA(32; 32; 32; 1);
    RGBA(96; 96; 96; 1)
)
```

## Timer visual y contador

Inserta un segundo Timer llamado `tmrVistaLote`. No llama flujos ni actualiza
el lote; solo actualiza la animación y el reloj.

| Propiedad | Valor |
| --- | --- |
| `Duration` | `750` |
| `Repeat` | `true` |
| `AutoStart` | `false` |
| `Start` | `!IsBlank(varInicioProceso) && IsBlank(varFinProceso)` |
| `Reset` | `IsBlank(varInicioProceso) || !IsBlank(varFinProceso)` |
| `Visible` | `false` |
| `OnTimerEnd` | `Set(varBlinkPasoActivo; !varBlinkPasoActivo);; Set(varAhoraProceso; Now())` |

Agrega una etiqueta `lblTiempoLote` con esta propiedad `Text`:

```powerfx
With(
    {
        segundos: If(
            IsBlank(varInicioProceso);
            Blank();
            DateDiff(
                varInicioProceso;
                If(IsBlank(varFinProceso); varAhoraProceso; varFinProceso);
                TimeUnit.Seconds
            )
        )
    };
    If(
        IsBlank(segundos);
        "Tiempo transcurrido: --:--:--";
        "Tiempo " & If(IsBlank(varFinProceso); "transcurrido: "; "total: ") &
        Text(RoundDown(segundos / 3600; 0); "00") & ":" &
        Text(RoundDown(Mod(segundos; 3600) / 60; 0); "00") & ":" &
        Text(Mod(segundos; 60); "00")
    )
)
```

La duración se calcula en la pantalla a partir de las fechas persistidas. El
campo `duracion_segundos` queda disponible como verificación y para mostrar el
último valor servidor si fuera necesario.

## Etiquetas de estado y progreso

En `Label3.Text` muestra un estado amistoso:

```powerfx
"Estado: " & Switch(
    varEstadoLote;
    "RECIBIDO"; "Lote recibido";
    "CARGANDO_PDFS"; "Cargando documentos";
    "LISTO_PARA_PROCESAR"; "Preparando procesamiento";
    "EN_PROCESO"; "Procesando tasaciones";
    "COMPLETADO"; "Resultado generado";
    "ENTREGADO"; "Entregado";
    "FALLIDO"; "Error durante el procesamiento";
    "FALLIDO_ORIGEN_CAMBIO"; "Error al cargar documentos";
    "Sin iniciar"
)
```

Para `lblProgresoLote.Text` usa:

```powerfx
Switch(
    varEstadoLote;
    "CARGANDO_PDFS";
    "Documentos cargados: " & Text(varPdfsCargados) & " / " & Text(varTotalPdfs);
    "LISTO_PARA_PROCESAR";
    "Documentos cargados: " & Text(varPdfsCargados) & " / " & Text(varTotalPdfs) & ". Preparando procesamiento.";
    "EN_PROCESO";
    "Procesando " & Text(varPdfsProcesados) & " de " & Text(varTotalPdfs) & " documentos.";
    "COMPLETADO";
    "Resultado generado. Esperando entrega en OneDrive.";
    "ENTREGADO";
    "Proceso completado correctamente. El Excel está disponible.";
    "FALLIDO";
    Coalesce(varMensajeLote; "El lote terminó con error.");
    "FALLIDO_ORIGEN_CAMBIO";
    Coalesce(varMensajeLote; "Un documento cambió durante la carga.");
    ""
)
```

## Reapertura y compatibilidad

Las fechas viven en el manifiesto de GCS, no solo en variables de la sesión.
Cuando la aplicación vuelve a consultar un `id_lote`, reconstruye
`varInicioProceso`, `varFinProceso` y el tiempo total desde esa respuesta.

Para permitirlo después de cerrar la aplicación sin crear otro flujo, agrega
un cuadro de texto `txtIdLote` con `HintText = "ID de lote para reanudar"` y un
botón `btnReanudarLote`. En su propiedad `OnSelect` usa:

```powerfx
If(
    IsBlank(Trim(txtIdLote.Text));
    Notify("Ingrese un ID de lote."; NotificationType.Warning);
    Set(varIdLote; Trim(txtIdLote.Text));;
    Set(varEstadoLote; Blank());;
    Set(varMensajeLote; Blank());;
    Set(varFechaInicioProceso; Blank());;
    Set(varFechaFinProceso; Blank());;
    Set(varInicioProceso; Blank());;
    Set(varFinProceso; Blank());;
    Set(varPasoActivo; 0);;
    Set(varPasoError; Blank());;
    Set(varMonitorearLote; true)
)
```

El Timer de polling consulta el ID en un maximo de 10 segundos y reconstituye el
stepper y el contador desde los datos persistidos. No se agrego un flujo de
historial: el operador obtiene el ID mostrado al registrar el lote o desde el
nombre del Excel `Resultado_Final_<ID_LOTE>.xlsx`.

## Prueba manual

1. Selecciona dos PDFs y pulsa **Ejecutar**.
2. Confirma que el paso 1 pulsa y el contador inicia en `00:00:00`.
3. Comprueba la progresión de pasos hasta `COMPLETADO` y luego `ENTREGADO` sin
   pulsar **Actualizar**.
4. Confirma que todos los pasos quedan verdes, `varMonitorearLote` es `false` y
   el contador queda fijo al entregarse el Excel.
5. Prueba un lote que termine en `FALLIDO` o `FALLIDO_ORIGEN_CAMBIO`: el paso
   afectado debe mostrarse rojo, el mensaje debe ser visible y el tiempo debe
   quedar congelado.
