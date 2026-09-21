function procesarYClasificarTasaciones() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var entrada = ss.getSheetByName(CONFIG.SHEET_ENTRADA);
  if (!entrada || entrada.getLastRow() < 2) {
    Browser.msgBox("Primero escanea la carpeta y confirma que hay PDFs.", Browser.Buttons.OK);
    return;
  }
  ss.toast("Extrayendo campos de tasación desde Cloud Run…", "Procesamiento");
  try {
    var response = UrlFetchApp.fetch(CONFIG.CLOUD_FUNCTION_URL, {
      method: "post", contentType: "application/json",
      payload: JSON.stringify({ filas: entrada.getDataRange().getValues() }),
      muteHttpExceptions: true
    });
    var data = JSON.parse(response.getContentText());
    if (response.getResponseCode() !== 200 || data.status !== "success") {
      throw new Error(data.mensaje || "Cloud Run respondió HTTP " + response.getResponseCode());
    }
    var revision = obtenerOCrearPestaña(ss, CONFIG.SHEET_REVISION);
    var banco = obtenerOCrearPestaña(ss, CONFIG.SHEET_BANCO);
    prepararResultados(revision);
    prepararResultados(banco);
    var observados = [], validados = [];
    data.resultados.forEach(function (result) {
      var row = resultadoAFila(result);
      if (result.observacion_extraccion) {
        row.push("Pendiente de revisión");
        observados.push(row);
      } else {
        row.push("Validado automáticamente");
        validados.push(row);
      }
    });
    escribirFilas(revision, observados);
    escribirFilas(banco, validados);
    formatearPestañaCompleta(revision, true);
    formatearPestañaCompleta(banco, false);
    ss.setActiveSheet(observados.length ? revision : banco);
    Browser.msgBox("Análisis finalizado", "Validados: " + validados.length + "\nPendientes de revisión: " + observados.length, Browser.Buttons.OK);
  } catch (error) {
    Browser.msgBox("Error de procesamiento: " + error, Browser.Buttons.OK);
  }
}

function resultadoAFila(result) {
  return [
    result.id_codigo_pdf, result.pdf_archivo, result.pdf_original_drive, result.drive_file_id,
    result.drive_modificado, result.direccion_extraida, result.pagina_direccion,
    result.tipo_inmueble, result.tipo_inmueble_texto, result.pagina_tipo_inmueble,
    result.valor_elegido_tipo, result.valor_elegido_usd, result.valor_elegido_pen,
    result.valor_comercial_usd, result.valor_comercial_pen, result.pagina_valor_comercial,
    result.valor_reconstruccion_usd, result.valor_reconstruccion_pen, result.pagina_valor_reconstruccion,
    result.anio_construccion, result.pagina_anio_construccion, result.nro_pisos_edificio,
    result.nro_sotanos_edificio, result.pagina_pisos_sotanos, result.observacion_extraccion
  ];
}

function prepararResultados(sheet) {
  sheet.clear();
  sheet.getRange(1, 1, 1, CONFIG.RESULT_HEADERS.length).setValues([CONFIG.RESULT_HEADERS]);
}

function escribirFilas(sheet, rows) {
  if (rows.length) sheet.getRange(2, 1, rows.length, CONFIG.RESULT_HEADERS.length).setValues(rows);
}

function formatearPestañaCompleta(sheet, esRevision) {
  var columns = CONFIG.RESULT_HEADERS.length;
  sheet.getDataRange().setFontFamily("Segoe UI").setFontSize(10);
  sheet.getRange(1, 1, 1, columns).setBackground("#1F2937").setFontColor("#FFFFFF").setFontWeight("bold");
  sheet.setFrozenRows(1);
  sheet.setRowHeight(1, 32);
  sheet.autoResizeColumns(1, columns);
  sheet.setColumnWidth(6, 300);
  sheet.setColumnWidth(25, 300);
  if (sheet.getLastRow() > 1) {
    sheet.getRange(2, 1, sheet.getLastRow() - 1, columns)
      .setBackground(esRevision ? "#FEF3C7" : "#ECFDF5");
  }
}

// Crea un archivo Excel descargable sin macros. La macro NT3270 debe vivir en
// su plantilla .xlsm; Excel no conserva VBA al exportar un Google Sheet a xlsx.
function exportarResultadosAExcel() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var origen = ss.getSheetByName(CONFIG.SHEET_BANCO);
  if (!origen || origen.getLastRow() < 2) {
    Browser.msgBox("No hay casos validados para exportar.", Browser.Buttons.OK);
    return;
  }
  var temporal = SpreadsheetApp.create("Exportación tasaciones " + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyyMMdd_HHmmss"));
  var destino = temporal.getSheets()[0];
  var values = origen.getDataRange().getValues().map(function (row) { return row.slice(0, CONFIG.RESULT_HEADERS.length - 1); });
  destino.getRange(1, 1, values.length, values[0].length).setValues(values);
  destino.setFrozenRows(1);
  destino.getRange(1, 1, 1, values[0].length).setFontWeight("bold");
  destino.autoResizeColumns(1, values[0].length);
  var xlsx = DriveApp.getFileById(temporal.getId()).getBlob().getAs(MimeType.MICROSOFT_EXCEL)
    .setName(temporal.getName() + ".xlsx");
  var file = DriveApp.createFile(xlsx);
  Browser.msgBox("Excel creado", "Descárgalo desde Drive: " + file.getUrl(), Browser.Buttons.OK);
}
