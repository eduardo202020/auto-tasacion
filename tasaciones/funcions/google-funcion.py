"""Endpoint de tasaciones.

El resultado replica el contrato de columnas del Colab en app-init. Los
campos no detectados permanecen vacíos y generan una observación: nunca se
inventan años, pisos ni valores.
"""
import json
import os
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
    "Sugerencia IA", "Observacion extraccion",
]
RAW_CASA_RE = re.compile(r"\b(CASA|CASA\s+HABITACION|VIVIENDA\s+UNIFAMILIAR|VIVIENDA)\b", re.I)
RAW_DEPTO_RE = re.compile(r"\b(DEPARTAMENTO|DPTO\.?|DUPLEX|FLAT)\b", re.I)
VALOR_COMERCIAL_RE = re.compile(r"\bVALOR\s+COMERCIAL\b", re.I)
VALOR_RECONSTRUCCION_RE = re.compile(r"\b(VALORES?\s+DE\s+RECONSTRUCCION|VALOR\s+DE\s+RECONSTRUCCION|RECONSTRUCCION)\b", re.I)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
GEMINI_FIELDS = (
    "direccion_extraida", "pagina_direccion", "tipo_inmueble", "tipo_inmueble_texto",
    "pagina_tipo_inmueble", "valor_comercial_usd", "valor_comercial_pen",
    "pagina_valor_comercial", "valor_reconstruccion_usd", "valor_reconstruccion_pen",
    "pagina_valor_reconstruccion", "anio_construccion", "pagina_anio_construccion",
    "nro_pisos_edificio", "nro_sotanos_edificio", "pagina_pisos_sotanos",
)


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
    labels = (
        "ANO DE CONSTRUCCION", "ANO DE EDIFICACION", "ANTIGUEDAD DEL INMUEBLE",
        "ANTIGUEDAD",
    )
    for page_index in range(len(doc)):
        lines = doc[page_index].get_text("text").splitlines()
        for line_index, line in enumerate(lines):
            normalized_line = norm_up(line)
            if any(label in normalized_line for label in labels):
                nearby = " ".join(lines[line_index:line_index + 4])
                nearby = re.sub(r"(FECHA\s+DE\s+INSPECCION|FECHA\s+DE\s+EXPEDICION|FECHA\s+DE\s+CADUCIDAD)\s*[:\-]?\s*", "", norm_up(nearby))
                match = YEAR_RE.search(nearby)
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


def document_context(doc) -> str:
    pages = []
    for page_index in range(len(doc)):
        text = collapse_spaces(doc[page_index].get_text("text"))
        if text:
            pages.append(f"[PAGINA {page_index + 1}]\n{text}")
    return "\n\n".join(pages)[:100000]


def gemini_json(text: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    if not api_key:
        return None
    prompt = f"""Eres un extractor de tasaciones inmobiliarias peruanas. Corrige SOLO los campos del JSON usando evidencia literal del texto del PDF.
Reglas estrictas:
- No inventes ni completes datos ausentes.
- La direccion debe ser la del inmueble tasado, preferentemente la etiqueta 'Dirección según inspección ocular'; si falta, usa 'Dirección Minuta de compraventa' y luego la municipal. No devuelvas etiquetas, solo el valor.
- 'DEPARTAMENTO' gana si aparece 'Tipo de inmueble Departamento', 'Departamento N°' o 'Departamento Flat'. 'CASA' solo si el inmueble tasado es una casa, no por menciones de vivienda en anexos o descripciones generales.
- Usa valor comercial para DEPARTAMENTO y valor de reconstrucción solo para CASA.
- Para año de construcción busca explícitamente 'Año de construcción', 'Año de edificación' o 'Antigüedad'. No uses fechas de inspección, expedición, caducidad, minuta o compraventa. Si la etiqueta no tiene un año asociado, devuelve null.
- Devuelve páginas 1-based y números como números. Devuelve null cuando no haya evidencia.
- Devuelve JSON válido, sin markdown, con 'campos' y 'sugerencia'. En 'campos' incluye solo campos corregidos o confirmados con evidencia.

""" + json.dumps({"campos_actuales": {key: result.get(key, "") for key in GEMINI_FIELDS}, "texto_pdf": text}, ensure_ascii=False)
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}},
        timeout=(10, 90),
    )
    response.raise_for_status()
    body = response.json()
    output = body["candidates"][0]["content"]["parts"][0]["text"]
    output = re.sub(r"^```(?:json)?\s*|\s*```$", "", output.strip(), flags=re.I)
    parsed = json.loads(output)
    return parsed if isinstance(parsed, dict) else None


