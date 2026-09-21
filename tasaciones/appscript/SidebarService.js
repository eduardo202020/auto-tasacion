function abrirPanelRevision() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.SHEET_REVISION);
  if (!sheet) {
    SpreadsheetApp.getUi().alert("Ejecute el procesamiento antes de abrir la revisión.");
    return;
  }
  SpreadsheetApp.getActiveSpreadsheet().setActiveSheet(sheet);
  SpreadsheetApp.getUi().showSidebar(HtmlService.createHtmlOutputFromFile("PanelRevision")
    .setTitle("Revisión de tasaciones").setWidth(350));
}

function indiceColumna(headers, name) {
  var index = headers.indexOf(name);
  if (index < 0) throw new Error("No existe la columna requerida: " + name);
  return index;
}

function obtenerSiguienteCasoPendiente() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.SHEET_REVISION);
  if (!sheet || sheet.getLastRow() < 2) return null;
  var values = sheet.getDataRange().getValues();
  var headers = values[0];
  var obs = indiceColumna(headers, "Observacion extraccion");
  var state = indiceColumna(headers, "Estado");
  var address = indiceColumna(headers, "Direccion extraida");
  var type = indiceColumna(headers, "Tipo inmueble");
  var page = indiceColumna(headers, "Pagina direccion");
  for (var row = 1; row < values.length; row++) {
    if (String(values[row][obs]).trim() && !String(values[row][state]).includes("Validado")) {
      sheet.setActiveRange(sheet.getRange(row + 1, 1, 1, headers.length));
      return {
        fila: row + 1, direccion: values[row][address], tipo: values[row][type],
        observacion: values[row][obs],
        sugerencia: "Revise la evidencia indicada en la página " + (values[row][page] || "correspondiente") + "."
      };
    }
  }
  return null;
}

function aplicarCorreccionFila(fila, tipoCorregido) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var revision = ss.getSheetByName(CONFIG.SHEET_REVISION);
  var banco = obtenerOCrearPestaña(ss, CONFIG.SHEET_BANCO);
  var headers = revision.getRange(1, 1, 1, revision.getLastColumn()).getValues()[0];
  var values = revision.getRange(fila, 1, 1, headers.length).getValues()[0];
  var state = indiceColumna(headers, "Estado");
  if (tipoCorregido) {
    var type = indiceColumna(headers, "Tipo inmueble");
    values[type] = tipoCorregido;
    var chosenType = indiceColumna(headers, "Valor elegido tipo");
    var chosenUsd = indiceColumna(headers, "Valor elegido US$");
    var chosenPen = indiceColumna(headers, "Valor elegido S/");
    var source = tipoCorregido === "CASA" ? "reconstruccion" : "comercial";
    values[chosenType] = tipoCorregido === "CASA" ? "VALOR DE RECONSTRUCCION" : "VALOR COMERCIAL";
    values[chosenUsd] = values[indiceColumna(headers, "Valor " + source + " US$")];
    values[chosenPen] = values[indiceColumna(headers, "Valor " + source + " S/")];
  }
  values[state] = "Validado y aprobado por operador";
  revision.getRange(fila, 1, 1, headers.length).setValues([values]).setBackground("#D1FAE5");
  if (banco.getLastRow() === 0) prepararResultados(banco);
  banco.appendRow(values);
  formatearPestañaCompleta(banco, false);
  SpreadsheetApp.flush();
}
