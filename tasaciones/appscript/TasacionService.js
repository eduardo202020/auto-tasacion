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
    "", // Nro Préstamo
    result.id_codigo_pdf, result.pdf_archivo, result.pdf_original_drive, result.drive_file_id,
    result.drive_modificado, result.direccion_extraida, result.pagina_direccion,
    result.tipo_via_1, result.domicilio_1, result.n_exterior, result.n_interior, result.referencia,
    result.ubicacion_tipo, result.ubicacion_1, result.distrito, result.provincia, result.departamento,
    result.tipo_inmueble, result.tipo_inmueble_texto, result.pagina_tipo_inmueble,
    result.valor_elegido_tipo, result.valor_elegido_usd, result.valor_elegido_pen,
    result.valor_comercial_usd, result.valor_comercial_pen, result.pagina_valor_comercial,
    result.valor_reconstruccion_usd, result.valor_reconstruccion_pen, result.pagina_valor_reconstruccion,
    result.anio_construccion, result.pagina_anio_construccion, result.nro_pisos_edificio,
    result.nro_sotanos_edificio, result.pagina_pisos_sotanos,
    result.distrito_cod, result.tipo_masivo_cod, result.provincia_cod, result.departamento_cod, result.clase_banco,
    result.sugerencia_ia, result.observacion_extraccion
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
        add(7, row[7]);
        add(19, row[20]); // Tipo inmueble
        add(22, row[20]); // Valor elegido tipo
        add(23, row[26] || row[29]);
        add(24, row[26] || row[29]);
        add(25, row[26]);
        add(26, row[26]);
        add(28, row[29]);
        add(29, row[29]);
        add(31, row[31]);
        add(33, row[34]);
        add(34, row[34]);


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
  
  // MAPEO EXACTO PARA LA MACRO "MASIVO"
  // Col A: Préstamo (row[0])
  // Col C: Valor Bien (row[22] o row[23] - Valor elegido US$ / S/)
  // Col E: Importe (Suele ser igual al valor del bien o manual, se deja espacio)
  // Col G: Dirección (row[8] - TIPO VIA 1)
  // Col H: Dirección1 (row[9] - DOMICILIO 1)
  // Col I: N Exterior (row[10])
  // Col J: N Interior (row[11])
  // Col K: Referencia (row[12])
  // Col M: Ubicación (row[13] - UBICACION TIPO)
  // Col N: Ubicación1 (row[14] - UBICACION 1)
  // Col O: Municipio (row[15] - DISTRITO)
  // Col P: CodDistrito (row[15] - DISTRITO para que el usuario valide)
  // Col R: CodProvincia (row[16] - PROVINCIA)
  // Col T: CodDepartamento (row[17] - DEPARTAMENTO)
  // Col U: Clase Inmueble (row[18] - Tipo Inmueble)
  // Col V: Pisos (row[32])
  // Col W: Sótanos (row[33])
  // Col X: Año (row[30])
  
  var sourceRows = origen.getRange(2, 1, origen.getLastRow() - 1, headers.length).getValues();
  
    var rowsParaMasivo = sourceRows.map(function(row) {
      var output = Array(25).fill(""); // De A hasta Y
      output[0] = row[0];  // Col A: Préstamo
      output[1] = row[36]; // Col B: TIPO_MASIVO_COD (C/N)
      output[2] = row[22]; // Col C: Valor Bien (US$ elegido)
      output[4] = row[22]; // Col E: Importe (Default al valor del bien)
      output[6] = row[8];  // Col G: TIPO VIA 1
      output[7] = row[9];  // Col H: DOMICILIO 1
      output[8] = row[10]; // Col I: N EXTERIOR
      output[9] = row[11]; // Col J: N INTERIOR
      output[10] = row[12]; // Col K: REFERENCIA
      output[12] = row[13]; // Col M: UBICACION TIPO
      output[13] = row[14]; // Col N: UBICACION 1
      output[14] = row[15]; // Col O: Municipio (Nombre Distrito)
      output[15] = row[35]; // Col P: DISTRITO_COD (CÓDIGO NUMÉRICO)
      output[17] = row[37]; // Col R: PROVINCIA_COD (CÓDIGO NUMÉRICO)
      output[19] = row[38]; // Col T: DEPARTAMENTO_COD (CÓDIGO NUMÉRICO)
      output[20] = row[39]; // Col U: CLASE_COD (1, 2, 3 según pisos)
      output[21] = row[32]; // Col V: Pisos
      output[22] = row[33]; // Col W: Sótanos
      output[23] = row[30]; // Col X: Año
      return output;
    });



  var temporal = SpreadsheetApp.create("Para Macro Masivo " + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyyMMdd_HHmmss"));
  var destino = temporal.getSheets()[0];
  destino.setName("MASIVO");
  
  // Encabezados para que el usuario se guíe (aunque la macro usa índices)
  var masivoHeaders = Array(25).fill("");
  masivoHeaders[0] = "PRESTAMO"; masivoHeaders[2] = "VALOR_BIEN"; masivoHeaders[4] = "IMPORTE";
  masivoHeaders[6] = "DIRECCION"; masivoHeaders[7] = "DIRECCION1"; masivoHeaders[8] = "EXTERIOR";
  masivoHeaders[9] = "INTERIOR"; masivoHeaders[10] = "REFERENCIA"; masivoHeaders[12] = "UBICACION";
  masivoHeaders[13] = "UBICACION1"; masivoHeaders[14] = "MUNICIPIO"; masivoHeaders[15] = "DIST_COD";
  masivoHeaders[17] = "PROV_COD"; masivoHeaders[19] = "DEPT_COD"; masivoHeaders[20] = "CLASE";
  masivoHeaders[21] = "PISOS"; masivoHeaders[22] = "SOTANOS"; masivoHeaders[23] = "AÑO";
  
    var values = [masivoHeaders].concat(rowsParaMasivo);
  destino.getRange(1, 1, values.length, 25).setValues(values);

  destino.setFrozenRows(1);
  destino.getRange(1, 1, 1, 25).setFontWeight("bold");
  destino.autoResizeColumns(1, 25);

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
