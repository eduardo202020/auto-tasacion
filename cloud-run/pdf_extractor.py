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
DATE_YEAR_RE = re.compile(
    r"\b(?:\d{1,2}\s*(?:[-/]\s*(?:\d{1,2}|[A-Z]{3,12})\s*[-/]\s*|\s+DE\s+[A-Z]{3,12}\s+DE\s+))(19\d{2}|20\d{2})\b",
    re.I,
)
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


def get_words(page: fitz.Page) -> list[dict[str, Any]]:
    """Obtiene palabras con coordenadas para leer tablas de tasación.

    Varios formatos ubican el número de pisos debajo del encabezado, no a su
    derecha. Leer solo el texto lineal desplaza los valores de esas tablas.
    """
    words = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        value = collapse_spaces(text)
        if value:
            words.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": value, "up": norm_up(value)})
    return words


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


def normalize_administrative_address(value: str) -> str:
    """Normaliza abreviaturas administrativas sin cambiar la vía ni el predio.

    El formulario ``Solicitud Construyo`` usa con frecuencia ``Dist.``,
    ``Prov.`` y ``Dpto.``. El parser de direcciones requiere las etiquetas
    completas. También admite el sufijo documentado ``distrito - provincia -
    departamento`` cuando los tres componentes están explícitos.
    """
    normalized = collapse_spaces(value)
    replacements = (
        (r"\bDIST\.?\s*:\s*", "Distrito "),
        (r"\bPROV\.?\s*:\s*", "Provincia "),
        (r"\bDPTO\.?\s*:\s*", "Departamento "),
    )
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized, flags=re.I)

    return collapse_spaces(normalized)


def has_complete_administrative_location(value: str) -> bool:
    """Indica si una dirección ya tiene distrito, provincia y departamento."""
    normalized = norm_up(value)
    return all(re.search(rf"\b{label}\b", normalized) for label in ("DISTRITO", "PROVINCIA", "DEPARTAMENTO"))


def has_hyphenated_administrative_suffix(value: str) -> bool:
    """Reconoce los tres niveles explícitos del anexo sin adivinar sus límites."""
    normalized = norm_up(value)
    return bool(re.search(r"\b[A-Z]{3,}(?:\s+[A-Z]{3,})*\s*-\s*[A-Z]{3,}(?:\s+[A-Z]{3,})*\s*-\s*[A-Z]{3,}\b", normalized))


def extract_solicitud_construyo_address(doc: fitz.Document) -> tuple[str, Optional[int]]:
    """Obtiene la dirección completa del anexo Solicitud Construyo.

    Esta fuente solo es respaldo territorial: ``extract_pdf`` la usa cuando la
    fuente prioritaria carece de distrito, provincia o departamento. Así no
    sustituye una dirección de minuta que ya es operable.
    """
    for page_index, page in enumerate(doc):
        text = page.get_text("text")
        normalized = norm_up(text)
        if "SOLICITUD CONSTRUYO" not in normalized or "DIRECCION DEL INMUEBLE" not in normalized:
            continue
        candidates = [
            normalize_administrative_address(clean_address(line))
            for line in text.splitlines()
            if looks_like_address(line)
        ]
        complete = [
            candidate for candidate in candidates
            if has_complete_administrative_location(candidate) or has_hyphenated_administrative_suffix(candidate)
        ]
        if len(complete) == 1:
            return complete[0], page_index + 1
    return "", None


