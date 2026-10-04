"""Extracción determinista de datos de tasaciones desde un PDF.

Las reglas provienen del flujo que funcionaba en Colab. Este módulo no llama a
IA: conserva evidencia por página y deja vacío todo dato sin evidencia.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

import fitz


RAW_CASA_RE = re.compile(r"\b(CASA|CASA\s+HABITACION|VIVIENDA\s+UNIFAMILIAR|VIVIENDA)\b", re.I)
RAW_DEPTO_RE = re.compile(r"\b(DEPARTAMENTO|DPTO\.?|DUPLEX|FLAT)\b", re.I)
VALOR_COMERCIAL_RE = re.compile(r"\bVALOR\s+COMERCIAL\b", re.I)
VALOR_RECONSTRUCCION_RE = re.compile(
    r"\b(VALORES?\s+DE\s+RECONSTRUCCION|VALOR\s+DE\s+RECONSTRUCCION|RECONSTRUCCION)\b",
    re.I,
)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
LOAN_LABEL_RE = re.compile(
    r"(?:N(?:RO|ÚMERO|UMERO)?\.?\s*(?:DE\s*)?)?(?:PR[EÉ]STAMO|OPERACI[OÓ]N|CR[EÉ]DITO)\D{0,35}((?:\d[\s-]*){20})",
    re.I,
)


def collapse_spaces(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def norm_up(text: object) -> str:
    plain = "".join(
        char for char in unicodedata.normalize("NFKD", str(text or ""))
        if not unicodedata.combining(char)
    )
    return collapse_spaces(plain.upper().replace("°", " ").replace("º", " "))


def clean_pdf_id(name: str) -> str:
    return re.sub(r"\.[Pp][Dd][Ff]$", "", str(name or "")).strip()


def parse_amount(text: object) -> Optional[float]:
    """Convierte importes US/PEN con miles y decimales frecuentes."""
    match = re.search(r"\d[\d., ]*", str(text or ""))
    if not match:
        return None
    value = re.sub(r"\s+", "", match.group(0))
    if value.count(",") and value.count("."):
        decimal = "," if value.rfind(",") > value.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        value = value.replace(thousands, "").replace(decimal, ".")
    elif value.count(",") > 1:
        value = value.replace(",", "")
    elif value.count(".") > 1:
        value = value.replace(".", "")
    elif value.count(",") == 1 and len(value.rsplit(",", 1)[1]) == 3:
        value = value.replace(",", "")
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def get_blocks(page: fitz.Page) -> list[dict[str, Any]]:
    blocks = []
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        value = collapse_spaces(str(text or "").replace("\n", " "))
        if value:
            blocks.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": value, "up": norm_up(value)})
    return sorted(blocks, key=lambda item: (round(item["y0"], 1), round(item["x0"], 1)))


def clean_address(value: str) -> str:
    value = re.sub(
        r"^(?:DIRECCI[OÓ]N(?:\s+DEL\s+INMUEBLE)?|UBICACI[OÓ]N\s+DEL\s+PREDIO|INMUEBLE\s+UBICADO)\s*[:\-]?\s*",
        "",
        value,
        flags=re.I,
    )
    return collapse_spaces(value.strip(" -:"))


def looks_like_address(value: str) -> bool:
    normalized = norm_up(value)
    return bool(
        re.search(r"\b(AV\.?|AVENIDA|JR\.?|JIRON|CALLE|URB\.?|PSJE\.?|PASAJE|MZ\.?|LOTE|CARRETERA)\b", normalized)
    ) and "PLANO" not in normalized and len(normalized) >= 8


def extract_address(doc: fitz.Document) -> tuple[str, Optional[int]]:
    labels = ("DIRECCION", "UBICACION DEL PREDIO", "INMUEBLE UBICADO", "DIRECCION DEL INMUEBLE")
    for page_index in range(min(len(doc), 5)):
        blocks = get_blocks(doc[page_index])
        for index, block in enumerate(blocks):
            if not any(label in block["up"] for label in labels):
                continue
            if any(noise in block["up"] for noise in ("PLANO", "INDICE", "LAMINA")):
                continue
            candidate = clean_address(block["text"])
            if not looks_like_address(candidate) and index + 1 < len(blocks):
                candidate = clean_address(candidate + " " + blocks[index + 1]["text"])
            if looks_like_address(candidate):
                return candidate, page_index + 1
    for page_index in range(min(len(doc), 5)):
        for block in get_blocks(doc[page_index]):
            if looks_like_address(block["text"]):
                return clean_address(block["text"]), page_index + 1
    return "", None


def extract_tipo_inmueble(doc: fitz.Document, direccion: str) -> tuple[str, str, Optional[int]]:
    labelled = re.compile(r"TIPO\s+(?:DE\s+)?INMUEBLE\D{0,50}(DEPARTAMENTO|DPTO\.?|DUPLEX|FLAT|CASA|CASA\s+HABITACION|VIVIENDA\s+UNIFAMILIAR)", re.I)
    for page_index in range(min(len(doc), 6)):
        text = doc[page_index].get_text("text")
        if match := labelled.search(text):
            raw = collapse_spaces(match.group(1))
            return ("DEPARTAMENTO" if RAW_DEPTO_RE.search(raw) else "CASA"), raw, page_index + 1
    for page_index in range(min(len(doc), 6)):
        text = doc[page_index].get_text("text")
        if match := RAW_DEPTO_RE.search(text):
            return "DEPARTAMENTO", collapse_spaces(match.group(0)), page_index + 1
        if match := RAW_CASA_RE.search(text):
            return "CASA", collapse_spaces(match.group(0)), page_index + 1
    if RAW_DEPTO_RE.search(direccion):
        return "DEPARTAMENTO", "DEPARTAMENTO", None
    if RAW_CASA_RE.search(direccion):
        return "CASA", "CASA", None
    return "", "", None


def first_amount_after_currency(text: str, currency_pattern: str) -> Optional[float]:
    match = re.search(currency_pattern + r"\s*([0-9][0-9,. ]*)", text, re.I)
    return parse_amount(match.group(1)) if match else None


def extract_values_by_anchor(doc: fitz.Document, anchor_re: re.Pattern[str]) -> tuple[Optional[float], Optional[float], Optional[int]]:
    for page_index in range(min(len(doc), 10)):
        page_text = doc[page_index].get_text("text")
        match = anchor_re.search(page_text)
        if not match:
            continue
        section = page_text[match.start():match.start() + 900]
        usd = first_amount_after_currency(section, r"(?:US\$|USD\$?|U\.?S\.?\$)")
        pen = first_amount_after_currency(section, r"(?:S/\.?|SOLES?)")
        if usd is not None or pen is not None:
            return usd, pen, page_index + 1
    return None, None, None


def extract_anio_construccion(doc: fitz.Document) -> tuple[Optional[int], Optional[int]]:
    labels = ("ANO DE CONSTRUCCION", "ANO DE EDIFICACION", "ANTIGUEDAD DEL INMUEBLE", "ANTIGUEDAD")
    excluded = re.compile(r"(FECHA\s+DE\s+INSPECCION|FECHA\s+DE\s+EXPEDICION|FECHA\s+DE\s+CADUCIDAD|MINUTA|COMPRAVENTA)", re.I)
    for page_index, page in enumerate(doc):
        lines = page.get_text("text").splitlines()
        for line_index, line in enumerate(lines):
            if not any(label in norm_up(line) for label in labels):
                continue
            nearby = " ".join(lines[line_index:line_index + 4])
            nearby = excluded.sub("", norm_up(nearby))
            if match := YEAR_RE.search(nearby):
                return int(match.group(1)), page_index + 1
    return None, None


def extract_pisos_sotanos(doc: fitz.Document) -> tuple[Optional[int], Optional[int], Optional[int]]:
    for page_index in range(min(len(doc), 10)):
        text = norm_up(doc[page_index].get_text("text"))
        patterns = (
            r"\b(\d{1,2})\s+PISOS?.{0,100}?(\d{1,2})\s+SOTANOS?\b",
            r"\b(\d{1,2})\s+SOTANOS?.{0,100}?(\d{1,2})\s+PISOS?\b",
        )
        if match := re.search(patterns[0], text):
            return int(match.group(1)), int(match.group(2)), page_index + 1
        if match := re.search(patterns[1], text):
            return int(match.group(2)), int(match.group(1)), page_index + 1
        floor = re.search(r"(?:NRO\.?\s*DE\s*)?PISOS?(?:\s+EN\s+EL\s+EDIFICIO)?\s*[:\-]?\s*(\d{1,2})\b", text)
        if floor:
            basement = re.search(r"(?:NRO\.?\s*DE\s*)?SOTANOS?(?:\s+Y/O\s+SEMISOTANOS)?\s*[:\-]?\s*(\d{1,2})\b", text)
            return int(floor.group(1)), int(basement.group(1)) if basement else 0, page_index + 1
    return None, None, None


def extract_loan_number(doc: fitz.Document, filename: str) -> str:
    candidates = re.findall(r"\d{20}", filename)
    if len(set(candidates)) == 1:
        return candidates[0]
    document_text = "\n".join(page.get_text("text") for page in doc)
    labelled = [re.sub(r"\D", "", value) for value in LOAN_LABEL_RE.findall(document_text)]
    labelled = [value for value in labelled if len(value) == 20]
    if len(set(labelled)) == 1:
        return labelled[0]
    candidates = re.findall(r"\b\d{20}\b", document_text)
    return candidates[0] if len(set(candidates)) == 1 else ""


def extract_pdf(content: bytes, filename: str) -> dict[str, Any]:
    """Extrae campos estructurados y conserva la observación de cada ausencia."""
    result: dict[str, Any] = {
        "ID / Codigo PDF": clean_pdf_id(filename),
        "PDF_Archivo": filename,
        "Direccion extraida": "",
        "Pagina direccion": "",
        "Tipo inmueble": "",
        "Tipo inmueble texto": "",
        "Pagina tipo inmueble": "",
        "Valor elegido tipo": "",
        "Valor elegido US$": "",
        "Valor elegido S/": "",
        "Valor comercial US$": "",
        "Valor comercial S/": "",
        "Pagina valor comercial": "",
        "Valor reconstruccion US$": "",
        "Valor reconstruccion S/": "",
        "Pagina valor reconstruccion": "",
        "Año construccion": "",
        "Pagina año construccion": "",
        "Nro pisos edificio": "",
        "Nro sotanos edificio": "",
        "Pagina pisos/sotanos": "",
        "PRESTAMO": "",
        "Observacion extraccion": "",
    }
    observations: list[str] = []
    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            direccion, page_direccion = extract_address(doc)
            tipo, tipo_texto, page_tipo = extract_tipo_inmueble(doc, direccion)
            commercial_usd, commercial_pen, page_commercial = extract_values_by_anchor(doc, VALOR_COMERCIAL_RE)
            reconstruction_usd, reconstruction_pen, page_reconstruction = extract_values_by_anchor(doc, VALOR_RECONSTRUCCION_RE)
            anio, page_anio = extract_anio_construccion(doc)
            pisos, sotanos, page_pisos = extract_pisos_sotanos(doc)
            prestamo = extract_loan_number(doc, filename)
    except Exception as error:
        result["Observacion extraccion"] = f"Error procesando PDF: {error}"
        return result

    if tipo == "DEPARTAMENTO":
        chosen_type, chosen_usd, chosen_pen = "VALOR COMERCIAL", commercial_usd, commercial_pen
    elif tipo == "CASA":
        chosen_type, chosen_usd, chosen_pen = "VALOR DE RECONSTRUCCION", reconstruction_usd, reconstruction_pen
    else:
        chosen_type, chosen_usd, chosen_pen = "", None, None

    result.update({
        "Direccion extraida": direccion,
        "Pagina direccion": page_direccion or "",
        "Tipo inmueble": tipo,
        "Tipo inmueble texto": tipo_texto,
        "Pagina tipo inmueble": page_tipo or "",
        "Valor elegido tipo": chosen_type,
        "Valor elegido US$": chosen_usd if chosen_usd is not None else "",
        "Valor elegido S/": chosen_pen if chosen_pen is not None else "",
        "Valor comercial US$": commercial_usd if commercial_usd is not None else "",
        "Valor comercial S/": commercial_pen if commercial_pen is not None else "",
        "Pagina valor comercial": page_commercial or "",
        "Valor reconstruccion US$": reconstruction_usd if reconstruction_usd is not None else "",
        "Valor reconstruccion S/": reconstruction_pen if reconstruction_pen is not None else "",
        "Pagina valor reconstruccion": page_reconstruction or "",
        "Año construccion": anio or "",
        "Pagina año construccion": page_anio or "",
        "Nro pisos edificio": pisos if pisos is not None else "",
        "Nro sotanos edificio": sotanos if sotanos is not None else "",
        "Pagina pisos/sotanos": page_pisos or "",
        "PRESTAMO": prestamo,
    })
    if not direccion:
        observations.append("Dirección no encontrada")
    if not tipo:
        observations.append("Tipo de inmueble no determinado")
    if tipo == "DEPARTAMENTO" and chosen_usd is None and chosen_pen is None:
        observations.append("Valor comercial no encontrado")
    if tipo == "CASA" and chosen_usd is None and chosen_pen is None:
        observations.append("Valor de reconstrucción no encontrado")
    if not anio:
        observations.append("Año de construcción no encontrado")
    if pisos is None:
        observations.append("Número de pisos no encontrado")
    if sotanos is None:
        observations.append("Número de sótanos no encontrado")
    if not prestamo:
        observations.append("Préstamo de 20 dígitos no encontrado")
    result["Observacion extraccion"] = "; ".join(observations)
    return result
