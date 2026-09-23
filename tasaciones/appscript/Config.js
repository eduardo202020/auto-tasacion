var CONFIG = {
  CLOUD_FUNCTION_URL: "https://demo-tasaciones-ia-1067946905386.northamerica-northeast1.run.app",
  SHEET_ENTRADA: "🎛️ Panel de Entrada",
  SHEET_REVISION: "🔍 Bandeja de Revisión",
  SHEET_BANCO: "⚡ Listos para el Banco",
  SHEET_EXPORT: "📥 Exportación Excel",
  MAX_PDFS_POR_LOTE: 300,
  MAX_TAMANO_PDF_MB: 25,
  RESULT_HEADERS: [
    "ID / Codigo PDF", "PDF_Archivo", "PDF_Original_Drive", "Drive_File_ID",
    "Drive_Modificado", "Direccion extraida", "Pagina direccion",
    "Tipo inmueble", "Tipo inmueble texto", "Pagina tipo inmueble",
    "Valor elegido tipo", "Valor elegido US$", "Valor elegido S/",
    "Valor comercial US$", "Valor comercial S/", "Pagina valor comercial",
    "Valor reconstruccion US$", "Valor reconstruccion S/",
    "Pagina valor reconstruccion", "Año construccion", "Pagina año construccion",
    "Nro pisos edificio", "Nro sotanos edificio", "Pagina pisos/sotanos",
    "Sugerencia IA", "Observacion extraccion", "Estado"
  ]
};
