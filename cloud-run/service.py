"""Endpoint HTTP del flujo Power Automate → Cloud Run → OneDrive.

Recibe un ZIP binario con PDFs y devuelve un XLSX con la hoja ``MASIVO`` que
consume la macro. La hoja ``CONTROL_EXTRACCION`` permite revisar evidencia y
campos no encontrados antes de ejecutar cualquier actualización bancaria.
"""
from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import functions_framework
import pandas as pd
from flask import Response

import address_parser
from catalog import lookup_location
from pdf_extractor import extract_pdf


MAX_PDFS_PER_BATCH = 300
MAX_ZIP_BYTES = 75 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024

MACRO_COLUMNS = [
    "PRESTAMO", "TIPO DE INMUEBLE", "VALOR DEL BIEN", "MONEDA", "IMPORTE", "COL_F",
    "DIRECCION", "DIRECCION1", "EXTERIOR", "INTERIOR", "REFERENCIA", "COL_L",
    "UBICACION", "UBICACION1", "MUNICIPIO", "DIST_COD", "COL_Q", "PROV_COD",
    "COL_S", "DEPT_COD", "CLASE", "PISOS", "SOTANOS", "AÑO",
]

CONTROL_COLUMNS = [
    "ID / Codigo PDF", "PDF_Archivo", "PRESTAMO", "Direccion extraida", "Pagina direccion",
    "Tipo inmueble", "Tipo inmueble texto", "Pagina tipo inmueble", "Valor elegido tipo",
    "Valor elegido US$", "Valor elegido S/", "Valor comercial US$", "Valor comercial S/",
    "Pagina valor comercial", "Valor reconstruccion US$", "Valor reconstruccion S/",
    "Pagina valor reconstruccion", "Año construccion", "Pagina año construccion",
    "Nro pisos edificio", "Nro sotanos edificio", "Pagina pisos/sotanos",
    "Observacion extraccion",
]

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def as_excel_value(value: Any) -> Any:
    """Conserva números como números y deja vacíos los valores no disponibles."""
    return "" if value is None else value


def macro_tipo(tipo: str) -> str:
    # Catálogo MASIVO: departamento usa valor comercial (C); casa valor nuevo (N).
    return {"DEPARTAMENTO": "C", "CASA": "N"}.get(tipo, "")


def macro_clase(pisos: Any) -> str:
    try:
        total = int(pisos)
    except (TypeError, ValueError):
        return ""
    if total <= 4:
        return "1"
    if total <= 10:
        return "2"
    return "3"


def choose_value(extracted: dict[str, Any]) -> tuple[Any, str]:
    """Prioriza US$ como hacía el flujo anterior; usa PEN solo si falta US$."""
    usd = extracted.get("Valor elegido US$")
    pen = extracted.get("Valor elegido S/")
    if usd not in (None, ""):
        return usd, "USD"
    if pen not in (None, ""):
        return pen, "PEN"
    return "", ""


