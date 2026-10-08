# Seguimiento automático de lote en `autoTasacionJG`

## Estado de la fuente de la aplicación

La fuente descargada el 7 de octubre de 2026 con `pac canvas download` muestra
que la aplicación tiene `Button5` como botón visible **Ejecutar**, `Label3`
como etiqueta de estado y `btnActualizar` para listar los PDFs. `Label3` ya
usa `varEstadoLote`, pero no había temporizador ni conexión a
`auto-tasacion-iniciar-lote` o `auto-tasacion-consultar-lote`; por ello el
estado inicial no se volvía a consultar.

La CLI permite descargar y empaquetar una Canvas App, pero no actualizar ni
publicar una aplicación existente. La exportación de la solución corporativa
`autoTasacion` sigue bloqueada por permisos de lectura sobre un flujo heredado.
Por eso estos cambios se aplican en Power Apps Studio, después de publicar los
dos flujos desde `scripts/deploy-mass-flows.ps1`.

No modifiques `btnActualizar`: continúa dedicado a actualizar `colPdfs`.

## Orígenes de datos

En **Datos**, agrega los flujos publicados:

1. `auto-tasacion-iniciar-lote`.
2. `auto-tasacion-consultar-lote`.

Conserva `auto-tasacion-listar-pdfs`. Al agregar el segundo flujo, Power Apps
recibe sus propiedades tipadas: `id_lote`, `estado`, `mensaje`, `total_pdfs`,
`pdfs_cargados`, `pdfs_procesados`, `pdfs_fallidos` y
`resultado_disponible`.

Las fórmulas siguientes usan `;` como separador de argumentos y `;;` para
encadenar acciones, correspondiente al locale `es-ES` de la aplicación.

## `Button5` — propiedad `OnSelect`

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
        Notify("No se pudo registrar el lote. Inténtelo nuevamente."; NotificationType.Error);
        Set(varIdLote; varLote.id_lote);;
        Set(varEstadoLote; varLote.estado);;
        Set(varTotalPdfs; CountRows(Filter(colPdfs; Seleccionado)));;
        Set(varPdfsCargados; 0);;
        Set(varPdfsProcesados; 0);;
        Set(varPdfsFallidos; 0);;
        Set(varMensajeLote; Blank());;
        Set(varResultadoDisponible; false);;
        Set(varErrorConsultaReportado; false);;
        Set(varMonitorearLote; true);;
        Notify(
            "Lote " & varIdLote & " registrado. El seguimiento se actualizará automáticamente.";
            NotificationType.Success
        )
    )
)
```

Opcionalmente, en `Button5.DisplayMode` usa esta fórmula para evitar iniciar
dos lotes mientras uno sigue activo:

```powerfx
If(
    varMonitorearLote || CountRows(Filter(colPdfs; Seleccionado)) = 0;
    DisplayMode.Disabled;
    DisplayMode.Edit
)
```

## Nuevo temporizador `tmrEstadoLote`

Inserta un control **Timer** clásico y asígnale estas propiedades:

| Propiedad | Valor |
| --- | --- |
| `Duration` | `10000` |
| `Repeat` | `true` |
| `AutoStart` | `false` |
| `Start` | `varMonitorearLote && !IsBlank(varIdLote)` |
| `Reset` | `!varMonitorearLote` |
| `Visible` | `false` |

En `tmrEstadoLote.OnTimerEnd` usa:

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
        );;
        Set(varConsultaLote; varConsultaIntento);;
        Set(varEstadoLote; varConsultaLote.estado);;
        Set(varMensajeLote; varConsultaLote.mensaje);;
        Set(varTotalPdfs; varConsultaLote.total_pdfs);;
        Set(varPdfsCargados; varConsultaLote.pdfs_cargados);;
        Set(varPdfsProcesados; varConsultaLote.pdfs_procesados);;
        Set(varPdfsFallidos; varConsultaLote.pdfs_fallidos);;
        Set(varResultadoDisponible; varConsultaLote.resultado_disponible);;
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

El error de red no modifica `varIdLote` ni `varEstadoLote`, y se notifica solo
una vez hasta que una consulta posterior tenga éxito. `COMPLETADO` no detiene
el temporizador: el monitoreo sigue hasta que el flujo de entrega cambie el
lote a `ENTREGADO`.

## Etiquetas

En `Label3.Text` conserva o aplica:

```powerfx
"Estado: " & Coalesce(varEstadoLote; "Sin iniciar")
```

Para mostrar avance, agrega `lblProgresoLote` con esta propiedad `Text`:

```powerfx
If(
    IsBlank(varIdLote);
    "Progreso: -";
    "Procesados: " & Text(Coalesce(varPdfsProcesados; 0)) &
    " / " & Text(Coalesce(varTotalPdfs; 0)) &
    " | Cargados: " & Text(Coalesce(varPdfsCargados; 0)) &
    " | Fallidos: " & Text(Coalesce(varPdfsFallidos; 0))
)
```

## Publicación y prueba

Guarda y publica la aplicación desde Power Apps Studio. Prueba con `D01.pdf`:
la pantalla debe mostrar `RECIBIDO`, consultar cada diez segundos y conservar
el seguimiento por `CARGANDO_PDFS`, `LISTO_PARA_PROCESAR`, `EN_PROCESO`,
`COMPLETADO` y finalmente `ENTREGADO`. El temporizador se detiene solamente en
`ENTREGADO`, `FALLIDO` o `FALLIDO_ORIGEN_CAMBIO`.