def extract_address(doc: fitz.Document) -> tuple[str, Optional[int]]:
    """Extrae la dirección operativa con prioridad documental definida.

    El flujo histórico usa la dirección de minuta de la unidad tasada. La de
    inspección ocular es el primer respaldo y la dirección municipal/matriz
    queda como último recurso. Así se evita que una dirección matriz sustituya
    la ubicación específica de la garantía.
    """
    for source_marker in ("MINUTA", "INSPECCION"):
        for page_index in range(min(len(doc), 5)):
            blocks = get_blocks(doc[page_index])
            for block in blocks:
                if "DIRECCION" not in block["up"] or source_marker not in block["up"]:
                    continue
                inline = re.sub(
                    r"^.*?\b(?:MINUTA|INSPECCION(?:\s+OCULAR)?)\b\s*",
                    "",
                    block["text"],
                    flags=re.I,
                )
                value = clean_address(inline)
                if looks_like_address(value):
                    return normalize_administrative_address(value), page_index + 1
                nearby = sorted(
                    (
                        candidate for candidate in blocks
                        if candidate is not block
                        and candidate["x0"] >= block["x1"] - 12
                        and abs(candidate["y0"] - block["y0"]) <= 35
                    ),
                    key=lambda candidate: (abs(candidate["y0"] - block["y0"]), candidate["x0"]),
                )
                for candidate in nearby:
                    value = clean_address(candidate["text"])
                    if looks_like_address(value):
                        return normalize_administrative_address(value), page_index + 1

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
                return normalize_administrative_address(candidate), page_index + 1
    for page_index in range(min(len(doc), 5)):
        for block in get_blocks(doc[page_index]):
            if looks_like_address(block["text"]):
                return normalize_administrative_address(clean_address(block["text"])), page_index + 1
    return "", None


def detect_address_conflict(doc: fitz.Document, selected_address: str) -> str:
    """La prioridad Minuta > Inspección > Matriz resuelve fuentes distintas."""
    # La diferencia entre esas fuentes es esperada en los informes y queda
    # resuelta por la regla operativa de prioridad aplicada en extract_address.
    return ""


def extract_tipo_inmueble(doc: fitz.Document, direccion: str) -> tuple[str, str, Optional[int]]:
    labelled = re.compile(r"TIPO\s+(?:DE\s+)?INMUEBLE\D{0,50}(DEPARTAMENTO|DPTO\.?|DUPLEX|FLAT|CASA|CASA\s+HABITACION|VIVIENDA\s+UNIFAMILIAR)", re.I)
    for page_index in range(min(len(doc), 6)):
        text = doc[page_index].get_text("text")
        if match := labelled.search(text):
            raw = collapse_spaces(match.group(1))
            return ("DEPARTAMENTO" if RAW_DEPTO_RE.search(raw) else "CASA"), raw, page_index + 1
    for page_index in range(min(len(doc), 6)):
        text = doc[page_index].get_text("text")
        for match in RAW_DEPTO_RE.finditer(text):
            # ``Departamento Lambayeque`` y el encabezado geográfico no son
            # el tipo del inmueble. El tipo etiquetado ya se resolvió arriba;
            # este respaldo solo admite una mención no territorial.
            context = norm_up(text[max(0, match.start() - 100):match.end() + 100])
            if re.search(r"\b(?:DISTRITO|DIST\.?|PROVINCIA|PROV\.?)\b.{0,80}\b(?:DEPARTAMENTO|DPTO\.?)\b", context):
                continue
            return "DEPARTAMENTO", collapse_spaces(match.group(0)), page_index + 1
        if match := RAW_CASA_RE.search(text):
            return "CASA", collapse_spaces(match.group(0)), page_index + 1
    if RAW_DEPTO_RE.search(direccion):
        return "DEPARTAMENTO", "DEPARTAMENTO", None
    if RAW_CASA_RE.search(direccion):
        return "CASA", "CASA", None
    return "", "", None


def first_amount_after_currency(text: str, currency_pattern: str) -> Optional[float]:
    # Una tabla puede continuar con otros importes en la misma fila. Capturar
    # espacios aquí uniría, por ejemplo, el total y sus componentes en un
    # único número inválido.
    match = re.search(
        currency_pattern + r"\s*([0-9]+(?:[,.][0-9]{3})*(?:[,.][0-9]{1,2})?)",
        text,
        re.I,
    )
    return parse_amount(match.group(1)) if match else None


