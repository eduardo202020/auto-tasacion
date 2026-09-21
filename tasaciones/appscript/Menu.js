function onOpen() {
  SpreadsheetApp.getUi().createMenu("🤖 Automatización de Tasaciones")
    .addItem("1. Escanear PDFs desde Google Drive", "escanearCarpetaPDFs")
    .addItem("2. Procesar y clasificar archivos", "procesarYClasificarTasaciones")
    .addItem("3. Abrir panel de revisión", "abrirPanelRevision")
    .addSeparator()
    .addItem("4. Generar Excel de casos validados", "exportarResultadosAExcel")
    .addToUi();
}
