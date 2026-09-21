var FOLDER_ID = "1eBW9eN4qpe2dMy9S65h_8Njebv28rDWZ";

function abrirPanelCargaPDFs() {
  var html = HtmlService.createTemplateFromFile("CargaPDFs").evaluate()
    .setTitle("Cargar PDFs de tasación")
    .setWidth(430);
  SpreadsheetApp.getUi().showSidebar(html);
}

// Se invoca una vez por archivo desde CargaPDFs.html. La carga secuencial
// permite procesar lotes grandes sin superar el límite de una sola solicitud.
function cargarPdfEnDrive(upload) {
  if (!upload || !upload.nombre || !upload.base64) {
    throw new Error("No se recibió un archivo válido.");
  }
  var nombre = String(upload.nombre).replace(/[\\/]/g, "_").trim();
  var extensionPdf = /\.pdf$/i.test(nombre);
  if (!extensionPdf) throw new Error("Solo se permiten archivos PDF.");

  var bytes = Utilities.base64Decode(String(upload.base64));
  var maxBytes = CONFIG.MAX_TAMANO_PDF_MB * 1024 * 1024;
  if (!bytes.length || bytes.length > maxBytes) {
    throw new Error("El archivo supera el máximo de " + CONFIG.MAX_TAMANO_PDF_MB + " MB.");
  }
  if (bytes.length < 5 || bytes[0] !== 37 || bytes[1] !== 80 || bytes[2] !== 68 || bytes[3] !== 70 || bytes[4] !== 45) {
    throw new Error("El contenido no corresponde a un PDF válido.");
  }

  var folder = DriveApp.getFolderById(FOLDER_ID);
  var existing = folder.getFilesByName(nombre);
  if (existing.hasNext()) {
    return { estado: "omitido", nombre: nombre, mensaje: "Ya existe un archivo con este nombre." };
  }
  var blob = Utilities.newBlob(bytes, MimeType.PDF, nombre);
  var file = folder.createFile(blob);
  return { estado: "cargado", nombre: file.getName(), fileId: file.getId() };
}

function finalizarCargaDeLote() {
  escanearCarpetaPDFs();
  return { mensaje: "Panel de entrada actualizado." };
}

function escanearCarpetaPDFs() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = obtenerOCrearPestaña(ss, CONFIG.SHEET_ENTRADA);
  sheet.clear();
  var headers = ["PDF_Archivo", "Drive_File_ID", "Drive_Modificado"];
  var rows = [];

  try {
    var files = DriveApp.getFolderById(FOLDER_ID).getFilesByType(MimeType.PDF);
    while (files.hasNext()) {
      var file = files.next();
      rows.push([file.getName(), file.getId(), file.getLastUpdated().toISOString()]);
    }
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    if (rows.length) sheet.getRange(2, 1, rows.length, headers.length).setValues(rows);
    sheet.hideColumns(2);
    formatearEntrada(sheet);
    ss.setActiveSheet(sheet);
    ss.toast("Se detectaron " + rows.length + " PDFs listos para procesar.", "Google Drive conectado");
  } catch (error) {
    Browser.msgBox("Error al acceder a Google Drive: " + error, Browser.Buttons.OK);
  }
}

function obtenerOCrearPestaña(ss, name) {
  return ss.getSheetByName(name) || ss.insertSheet(name);
}

function formatearEntrada(sheet) {
  sheet.getDataRange().setFontFamily("Segoe UI").setFontSize(10);
  sheet.getRange(1, 1, 1, 3).setBackground("#1F2937").setFontColor("#FFFFFF").setFontWeight("bold");
  sheet.setFrozenRows(1);
  sheet.setColumnWidth(1, 300);
  sheet.setColumnWidth(2, 110);
  sheet.setColumnWidth(3, 180);
}
