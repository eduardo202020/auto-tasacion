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
    result.nro_sotanos_edificio, result.pagina_pisos_sotanos, result.sugerencia_ia,
    result.observacion_extraccion
  ];
}

function prepararResultados(sheet) {
  sheet.clear();
  sheet.getRange(1, 1, 1, CONFIG.RESULT_HEADERS.length).setValues([CONFIG.RESULT_HEADERS]);
}

function escribirFilas(sheet, rows) {
  if (!rows.length) return;
  var range = sheet.getRange(2, 1, rows.length, CONFIG.RESULT_HEADERS.length);
  range.setValues(rows);
  agregarNotasDeFuente(range, rows);
}

function agregarNotasDeFuente(range, rows) {
  var notes = rows.map(function (row) {
    var noteRow = Array(CONFIG.RESULT_HEADERS.length).fill("");
    var pdfName = row[1] || row[0] || "PDF";
    var fileId = String(row[3] || "").trim();
    var fileUrl = fileId ? "https://drive.google.com/open?id=" + fileId : "";
    var source = function (page) {
      if (!page) return "";
      return "Fuente: " + pdfName + "\nPágina del PDF: " + page +
        (fileUrl ? "\nAbrir PDF: " + fileUrl : "");
    };
    var add = function (column, page) {
      var note = source(page);
      if (note) noteRow[column - 1] = note;
    };
    add(6, row[6]);
    add(8, row[9]);
    add(11, row[9]);
    add(12, row[15] || row[18]);
    add(13, row[15] || row[18]);
    add(14, row[15]);
    add(15, row[15]);
    add(17, row[18]);
    add(18, row[18]);
    add(20, row[20]);
    add(22, row[23]);
    add(23, row[23]);
    return noteRow;
  });
  range.setNotes(notes);
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
    var dataRange = sheet.getRange(2, 1, sheet.getLastRow() - 1, columns);
    var values = dataRange.getValues();
    var backgrounds = values.map(function (row) {
      return row.map(function (value) {
        return esRevision && String(value).trim() === "" ? "#FECACA" : (esRevision ? "#FEF3C7" : "#ECFDF5");
      });
    });
    dataRange.setBackgrounds(backgrounds);
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
  var headers = origen.getRange(1, 1, 1, origen.getLastColumn()).getValues()[0];
  var stateIndex = indiceColumna(headers, "Estado");
  var exportHeaders = [
    "ID / Codigo PDF", "PDF_Archivo", "PDF_Original_Drive", "Drive_File_ID",
    "Drive_Modificado", "Direccion extraida", "Pagina direccion", "Tipo inmueble",
    "Tipo inmueble texto", "Pagina tipo inmueble", "Valor elegido tipo", "Valor elegido US$",
    "Valor elegido S/", "Valor comercial US$", "Valor comercial S/", "Pagina valor comercial",
    "Valor reconstruccion US$", "Valor reconstruccion S/", "Pagina valor reconstruccion",
    "Año construccion", "Pagina año construccion", "Nro pisos edificio", "Nro sotanos edificio",
    "Pagina pisos/sotanos", "Observacion extraccion"
  ];
  var exportIndexes = exportHeaders.map(function (header) { return indiceColumna(headers, header); });
  var sourceRows = origen.getRange(2, 1, origen.getLastRow() - 1, headers.length).getValues();
  var invalidRows = sourceRows.filter(function (row) {
    return row.some(function (value) { return String(value).trim(); }) && !String(row[stateIndex]).includes("Validado");
  });
  if (invalidRows.length) {
    Browser.msgBox("No se puede exportar", "Hay " + invalidRows.length + " caso(s) no validados en Listos para el Banco.", Browser.Buttons.OK);
    return;
  }
  var rows = sourceRows.filter(function (row) {
    return row.some(function (value) { return String(value).trim(); });
  }).map(function (row) {
    return exportIndexes.map(function (index) { return row[index]; });
  });
  if (!rows.length) {
    Browser.msgBox("No hay casos validados para exportar.", Browser.Buttons.OK);
    return;
  }
  var temporal = SpreadsheetApp.create("Exportación tasaciones " + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyyMMdd_HHmmss"));
  var destino = temporal.getSheets()[0];
  var values = [exportHeaders].concat(rows);
  destino.getRange(1, 1, values.length, exportHeaders.length).setValues(values);
  destino.setFrozenRows(1);
  destino.getRange(1, 1, 1, exportHeaders.length).setFontWeight("bold");
  destino.autoResizeColumns(1, exportHeaders.length);
  var exportUrl = "https://www.googleapis.com/drive/v3/files/" + temporal.getId() +
    "/export?mimeType=" + encodeURIComponent(MimeType.MICROSOFT_EXCEL);
  var exportResponse = UrlFetchApp.fetch(exportUrl, {
    headers: { Authorization: "Bearer " + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true
  });
  if (exportResponse.getResponseCode() !== 200) {
    DriveApp.getFileById(temporal.getId()).setTrashed(true);
    throw new Error("Drive no pudo convertir la hoja a XLSX: " + exportResponse.getContentText());
  }
  var xlsx = exportResponse.getBlob().setName(temporal.getName() + ".xlsx");
  var file = DriveApp.createFile(xlsx);
  DriveApp.getFileById(temporal.getId()).setTrashed(true);
  var downloadUrl = file.getDownloadUrl();
  var dialog = HtmlService.createHtmlOutput(
    '<div style="font-family:Arial,sans-serif;padding:18px;line-height:1.5">' +
    '<h3>Excel listo para el banco</h3>' +
    '<p>La hoja fue validada y el archivo contiene únicamente los casos aprobados.</p>' +
    '<a href="' + downloadUrl + '" target="_blank" style="display:inline-block;padding:10px 14px;background:#2563eb;color:#fff;text-decoration:none;border-radius:5px">Descargar Excel</a>' +
    '<p style="font-size:12px;color:#6b7280">El archivo también quedó guardado en Google Drive.</p>' +
    '</div>'
  ).setWidth(420).setHeight(210);
  SpreadsheetApp.getUi().showModalDialog(dialog, "Exportación completada");
}