def extract_values_by_anchor(doc: fitz.Document, anchor_re: re.Pattern[str]) -> tuple[Optional[float], Optional[float], Optional[int]]:
    for page_index in range(min(len(doc), 10)):
        page = doc[page_index]
        blocks = get_blocks(page)
        for block in blocks:
            if not anchor_re.search(block["up"]):
                continue
            related = [
                item for item in blocks
                if block["y0"] - 3 <= item["y0"] <= block["y1"] + 42
                and item["x0"] >= max(0, block["x0"] - 40)
            ]
            related.sort(key=lambda item: (item["y0"], item["x0"]))
            section = " ".join(item["text"] for item in related)
            usd = first_amount_after_currency(section, r"(?:US\$|USD\$?|U\.?S\.?\$)")
            pen = first_amount_after_currency(section, r"(?:S/\.?|SOLES?)")
            if usd is not None or pen is not None:
                return usd, pen, page_index + 1

        page_text = page.get_text("text")
        match = anchor_re.search(norm_up(page_text))
        if match:
            section = page_text[match.start():match.start() + 1200]
            usd = first_amount_after_currency(section, r"(?:US\$|USD\$?|U\.?S\.?\$)")
            pen = first_amount_after_currency(section, r"(?:S/\.?|SOLES?)")
            if usd is not None or pen is not None:
                return usd, pen, page_index + 1
    return None, None, None


def extract_anio_construccion(doc: fitz.Document) -> tuple[Optional[int], Optional[int]]:
    labels = ("ANO DE CONSTRUCCION", "ANO DE EDIFICACION", "ANTIGUEDAD DEL INMUEBLE", "ANTIGUEDAD")
    excluded = re.compile(r"(FECHA\s+DE\s+INSPECCION|FECHA\s+DE\s+EXPEDICION|FECHA\s+DE\s+CADUCIDAD|MINUTA|COMPRAVENTA)", re.I)
    for page_index, page in enumerate(doc):
        # En algunos formatos el valor está en una celda a la derecha de la
        # etiqueta. El orden lineal del texto PDF no conserva necesariamente
        # esa relación, por lo que se prioriza la geometría de la misma fila.
        blocks = get_blocks(page)
        for label in blocks:
            if not any(item in label["up"] for item in labels):
                continue
            direct = excluded.sub("", label["up"])
            if match := YEAR_RE.search(direct):
                return int(match.group(1)), page_index + 1
            same_row = [
                item for item in blocks
                if item is not label
                and label["y0"] - 5 <= item["y0"] <= label["y1"] + 12
                and item["x0"] >= label["x1"] - 5
            ]
            for item in sorted(same_row, key=lambda entry: (entry["y0"], entry["x0"])):
                if match := YEAR_RE.search(item["up"]):
                    return int(match.group(1)), page_index + 1

        lines = page.get_text("text").splitlines()
        for line_index, line in enumerate(lines):
            if not any(label in norm_up(line) for label in labels):
                continue
            nearby = " ".join(lines[line_index:line_index + 4])
            nearby = excluded.sub("", norm_up(nearby))
            if match := YEAR_RE.search(nearby):
                return int(match.group(1)), page_index + 1
    return None, None


def extract_edad_efectiva(doc: fitz.Document) -> tuple[Optional[int], Optional[int]]:
    """Lee la edad efectiva de la tabla de construcciones, con su evidencia.

    El valor suele estar debajo del encabezado ``Edad Efectiva (años)``. Se
    usan palabras y coordenadas de la columna, no bloques de texto amplios:
    algunos motores PDF agrupan toda la tabla y podrían confundir los pisos
    del edificio con la edad.
    """
    for page_index, page in enumerate(doc):
        words = get_words(page)
        for header_word in words:
            if header_word["up"] != "EDAD":
                continue
            header_line = [
                item for item in words
                if abs(item["y0"] - header_word["y0"]) <= 3
            ]
            header_line.sort(key=lambda item: item["x0"])
            try:
                edad_index = header_line.index(header_word)
            except ValueError:
                continue
            effective = next(
                (item for item in header_line[edad_index + 1:] if item["up"].startswith("EFECTIVA")),
                None,
            )
            if effective is None:
                continue
            column_end = next(
                (item for item in header_line if item["x0"] >= effective["x1"] and "ANO" in item["up"]),
                effective,
            )
            candidates = [
                item for item in words
                if header_word["y1"] - 2 <= item["y0"] <= header_word["y1"] + 36
                and header_word["x0"] - 5 <= (item["x0"] + item["x1"]) / 2 <= column_end["x1"] + 8
                and re.fullmatch(r"0|[1-9]\d?|1[0-4]\d|150", item["text"])
            ]
            if candidates:
                candidates.sort(key=lambda item: (item["y0"], item["x0"]))
                return int(candidates[0]["text"]), page_index + 1
    # Un primer construyo declarado sin construcciones existentes acredita
    # edad efectiva cero. Se limita a la combinación literal para no convertir
    # cualquier obra en proyecto en una edad supuesta.
    for page_index, page in enumerate(doc):
        text = norm_up(page.get_text("text"))
        if "PRIMER CONSTRUYO" in text and "SIN CONSTRUCCIONES" in text:
            return 0, page_index + 1
    return None, None