def apply_gemini_result(result: Dict[str, Any], parsed: Optional[Dict[str, Any]]) -> None:
    if not parsed:
        return
    fields = parsed.get("campos") or {}
    for key in GEMINI_FIELDS:
        if key in fields and fields[key] is not None and str(fields[key]).strip() != "":
            result[key] = fields[key]
    if result.get("tipo_inmueble") == "DEPARTAMENTO":
        result["valor_elegido_tipo"] = "VALOR COMERCIAL"
        result["valor_elegido_usd"] = result.get("valor_comercial_usd", "")
        result["valor_elegido_pen"] = result.get("valor_comercial_pen", "")
    elif result.get("tipo_inmueble") == "CASA":
        result["valor_elegido_tipo"] = "VALOR DE RECONSTRUCCION"
        result["valor_elegido_usd"] = result.get("valor_reconstruccion_usd", "")
        result["valor_elegido_pen"] = result.get("valor_reconstruccion_pen", "")
    result["sugerencia_ia"] = collapse_spaces(parsed.get("sugerencia", ""))


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
        "sugerencia_ia": "",
    }


def extract_data_from_bytes(content: bytes, pdf: Dict[str, str]) -> Dict[str, Any]:
    result = empty_result(pdf)
    with fitz.open(stream=content, filetype="pdf") as doc:
        direccion, page_direccion = extract_address(doc)
        tipo, tipo_texto, page_tipo = extract_tipo_inmueble(doc, direccion)
        commercial_usd, commercial_pen, page_commercial = extract_values_by_anchor(doc, VALOR_COMERCIAL_RE)
        reconstruction_usd, reconstruction_pen, page_reconstruction = extract_values_by_anchor(doc, VALOR_RECONSTRUCCION_RE)
        anio, page_anio = extract_anio_construccion(doc)
        pisos, sotanos, page_pisos = extract_pisos_sotanos(doc)
        context = document_context(doc)
    value_type, chosen_usd, chosen_pen = "", None, None
    if tipo == "DEPARTAMENTO":
        value_type, chosen_usd, chosen_pen = "VALOR COMERCIAL", commercial_usd, commercial_pen
    elif tipo == "CASA":
        value_type, chosen_usd, chosen_pen = "VALOR DE RECONSTRUCCION", reconstruction_usd, reconstruction_pen
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
    })
    try:
        apply_gemini_result(result, gemini_json(context, result))
    except Exception as error:
        result["sugerencia_ia"] = "IA no disponible: " + str(error)
    observations = []
    if not result["direccion_extraida"]: observations.append("Dirección no encontrada")
    if result["tipo_inmueble"] not in ("CASA", "DEPARTAMENTO"): observations.append("Tipo de inmueble no determinado")
    if result["tipo_inmueble"] == "DEPARTAMENTO":
        if not result["valor_comercial_usd"] or float(result["valor_comercial_usd"]) <= 0: observations.append("Valor comercial US$ ausente o inválido")
        if not result["valor_comercial_pen"] or float(result["valor_comercial_pen"]) <= 0: observations.append("Valor comercial S/ ausente o inválido")
    if result["tipo_inmueble"] == "CASA":
        if not result["valor_reconstruccion_usd"] or float(result["valor_reconstruccion_usd"]) <= 0: observations.append("Valor de reconstrucción US$ ausente o inválido")
        if not result["valor_reconstruccion_pen"] or float(result["valor_reconstruccion_pen"]) <= 0: observations.append("Valor de reconstrucción S/ ausente o inválido")
    if not result["anio_construccion"]: observations.append("Año de construcción no encontrado")
    if not result["nro_pisos_edificio"]: observations.append("Número de pisos no encontrado")
    result["observacion_extraccion"] = "; ".join(observations)
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
