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

var CAMPOS_REVISION = [
  { header: "Direccion extraida", etiqueta: "Dirección", observacion: "Dirección" },
  { header: "Tipo inmueble", etiqueta: "Tipo de inmueble", observacion: "Tipo de inmueble" },
  { header: "Valor comercial US$", etiqueta: "Valor comercial US$", observacion: "Valor comercial US$" },
  { header: "Valor comercial S/", etiqueta: "Valor comercial S/", observacion: "Valor comercial S/" },
  { header: "Valor reconstruccion US$", etiqueta: "Valor de reconstrucción US$", observacion: "Valor de reconstrucción US$" },
  { header: "Valor reconstruccion S/", etiqueta: "Valor de reconstrucción S/", observacion: "Valor de reconstrucción S/" },
  { header: "Año construccion", etiqueta: "Año de construcción", observacion: "Año de construcción" },
  { header: "Nro pisos edificio", etiqueta: "Número de pisos", observacion: "Número de pisos" },
  { header: "Nro sotanos edificio", etiqueta: "Número de sótanos", observacion: "Número de sótanos" }
];

function campoPendiente(headers, values, observacion) {
  for (var i = 0; i < CAMPOS_REVISION.length; i++) {
    var field = CAMPOS_REVISION[i];
    if (observacion.indexOf(field.observacion) >= 0 || !String(values[indiceColumna(headers, field.header)]).trim()) {
      return field;
    }
  }
  return CAMPOS_REVISION[0];
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
  var suggestion = indiceColumna(headers, "Sugerencia IA");
  for (var row = 1; row < values.length; row++) {
    if (String(values[row][obs]).trim() && !String(values[row][state]).includes("Validado")) {
      var observation = String(values[row][obs]);
      var field = campoPendiente(headers, values[row], observation);
      var fieldIndex = indiceColumna(headers, field.header);
      var pageHeader = field.header === "Direccion extraida" ? "Pagina direccion" :
        field.header === "Tipo inmueble" ? "Pagina tipo inmueble" :
        field.header === "Año construccion" ? "Pagina año construccion" :
        field.header.indexOf("comercial") >= 0 ? "Pagina valor comercial" :
        field.header.indexOf("reconstruccion") >= 0 ? "Pagina valor reconstruccion" :
        "Pagina pisos/sotanos";
      var page = values[row][indiceColumna(headers, pageHeader)];
      sheet.setActiveRange(sheet.getRange(row + 1, 1, 1, headers.length));
      return {
        fila: row + 1, direccion: values[row][address], tipo: values[row][type],
        observacion: observation, campo: field.header, etiquetaCampo: field.etiqueta,
        valorActual: values[row][fieldIndex], pagina: page,
        pdfUrl: "https://drive.google.com/open?id=" + values[row][3],
        sugerencia: values[row][suggestion] || "Revise la evidencia indicada en la página " + (page || "correspondiente") + "."
      };
    }
  }
  return null;
}

function aplicarCorreccionCampo(fila, campo, valorCorregido) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var revision = ss.getSheetByName(CONFIG.SHEET_REVISION);
  var banco = obtenerOCrearPestaña(ss, CONFIG.SHEET_BANCO);
  var headers = revision.getRange(1, 1, 1, revision.getLastColumn()).getValues()[0];
  var values = revision.getRange(fila, 1, 1, headers.length).getValues()[0];
  var state = indiceColumna(headers, "Estado");
  if (!valorCorregido || !headers.includes(campo)) throw new Error("Indique un campo y un valor válido.");
  values[indiceColumna(headers, campo)] = valorCorregido;
  if (campo === "Tipo inmueble") {
    var chosenType = indiceColumna(headers, "Valor elegido tipo");
    var chosenUsd = indiceColumna(headers, "Valor elegido US$");
    var chosenPen = indiceColumna(headers, "Valor elegido S/");
    var source = valorCorregido === "CASA" ? "reconstruccion" : "comercial";
    values[chosenType] = valorCorregido === "CASA" ? "VALOR DE RECONSTRUCCION" : "VALOR COMERCIAL";
    values[chosenUsd] = values[indiceColumna(headers, "Valor " + source + " US$")];
    values[chosenPen] = values[indiceColumna(headers, "Valor " + source + " S/")];
  }
  var obs = indiceColumna(headers, "Observacion extraccion");
  var remaining = String(values[obs] || "").split("; ").filter(function (item) {
    var field = CAMPOS_REVISION.filter(function (candidate) { return candidate.header === campo; })[0];
    return item && (!field || item.indexOf(field.observacion) < 0);
  });
  values[obs] = remaining.join("; ");
  var target = revision.getRange(fila, 1, 1, headers.length);
  if (values[obs]) {
    values[state] = "Pendiente de revisión";
    target.setValues([values]).setBackground("#FEF3C7");
  } else {
    values[state] = "Validado y aprobado por operador";
    target.setValues([values]).setBackground("#D1FAE5");
    if (banco.getLastRow() === 0) prepararResultados(banco);
    banco.appendRow(values);
    formatearPestañaCompleta(banco, false);
  }
  SpreadsheetApp.flush();
}