def parse_address(extracted: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    observations: list[str] = []
    raw_address = str(extracted.get("Direccion extraida") or "")
    if not raw_address:
        return {}, ["No se puede estructurar la dirección porque no fue extraída"]
    try:
        parsed = address_parser.parse_direccion(raw_address)
    except Exception as error:
        return {}, [f"No se pudo estructurar la dirección: {error}"]

    location = lookup_location(
        parsed.get("DEPARTAMENTO", ""),
        parsed.get("PROVINCIA", ""),
        parsed.get("DISTRITO", ""),
    )
    parsed.update(location)
    for field, label in (
        ("DISTRITO_COD", "código de distrito"),
        ("PROVINCIA_COD", "código de provincia"),
        ("DEPARTAMENTO_COD", "código de departamento"),
    ):
        if not parsed.get(field):
            observations.append(f"{label.capitalize()} no encontrado en catálogo")
    return parsed, observations


def to_macro_row(extracted: dict[str, Any]) -> tuple[list[Any], list[str]]:
    parsed, observations = parse_address(extracted)
    value, currency = choose_value(extracted)
    pisos = extracted.get("Nro pisos edificio", "")
    tipo = str(extracted.get("Tipo inmueble") or "")
    row = [""] * len(MACRO_COLUMNS)
    row[0] = extracted.get("PRESTAMO", "")
    row[1] = macro_tipo(tipo)
    row[2] = as_excel_value(value)
    row[3] = currency
    row[4] = as_excel_value(value)
    row[6] = parsed.get("TIPO VIA 1", "")
    row[7] = parsed.get("DOMICILIO 1", "")
    row[8] = parsed.get("N. EXTERIOR", "")
    row[9] = parsed.get("N. INTERIOR", "")
    row[10] = parsed.get("REFERENCIA", "")
    row[12] = parsed.get("UBICACION TIPO", "")
    row[13] = parsed.get("UBICACION 1", "")
    row[14] = parsed.get("DISTRITO", "")
    row[15] = parsed.get("DISTRITO_COD", "")
    row[17] = parsed.get("PROVINCIA_COD", "")
    row[19] = parsed.get("DEPARTAMENTO_COD", "")
    row[20] = macro_clase(pisos)
    row[21] = as_excel_value(pisos)
    row[22] = as_excel_value(extracted.get("Nro sotanos edificio", ""))
    row[23] = as_excel_value(extracted.get("Año construccion", ""))
    return row, observations


def validate_zip(raw_data: bytes) -> list[zipfile.ZipInfo]:
    if not raw_data.startswith(b"PK"):
        raise ValueError("El cuerpo debe ser un archivo ZIP válido")
    if len(raw_data) > MAX_ZIP_BYTES:
        raise ValueError("El ZIP excede el tamaño máximo permitido")
    with zipfile.ZipFile(io.BytesIO(raw_data)) as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir() and entry.filename.lower().endswith(".pdf")]
        if not entries:
            raise ValueError("El ZIP no contiene archivos PDF")
        if len(entries) > MAX_PDFS_PER_BATCH:
            raise ValueError(f"El ZIP supera el máximo de {MAX_PDFS_PER_BATCH} PDFs")
        if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("El contenido descomprimido excede el tamaño máximo permitido")
        if any(entry.flag_bits & 0x1 for entry in entries):
            raise ValueError("El ZIP contiene PDFs cifrados y no puede procesarse")
        return entries


def process_zip(raw_data: bytes) -> tuple[list[list[Any]], list[dict[str, Any]]]:
    entries = validate_zip(raw_data)
    macro_rows: list[list[Any]] = []
    control_rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(raw_data)) as archive:
        for entry in entries:
            content = archive.read(entry)
            if not content.startswith(b"%PDF-"):
                extracted = {
                    "ID / Codigo PDF": entry.filename.rsplit("/", 1)[-1],
                    "PDF_Archivo": entry.filename,
                    "Observacion extraccion": "El archivo no tiene una firma PDF válida",
                }
            else:
                extracted = extract_pdf(content, entry.filename.rsplit("/", 1)[-1])
            macro_row, address_observations = to_macro_row(extracted)
            existing = str(extracted.get("Observacion extraccion") or "")
            all_observations = [item for item in [existing, *address_observations] if item]
            extracted["Observacion extraccion"] = "; ".join(all_observations)
            macro_rows.append(macro_row)
            control_rows.append(extracted)
    return macro_rows, control_rows


def build_workbook(macro_rows: list[list[Any]], control_rows: list[dict[str, Any]]) -> io.BytesIO:
    output = io.BytesIO()
    macro_df = pd.DataFrame(macro_rows, columns=MACRO_COLUMNS)
    control_df = pd.DataFrame(control_rows).reindex(columns=CONTROL_COLUMNS)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        macro_df.to_excel(writer, sheet_name="MASIVO", index=False)
        control_df.to_excel(writer, sheet_name="CONTROL_EXTRACCION", index=False)
        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for column in worksheet.columns:
                values = ["" if cell.value is None else str(cell.value) for cell in column]
                width = min(max(max(map(len, values), default=10) + 2, 12), 42)
                worksheet.column_dimensions[column[0].column_letter].width = width
    output.seek(0)
    return output


def json_error(message: str, status: int) -> Response:
    response = Response(json.dumps({"status": "error", "mensaje": message}, ensure_ascii=False), status=status, mimetype="application/json")
    response.headers.update(CORS_HEADERS)
    return response


@functions_framework.http
def procesar_tasaciones(request):
    if request.method == "OPTIONS":
        return "", 204, CORS_HEADERS
    if request.method != "POST":
        return json_error("Método no permitido", 405)
    try:
        raw_data = request.get_data(cache=False)
        macro_rows, control_rows = process_zip(raw_data)
        response = Response(
            build_workbook(macro_rows, control_rows).getvalue(),
            status=200,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response.headers["Content-Disposition"] = 'attachment; filename="Resultado_Final.xlsx"'
        response.headers.update(CORS_HEADERS)
        return response
    except ValueError as error:
        return json_error(str(error), 400)
    except Exception:
        return json_error("Error interno al procesar el lote de tasaciones", 500)