def extract_anio_expedicion(doc: fitz.Document) -> tuple[Optional[int], Optional[int]]:
    """Extrae el año de la fecha de expedición, nunca otra fecha del informe."""
    for page_index, page in enumerate(doc):
        text = norm_up(page.get_text("text"))
        # El encabezado y ambas fechas pueden venir en el mismo bloque. Se
        # toma el primer año posterior a Expedición, antes de revisar celdas
        # cercanas que podrían pertenecer a Caducidad.
        if match := re.search(r"FECHA\s+DE\s+EXPEDICION.{0,45}?(19\d{2}|20\d{2})", text, re.S):
            return int(match.group(1)), page_index + 1
        blocks = get_blocks(page)
        for header in blocks:
            if "FECHA DE EXPEDICION" not in header["up"]:
                continue
            nearby = [header]
            nearby.extend(
                item for item in blocks
                if item is not header
                and header["y0"] - 5 <= item["y0"] <= header["y1"] + 45
                and item["x0"] >= header["x0"] - 20
            )
            nearby.sort(key=lambda item: (item["y0"], item["x0"]))
            for item in nearby:
                if match := DATE_YEAR_RE.search(item["up"]):
                    return int(match.group(1)), page_index + 1
    return None, None


def extract_pisos_sotanos_tabla(page: fitz.Page) -> tuple[Optional[int], Optional[int]]:
    """Extrae pisos y sótanos de la tabla de características del inmueble."""
    words = get_words(page)

    def value_below(header: dict[str, Any], *, left_tolerance: float = 8) -> Optional[int]:
        candidates = [
            word for word in words
            if header["y1"] - 2 <= word["y0"] <= header["y1"] + 42
            # Algunos PDFs centran el valor bajo la etiqueta completa
            # "N° de Pisos", por lo que queda a la izquierda de la palabra
            # "Pisos" que expone el extractor de texto.
            and header["x0"] - left_tolerance <= (word["x0"] + word["x1"]) / 2 <= header["x1"] + 85
            and re.fullmatch(r"\d{1,3}", word["text"])
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda word: (word["y0"], abs(((word["x0"] + word["x1"]) / 2) - ((header["x0"] + header["x1"]) / 2))))
        return int(candidates[0]["text"])

    floor_headers = [word for word in words if "PISOS" in word["up"]]
    basement_headers = [word for word in words if "SOTANO" in word["up"]]

    # Algunos formatos ponen ambos valores en una sola celda, por ejemplo
    # ``3 / 0``, bajo el encabezado ``N° de Pisos/Sótanos del edificio``. En
    # ese caso las columnas individuales no existen y la lectura anterior no
    # puede asociar el segundo valor con la palabra Sótanos.
    header_lines: list[list[dict[str, Any]]] = []
    for word in words:
        for line in header_lines:
            if abs(line[0]["y0"] - word["y0"]) <= 3:
                line.append(word)
                break
        else:
            header_lines.append([word])
    for line in header_lines:
        line.sort(key=lambda word: word["x0"])
        line_up = " ".join(word["up"] for word in line)
        if "PISOS" not in line_up or "SOTANOS" not in line_up:
            continue
        pair_header = [word for word in line if "PISOS" in word["up"] or "SOTANO" in word["up"]]
        x0 = min(word["x0"] for word in pair_header)
        x1 = max(word["x1"] for word in pair_header)
        y1 = max(word["y1"] for word in pair_header)
        values = [
            word for word in words
            if y1 - 2 <= word["y0"] <= y1 + 42
            and x0 - 60 <= (word["x0"] + word["x1"]) / 2 <= x1 + 60
            and re.fullmatch(r"\d{1,3}", word["text"])
        ]
        values.sort(key=lambda word: (word["y0"], word["x0"]))
        if len(values) >= 2:
            return int(values[0]["text"]), int(values[1]["text"])

    table_candidates: list[tuple[float, int, int]] = []
    for floor_header in floor_headers:
        pisos = value_below(floor_header, left_tolerance=50)
        if pisos is None:
            continue
        for basement_header in basement_headers:
            if abs(floor_header["y0"] - basement_header["y0"]) > 8:
                continue
            sotanos = value_below(basement_header)
            if sotanos is not None:
                table_candidates.append((floor_header["y0"], pisos, sotanos))
    if table_candidates:
        table_candidates.sort(key=lambda item: item[0])
        _, pisos, sotanos = table_candidates[0]
        return pisos, sotanos

    lines: list[list[dict[str, Any]]] = []
    for word in words:
        for line in lines:
            if abs(line[0]["y0"] - word["y0"]) <= 3:
                line.append(word)
                break
        else:
            lines.append([word])

    candidates: dict[str, tuple[float, float, float]] = {}
    for line in lines:
        line.sort(key=lambda word: word["x0"])
        line_up = " ".join(word["up"] for word in line)
        if "PISOS" in line_up and "EDIFIC" in line_up:
            floor_words = [word for word in line if "PISOS" in word["up"] or "EDIFIC" in word["up"]]
            candidates.setdefault(
                "pisos",
                (min(word["x0"] for word in floor_words), max(word["x1"] for word in floor_words), max(word["y1"] for word in floor_words)),
            )
        for word in line:
            if "SOTANO" in word["up"]:
                candidates.setdefault("sotanos", (word["x0"], word["x1"], word["y1"]))

    values: dict[str, Optional[int]] = {"pisos": None, "sotanos": None}
    for key, (x0, x1, y1) in candidates.items():
        below = [
            word for word in words
            if y1 - 2 <= word["y0"] <= y1 + 52
            and x0 - 5 <= (word["x0"] + word["x1"]) / 2 <= x1 + 20
            and re.fullmatch(r"\d{1,3}", word["text"])
        ]
        if below:
            below.sort(key=lambda word: (word["y0"], word["x0"]))
            values[key] = int(below[0]["text"])
    return values["pisos"], values["sotanos"]


