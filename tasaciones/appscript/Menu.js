function onOpen() {
  SpreadsheetApp.getUi().createMenu("🤖 Automatización de Tasaciones")
    .addItem("1. Cargar PDFs", "abrirPanelCargaPDFs")
    .addItem("2. Actualizar lista de PDFs", "escanearCarpetaPDFs")
    .addItem("3. Procesar y clasificar archivos", "procesarYClasificarTasaciones")
    .addItem("4. Abrir panel de revisión", "abrirPanelRevision")
    .addSeparator()
    .addItem("5. Generar Excel de casos validados", "exportarResultadosAExcel")
    .addToUi();
}
