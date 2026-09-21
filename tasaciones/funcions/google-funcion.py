"""Endpoint de tasaciones.

El resultado replica el contrato de columnas del Colab en app-init. Los
campos no detectados permanecen vacíos y generan una observación: nunca se
inventan años, pisos ni valores.
"""
import json
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import fitz
import functions_framework
import requests

RESULT_HEADERS = [
    "ID / Codigo PDF", "PDF_Archivo", "PDF_Original_Drive", "Drive_File_ID",
    "Drive_Modificado", "Direccion extraida", "Pagina direccion",
    "Tipo inmueble", "Tipo inmueble texto", "Pagina tipo inmueble",
    "Valor elegido tipo", "Valor elegido US$", "Valor elegido S/",
    "Valor comercial US$", "Valor comercial S/", "Pagina valor comercial",
    "Valor reconstruccion US$", "Valor reconstruccion S/",
    "Pagina valor reconstruccion", "Año construccion", "Pagina año construccion",
    "Nro pisos edificio", "Nro sotanos edificio", "Pagina pisos/sotanos",
    "Observacion extraccion",
]
RAW_CASA_RE = re.compile(r"\b(CASA|CASA\s+HABITACION|VIVIENDA\s+UNIFAMILIAR|VIVIENDA)\b", re.I)
RAW_DEPTO_RE = re.compile(r"\b(DEPARTAMENTO|DPTO\.?|DUPLEX|FLAT)\b", re.I)
VALOR_COMERCIAL_RE = re.compile(r"\bVALOR\s+COMERCIAL\b", re.I)
VALOR_RECONSTRUCCION_RE = re.compile(r"\b(VALORES?\s+DE\s+RECONSTRUCCION|VALOR\s+DE\s+RECONSTRUCCION|RECONSTRUCCION)\b", re.I)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def norm_up(text: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(text or "")) if not unicodedata.combining(c))
    return collapse_spaces(plain.upper().replace("°", " ").replace("º", " "))