def extract_pisos_sotanos_descripcion(doc: fitz.Document) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Prioriza la descripción del edificio cuando declara ambos totales.

    En informes con tablas, la fila puede referirse a una torre o a un nivel
    distinto. La regla del Colab toma la descripción explícita ``consta de`` /
    ``constará de`` cuando está disponible.
    """
    pattern = re.compile(
        r"\bCONSTA(?:RA)?\s+DE\b.{0,100}?\b(\d{1,3})\s+PISOS?\b.{0,100}?\b(\d{1,2})\s+SOTANOS?\b",
        re.I,
    )
    for page_index in range(min(len(doc), 10)):
        text = norm_up(doc[page_index].get_text("text"))
        match = pattern.search(text)
        if match:
            return int(match.group(1)), int(match.group(2)), page_index + 1
        project = re.search(
            r"\bPRIMER\s+CONSTRUYO\b.{0,180}?\b(?:PROYECTAD[AO]\s+A\s+)?(\d{1,3})\s+PISOS?\b.{0,40}?\bAZOTEA\b",
            text,
        )
        if project and "SIN CONSTRUCCIONES" in text:
            return int(project.group(1)), 0, page_index + 1
    return None, None, None


def extract_pisos_sotanos(doc: fitz.Document) -> tuple[Optional[int], Optional[int], Optional[int]]:
    # La tabla de características es la fuente operativa. La descripción se
    # conserva como respaldo cuando el informe no contiene una tabla legible.
    for page_index in range(min(len(doc), 10)):
        page = doc[page_index]
        pisos_tabla, sotanos_tabla = extract_pisos_sotanos_tabla(page)
        if pisos_tabla is not None:
            return pisos_tabla, sotanos_tabla if sotanos_tabla is not None else 0, page_index + 1

    pisos_descripcion, sotanos_descripcion, page_descripcion = extract_pisos_sotanos_descripcion(doc)
    if pisos_descripcion is not None:
        return pisos_descripcion, sotanos_descripcion, page_descripcion
    return None, None, None


def detect_pisos_sotanos_conflict(doc: fitz.Document) -> str:
    """La tabla prevalece sobre la descripción según la regla operativa."""
    return ""


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
        "Origen año construccion": "",
        "Edad efectiva": "",
        "Pagina edad efectiva": "",
        "Año expedicion": "",
        "Pagina año expedicion": "",
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
            solicitud_direccion, solicitud_page = extract_solicitud_construyo_address(doc)
            if solicitud_direccion and not has_complete_administrative_location(direccion):
                direccion, page_direccion = solicitud_direccion, solicitud_page
            tipo, tipo_texto, page_tipo = extract_tipo_inmueble(doc, direccion)
            commercial_usd, commercial_pen, page_commercial = extract_values_by_anchor(doc, VALOR_COMERCIAL_RE)
            reconstruction_usd, reconstruction_pen, page_reconstruction = extract_values_by_anchor(doc, VALOR_RECONSTRUCCION_RE)
            anio, page_anio = extract_anio_construccion(doc)
            edad_efectiva, page_edad_efectiva = extract_edad_efectiva(doc)
            anio_expedicion, page_anio_expedicion = extract_anio_expedicion(doc)
            pisos, sotanos, page_pisos = extract_pisos_sotanos(doc)
            # PRESTAMO y SEGURO INMUEBLE se obtienen después en PAD/IBM 3270.
            # Cloud Run no toma ni infiere esos identificadores desde el PDF.
            prestamo = ""
            address_conflict = detect_address_conflict(doc, direccion)
            floors_conflict = detect_pisos_sotanos_conflict(doc)
    except Exception as error:
        result["Observacion extraccion"] = f"Error procesando PDF: {error}"
        return result

    if tipo == "DEPARTAMENTO":
        chosen_type, chosen_usd, chosen_pen = "VALOR COMERCIAL", commercial_usd, commercial_pen
    elif tipo == "CASA":
        chosen_type, chosen_usd, chosen_pen = "VALOR DE RECONSTRUCCION", reconstruction_usd, reconstruction_pen
    else:
        chosen_type, chosen_usd, chosen_pen = "", None, None

    origen_anio = "AÑO DE CONSTRUCCIÓN" if anio is not None else ""
    if anio is None and edad_efectiva is not None and anio_expedicion is not None:
        calculated_year = anio_expedicion - edad_efectiva
        # No se rellena con una inferencia temporal imposible o fuera de un
        # intervalo razonable de construcción.
        if 1900 <= calculated_year <= anio_expedicion:
            anio = calculated_year
            page_anio = page_edad_efectiva
            origen_anio = "EDAD EFECTIVA"

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
        "Origen año construccion": origen_anio,
        "Edad efectiva": edad_efectiva if edad_efectiva is not None else "",
        "Pagina edad efectiva": page_edad_efectiva or "",
        "Año expedicion": anio_expedicion or "",
        "Pagina año expedicion": page_anio_expedicion or "",
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
        if edad_efectiva is None:
            observations.append("Año de construcción y edad efectiva no encontrados")
        elif anio_expedicion is None:
            observations.append("Año de construcción no encontrado: falta año de expedición")
        else:
            observations.append("Año de construcción no válido tras calcular edad efectiva")
    if pisos is None:
        observations.append("Número de pisos no encontrado")
    if sotanos is None:
        observations.append("Número de sótanos no encontrado")
    if address_conflict:
        observations.append(address_conflict)
    if floors_conflict:
        observations.append(floors_conflict)
    result["Observacion extraccion"] = "; ".join(observations)
    return result
