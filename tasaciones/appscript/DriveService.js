var FOLDER_ID = "1eBW9eN4qpe2dMy9S65h_8Njebv28rDWZ";

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