def parse_amount(text: str) -> Optional[float]:
    match = re.search(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?", str(text or ""))
    return float(match.group(0).replace(",", "")) if match else None


def clean_pdf_id(name: str) -> str:
    return re.sub(r"\.[Pp][Dd][Ff]$", "", str(name or "")).strip()


def get_blocks(page) -> List[Dict[str, Any]]:
    blocks = []
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        text = collapse_spaces(str(text or "").replace("\n", " "))
        if text:
            blocks.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": text, "up": norm_up(text)})
    return sorted(blocks, key=lambda item: (round(item["y0"], 1), round(item["x0"], 1)))


def extract_address(doc) -> Tuple[str, Optional[int]]:
    labels = ("DIRECCION", "UBICACION DEL PREDIO", "INMUEBLE UBICADO", "DIRECCION DEL INMUEBLE")
    for page_index in range(min(len(doc), 5)):
        blocks = get_blocks(doc[page_index])
        for index, block in enumerate(blocks):
            if any(label in block["up"] for label in labels) and not any(x in block["up"] for x in ("PLANO", "INDICE", "LAMINA")):
                value = block["text"]
                if index + 1 < len(blocks) and len(value) < 180:
                    value = collapse_spaces(value + " " + blocks[index + 1]["text"])
                return value, page_index + 1
    for page_index in range(min(len(doc), 4)):
        for block in get_blocks(doc[page_index]):
            if re.search(r"\b(AV\.?|AVENIDA|JR\.?|JIRON|CALLE|URB\.?|PSJE\.?|PASAJE|MZ\.?|LOTE)\b", block["up"]) and "PLANO" not in block["up"]:
                return block["text"], page_index + 1
    return "", None


def extract_tipo_inmueble(doc, direccion: str) -> Tuple[str, str, Optional[int]]:
    for page_index in range(min(len(doc), 5)):
        text = doc[page_index].get_text("text")
        if match := RAW_CASA_RE.search(text):
            return "CASA", collapse_spaces(match.group(0)), page_index + 1
        if match := RAW_DEPTO_RE.search(text):
            return "DEPARTAMENTO", collapse_spaces(match.group(0)), page_index + 1
    if match := RAW_CASA_RE.search(direccion):
        return "CASA", collapse_spaces(match.group(0)), None
    if match := RAW_DEPTO_RE.search(direccion):
        return "DEPARTAMENTO", collapse_spaces(match.group(0)), None
    return "", "", None


def first_amount_after_currency(text: str, currency_pattern: str) -> Optional[float]:
    match = re.search(currency_pattern + r"\s*([0-9][0-9,.]*)", text, re.I)
    return parse_amount(match.group(1)) if match else None


def extract_values_by_anchor(doc, anchor_re: re.Pattern) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    for page_index in range(min(len(doc), 8)):
        page_text = doc[page_index].get_text("text")
        match = anchor_re.search(norm_up(page_text))
        if match:
            section = page_text[match.start():match.start() + 650]
            usd = first_amount_after_currency(section, r"(?:US\$|USD\$?|U\.?S\.?\$)")
            pen = first_amount_after_currency(section, r"(?:S/\.?|SOLES?)")
            if usd is not None or pen is not None:
                return usd, pen, page_index + 1
    return None, None, None


def extract_anio_construccion(doc) -> Tuple[Optional[int], Optional[int]]:
    for page_index in range(min(len(doc), 8)):
        lines = doc[page_index].get_text("text").splitlines()
        for line_index, line in enumerate(lines):
            if any(label in norm_up(line) for label in ("CONSTRUCCION", "ANTIGUEDAD", "ANO", "AÑO")):
                match = YEAR_RE.search(" ".join(lines[line_index:line_index + 3]))
                if match:
                    return int(match.group(1)), page_index + 1
    return None, None


def extract_pisos_sotanos(doc) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    for page_index in range(min(len(doc), 8)):
        text = norm_up(doc[page_index].get_text("text"))
        if match := re.search(r"\b(\d{1,2})\s+PISOS?.{0,60}?(\d{1,2})\s+SOTANOS?\b", text):
            return int(match.group(1)), int(match.group(2)), page_index + 1
        if match := re.search(r"\b(\d{1,2})\s+SOTANOS?.{0,60}?(\d{1,2})\s+PISOS?\b", text):
            return int(match.group(2)), int(match.group(1)), page_index + 1
        if match := re.search(r"(?:NRO\.?\s*DE\s*)?PISOS?\s*[:\-]?\s*(\d{1,2})\b", text):
            basement = re.search(r"(?:NRO\.?\s*DE\s*)?SOTANOS?\s*[:\-]?\s*(\d{1,2})\b", text)
            return int(match.group(1)), int(basement.group(1)) if basement else None, page_index + 1
    return None, None, None


def empty_result(pdf: Dict[str, str]) -> Dict[str, Any]:
    return {
        "id_codigo_pdf": clean_pdf_id(pdf["name"]), "pdf_archivo": pdf["name"],
        "pdf_original_drive": pdf["name"], "drive_file_id": pdf["file_id"],
        "drive_modificado": pdf.get("modified", ""), "direccion_extraida": "", "pagina_direccion": "",
        "tipo_inmueble": "", "tipo_inmueble_texto": "", "pagina_tipo_inmueble": "",
        "valor_elegido_tipo": "", "valor_elegido_usd": "", "valor_elegido_pen": "",
        "valor_comercial_usd": "", "valor_comercial_pen": "", "pagina_valor_comercial": "",
        "valor_reconstruccion_usd": "", "valor_reconstruccion_pen": "", "pagina_valor_reconstruccion": "",
        "anio_construccion": "", "pagina_anio_construccion": "", "nro_pisos_edificio": "",
        "nro_sotanos_edificio": "", "pagina_pisos_sotanos": "", "observacion_extraccion": "",
    }


def extract_data_from_bytes(content: bytes, pdf: Dict[str, str]) -> Dict[str, Any]:
    result, observations = empty_result(pdf), []
    with fitz.open(stream=content, filetype="pdf") as doc:
        direccion, page_direccion = extract_address(doc)
        tipo, tipo_texto, page_tipo = extract_tipo_inmueble(doc, direccion)
        commercial_usd, commercial_pen, page_commercial = extract_values_by_anchor(doc, VALOR_COMERCIAL_RE)
        reconstruction_usd, reconstruction_pen, page_reconstruction = extract_values_by_anchor(doc, VALOR_RECONSTRUCCION_RE)
        anio, page_anio = extract_anio_construccion(doc)
        pisos, sotanos, page_pisos = extract_pisos_sotanos(doc)
    value_type, chosen_usd, chosen_pen = "", None, None
    if tipo == "DEPARTAMENTO":
        value_type, chosen_usd, chosen_pen = "VALOR COMERCIAL", commercial_usd, commercial_pen
    elif tipo == "CASA":
        value_type, chosen_usd, chosen_pen = "VALOR DE RECONSTRUCCION", reconstruction_usd, reconstruction_pen
    if not direccion: observations.append("Dirección no encontrada")
    if not tipo: observations.append("Tipo de inmueble no determinado")
    if chosen_usd is None or chosen_usd <= 0: observations.append("Valor elegido US$ ausente o inválido")
    if chosen_pen is None or chosen_pen <= 0: observations.append("Valor elegido S/ ausente o inválido")
    if anio is None: observations.append("Año de construcción no encontrado")
    if pisos is None: observations.append("Número de pisos no encontrado")
    result.update({
        "direccion_extraida": direccion, "pagina_direccion": page_direccion or "",
        "tipo_inmueble": tipo, "tipo_inmueble_texto": tipo_texto, "pagina_tipo_inmueble": page_tipo or "",
        "valor_elegido_tipo": value_type, "valor_elegido_usd": chosen_usd if chosen_usd is not None else "",
        "valor_elegido_pen": chosen_pen if chosen_pen is not None else "",
        "valor_comercial_usd": commercial_usd if commercial_usd is not None else "",
        "valor_comercial_pen": commercial_pen if commercial_pen is not None else "", "pagina_valor_comercial": page_commercial or "",
        "valor_reconstruccion_usd": reconstruction_usd if reconstruction_usd is not None else "",
        "valor_reconstruccion_pen": reconstruction_pen if reconstruction_pen is not None else "",
        "pagina_valor_reconstruccion": page_reconstruction or "", "anio_construccion": anio or "",
        "pagina_anio_construccion": page_anio or "", "nro_pisos_edificio": pisos if pisos is not None else "",
        "nro_sotanos_edificio": sotanos if sotanos is not None else "", "pagina_pisos_sotanos": page_pisos or "",
        "observacion_extraccion": "; ".join(observations),
    })
    return result


def download_drive_pdf(file_id: str) -> bytes:
    for url in (f"https://drive.google.com/uc?export=download&id={file_id}", f"https://drive.google.com/uc?export=download&confirm=t&id={file_id}"):
        response = requests.get(url, timeout=(10, 120))
        if response.ok and response.content.startswith(b"%PDF-"):
            return response.content
    raise ValueError("No fue posible descargar un PDF válido desde Google Drive")


def parse_rows(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    if isinstance(payload.get("archivos"), list):
        return [{"name": str(item.get("nombre", item.get("name", ""))), "file_id": str(item.get("file_id", "")), "modified": str(item.get("modified", ""))} for item in payload["archivos"] if item.get("file_id")]
    rows = payload.get("filas") or []
    if len(rows) < 2: return []
    header = [norm_up(value) for value in rows[0]]
    id_index = next((i for i, value in enumerate(header) if "FILE ID" in value or "DRIVE_FILE_ID" in value), 1)
    name_index = next((i for i, value in enumerate(header) if "NOMBRE" in value or "PDF_ARCHIVO" in value), 0)
    modified_index = next((i for i, value in enumerate(header) if "MODIFICADO" in value), -1)
    return [{"name": str(row[name_index]) if len(row) > name_index else "", "file_id": str(row[id_index]).strip(), "modified": str(row[modified_index]) if modified_index >= 0 and len(row) > modified_index else ""} for row in rows[1:] if len(row) > id_index and str(row[id_index]).strip()]


@functions_framework.http
def procesar_tasaciones(request):
    cors = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
    if request.method == "OPTIONS":
        return "", 204, {**cors, "Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type"}
    try:
        results = []
        for pdf in parse_rows(request.get_json(silent=True) or {}):
            try:
                results.append(extract_data_from_bytes(download_drive_pdf(pdf["file_id"]), pdf))
            except Exception as error:
                result = empty_result(pdf)
                result["observacion_extraccion"] = "Error procesando PDF: " + str(error)
                results.append(result)
        return json.dumps({"status": "success", "headers": RESULT_HEADERS, "resultados": results}, ensure_ascii=False), 200, cors
    except Exception as error:
        return json.dumps({"status": "error", "mensaje": str(error)}, ensure_ascii=False), 500, cors
