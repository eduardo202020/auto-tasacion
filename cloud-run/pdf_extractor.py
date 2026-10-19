"""Extracción determinista de datos de tasaciones desde un PDF.

Las reglas provienen del flujo que funcionaba en Colab. Este módulo no llama a
IA: conserva evidencia por página y deja vacío todo dato sin evidencia.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
import unicodedata
from typing import Any, Optional

import fitz

from document_classifier import classify_document, text_is_insufficient
from profile_registry import (
    detect_document_profile,
    profile_anchor_aliases,
    profile_selection_sections,
    profile_uses_strategy,
)
from provider_ocr import extract_braschi_floor_table_ocr, iter_provider_ocr_texts


RAW_CASA_RE = re.compile(r"\b(CASA|CASA\s+HABITACION|VIVIENDA\s+UNIFAMILIAR|VIVIENDA)\b", re.I)
RAW_DEPTO_RE = re.compile(r"\b(DEPARTAMENTO|DPTO\.?|DUPLEX|FLAT)\b", re.I)
RAW_TERRENO_RE = re.compile(r"\bTERRENO(?:\s+SIN\s+CONSTRUCCIONES)?\b", re.I)
VALOR_COMERCIAL_RE = re.compile(r"\bVALOR\s+COMERCIAL\b", re.I)
VALOR_RECONSTRUCCION_RE = re.compile(
    r"\b(VALORES?\s+DE\s+(?:RECONSTRUCCION|REPOSICION)|VALOR\s+DE\s+(?:RECONSTRUCCION|REPOSICION)|RECONSTRUCCION|REPOSICION)\b",
    re.I,
)
VALUE_BOUNDARY_RE = re.compile(
    r"\bVALOR(?:ES)?\s+(?:COMERCIAL|DE\s+(?:RECONSTRUCCION|REPOSICION)|INSCRITOS?|NO\s+INSCRITOS?)\b",
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

    La dirección registral prevalece sobre la de minuta; inspección ocular es
    el último respaldo. Las fuentes municipales o matriciales solo se revisan
    en el recorrido genérico posterior para no sustituir la garantía.
    """
    for source_marker, source_pattern in (
        ("REGISTRAL", r"REGISTRAL"),
        ("REGISTRO", r"REGISTRO"),
        ("MINUTA", r"MINUTA"),
        ("INSPECCION", r"INSPECCION(?:\s+OCULAR)?"),
    ):
        for page_index in range(min(len(doc), 5)):
            blocks = get_blocks(doc[page_index])
            for block in blocks:
                has_address_label = any(
                    label in block["up"] for label in ("DIRECCION", "UBICACION", "INMUEBLE")
                )
                if not has_address_label or source_marker not in block["up"]:
                    continue
                inline = re.sub(
                    rf"^.*?\b(?:{source_pattern})\b\s*",
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
    """La prioridad Registral > Minuta > Inspección resuelve fuentes distintas."""
    # La diferencia entre esas fuentes es esperada en los informes y queda
    # resuelta por la regla operativa de prioridad aplicada en extract_address.
    return ""


def extract_tipo_inmueble(doc: fitz.Document, direccion: str) -> tuple[str, str, Optional[int]]:
    labelled = re.compile(r"TIPO\s+(?:DE\s+)?INMUEBLE\D{0,50}(DEPARTAMENTO|DPTO\.?|DUPLEX|FLAT|CASA|CASA\s+HABITACION|VIVIENDA\s+UNIFAMILIAR|TERRENO(?:\s+SIN\s+CONSTRUCCIONES)?)", re.I)
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
        if match := RAW_TERRENO_RE.search(text):
            return "CASA", collapse_spaces(match.group(0)), page_index + 1
    if RAW_DEPTO_RE.search(direccion):
        return "DEPARTAMENTO", "DEPARTAMENTO", None
    if RAW_CASA_RE.search(direccion):
        return "CASA", "CASA", None
    if RAW_TERRENO_RE.search(direccion):
        return "CASA", "TERRENO", None
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


def anchor_position(text: str, anchor_re: re.Pattern[str], aliases: tuple[str, ...] = ()) -> int:
    """Encuentra la ancla base o una variante declarada por el perfil."""
    positions = [match.start() for match in anchor_re.finditer(text)]
    positions.extend(position for alias in aliases if (position := text.find(alias)) >= 0)
    return min(positions) if positions else -1


@dataclass(frozen=True)
class ValueCandidate:
    """Un importe vinculado a una ancla y contexto documental acotado."""

    field: str
    currency: str
    amount: float
    page: int
    anchor: str
    section: str
    source_priority: int


@dataclass(frozen=True)
class ValueSelection:
    usd: Optional[float]
    pen: Optional[float]
    page: Optional[int]
    candidates: tuple[ValueCandidate, ...]
    issues: tuple[str, ...]
    ambiguous_currencies: tuple[str, ...]


def _anchor_occurrences(text: str, anchor_re: re.Pattern[str], aliases: tuple[str, ...]) -> list[tuple[int, int, str]]:
    """Encuentra todas las anclas, incluidas las variantes declarativas."""
    occurrences = [(match.start(), match.end(), collapse_spaces(match.group(0))) for match in anchor_re.finditer(text)]
    normalized = norm_up(text)
    for alias in aliases:
        start = 0
        while (position := normalized.find(alias, start)) >= 0:
            occurrences.append((position, position + len(alias), alias))
            start = position + len(alias)
    return sorted(set(occurrences), key=lambda item: item[0])


def _value_context(anchor_text: str, before: str) -> tuple[str, int, str]:
    """Clasifica contexto por etiquetas conocidas, sin conservar texto del PDF."""
    normalized_anchor = norm_up(anchor_text)
    combined = norm_up(f"{before} {anchor_text}")
    if re.match(r"VALOR\s+COMERCIAL\s+DEL\s+INMUEBLE\b", normalized_anchor):
        return "VALOR_COMERCIAL_FINAL", 300, "VALOR COMERCIAL DEL INMUEBLE"
    if "VALORES NO INSCRITOS" in combined:
        return "VALORES_NO_INSCRITOS_RRPP", 220, "VALOR COMERCIAL"
    if "VALORES INSCRITOS" in combined:
        return "VALORES_INSCRITOS_RRPP", 120, "VALOR COMERCIAL"
    if "REPOSICION" in combined or "RECONSTRUCCION" in combined:
        return "REPOSICION", 220, "VALOR DE RECONSTRUCCION"
    if "COMERCIAL" in normalized_anchor:
        return "ANCLA_GENERAL", 180, "VALOR COMERCIAL"
    return "ANCLA_DECLARADA", 180, "VALOR DE RECONSTRUCCION"


def extract_value_candidates(
    doc: fitz.Document,
    anchor_re: re.Pattern[str],
    *,
    field: str,
    aliases: tuple[str, ...] = (),
) -> tuple[ValueCandidate, ...]:
    """Recolecta todos los importes razonables asociados a una misma ancla.

    El extractor anterior devolvía el primero. La lista permite conservar el
    cero de una sección registral como evidencia sin ocultar el valor final
    positivo que el layout pueda declarar después.
    """
    found: list[ValueCandidate] = []
    for page_index in range(min(len(doc), 10)):
        page = doc[page_index]
        # La capa de texto puede desordenar una tabla. Conservamos la lectura
        # geométrica de la implementación anterior como evidencia de mayor
        # proximidad al rótulo, pero ahora acumulamos todos los candidatos.
        blocks = get_blocks(page)
        for block in blocks:
            if anchor_position(block["up"], anchor_re, aliases) < 0:
                continue
            related = [
                item for item in blocks
                if block["y0"] - 3 <= item["y0"] <= block["y1"] + 42
                and item["x0"] >= max(0, block["x0"] - 40)
            ]
            related.sort(key=lambda item: (item["y0"], item["x0"]))
            section = " ".join(item["text"] for item in related)
            context, priority, normalized_anchor = _value_context(block["text"], "")
            usd = first_amount_after_currency(section, r"(?:US\$|USD\$?|U\.?S\.?\$)")
            pen = first_amount_after_currency(section, r"(?:S/\.?|SOLES?)")
            if usd is not None:
                found.append(ValueCandidate(field, "USD", usd, page_index + 1, normalized_anchor, context, priority + 40))
            if pen is not None:
                found.append(ValueCandidate(field, "PEN", pen, page_index + 1, normalized_anchor, context, priority + 40))

        page_text = page.get_text("text")
        occurrences = _anchor_occurrences(page_text, anchor_re, aliases)
        boundaries = [match.start() for match in VALUE_BOUNDARY_RE.finditer(page_text)]
        for position, end, anchor in occurrences:
            next_boundary = next((boundary for boundary in boundaries if boundary > position), None)
            section_end = next_boundary if next_boundary is not None else min(len(page_text), end + 600)
            section = page_text[end:section_end]
            usd = first_amount_after_currency(section, r"(?:US\$|USD\$?|U\.?S\.?\$)")
            pen = first_amount_after_currency(section, r"(?:S/\.?|SOLES?)")
            context, priority, normalized_anchor = _value_context(
                page_text[position:min(len(page_text), end + 35)],
                page_text[max(0, position - 180):position],
            )
            if usd is not None:
                found.append(ValueCandidate(field, "USD", usd, page_index + 1, normalized_anchor, context, priority))
            if pen is not None:
                found.append(ValueCandidate(field, "PEN", pen, page_index + 1, normalized_anchor, context, priority))
    unique_candidates = {
        (item.field, item.currency, item.amount, item.page, item.anchor, item.section, item.source_priority): item
        for item in found
    }
    # Dict conserva el orden de hallazgo: geometría de la página antes que
    # el respaldo lineal y páginas en orden documental. Es la prioridad
    # heredada para candidatos con la misma etiqueta y evita convertir un
    # valor posterior de una tabla auxiliar en el resultado operativo.
    return tuple(unique_candidates.values())


def extract_braschi_construyo_total_candidates(doc: fitz.Document) -> tuple[ValueCandidate, ...]:
    """Read the documented ``VALOR TOTAL`` column in Braschi Construyo tables.

    This strategy is restricted to the profile signed by Braschi, Construyo and
    the building table. The total, existing-building and projected-building
    columns coexist in the same row; this reads only the amount below the
    documented total column.
    """
    candidates: list[ValueCandidate] = []
    for page_index, page in enumerate(doc):
        words = get_words(page)
        rows: dict[float, list[dict[str, Any]]] = {}
        for word in words:
            rows.setdefault(round(word["y0"], 1), []).append(word)
        ordered_rows = sorted(rows.items())
        for y, row in ordered_rows:
            row.sort(key=lambda item: item["x0"])
            for word_index, word in enumerate(row[:-1]):
                next_word = row[word_index + 1]
                if word["up"] != "VALOR" or next_word["up"] != "TOTAL":
                    continue
                header_x = word["x0"]
                has_non_registered_section = any(
                    y - 25 <= nearby_y <= y + 25
                    and {"VALORES", "NO", "INSCRITOS"}.issubset({item["up"] for item in candidate_row})
                    for nearby_y, candidate_row in ordered_rows
                )
                if not has_non_registered_section:
                    continue
                for currency, tokens in (("USD", {"US$", "USD$"}), ("PEN", {"S/", "S/."})):
                    selected = None
                    for value_y, value_row in ordered_rows:
                        if not y < value_y <= y + 80 or not any(item["up"] in tokens for item in value_row):
                            continue
                        numeric = [
                            item for item in value_row
                            if header_x - 12 <= item["x0"] <= header_x + 105
                            and parse_amount(item["text"]) is not None
                        ]
                        if numeric:
                            selected = min(numeric, key=lambda item: abs(item["x0"] - header_x))
                            break
                    if selected is not None:
                        candidates.append(ValueCandidate(
                            "reconstruction_value", currency, parse_amount(selected["text"]),
                            page_index + 1, "VALOR TOTAL CONSTRUYO", "REPOSICION", 340,
                        ))
    unique = {(item.currency, item.amount, item.page): item for item in candidates}
    return tuple(unique.values())


def select_value_candidates(
    candidates: tuple[ValueCandidate, ...], *, issue_code: str,
    preferred_sections: tuple[str, ...] = (),
) -> ValueSelection:
    """Select by documentary hierarchy, keeping unruled ties fail-closed."""
    selected: dict[str, ValueCandidate] = {}
    issues: list[str] = []
    ambiguous_currencies: list[str] = []
    for currency in ("USD", "PEN"):
        currency_candidates = [item for item in candidates if item.currency == currency]
        positive = [item for item in currency_candidates if item.amount > 0]
        pool = positive or currency_candidates
        if not pool:
            continue
        highest_priority = max(item.source_priority for item in pool)
        finalists = [item for item in pool if item.source_priority == highest_priority]
        if preferred_sections:
            section_rank = {section: index for index, section in enumerate(preferred_sections)}
            declared = [item for item in finalists if item.section in section_rank]
            if declared:
                best_rank = min(section_rank[item.section] for item in declared)
                finalists = [item for item in declared if section_rank[item.section] == best_rank]
        if len({item.amount for item in finalists}) > 1:
            issues.append(issue_code)
            ambiguous_currencies.append(currency)
            continue
        selected[currency] = finalists[0]
    final = [item for item in selected.values()]
    page = max(final, key=lambda item: item.source_priority).page if final else None
    return ValueSelection(
        usd=selected.get("USD").amount if "USD" in selected else None,
        pen=selected.get("PEN").amount if "PEN" in selected else None,
        page=page,
        candidates=candidates,
        issues=tuple(dict.fromkeys(issues)),
        ambiguous_currencies=tuple(dict.fromkeys(ambiguous_currencies)),
    )


def operational_selection_issues(selection: ValueSelection) -> tuple[str, ...]:
    """Block only ambiguity in the currency that can feed the final row.

    The macro emits PEN whenever a PEN value exists, otherwise USD. A conflict
    in the unused currency remains in CONTROL candidates but cannot alter the
    selected operational amount. A conflict in the selected/preferred currency
    remains fail-closed.
    """
    available = {candidate.currency for candidate in selection.candidates}
    output_currency = "PEN" if "PEN" in available else "USD" if "USD" in available else ""
    return selection.issues if output_currency in selection.ambiguous_currencies else ()


def candidates_for_control(candidates: tuple[ValueCandidate, ...]) -> str:
    """Serializa solo metadatos técnicos; no incluye contenido del PDF."""
    return json.dumps([asdict(item) for item in candidates], ensure_ascii=False, separators=(",", ":"))


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


def extract_anio_inicio_obra(doc: fitz.Document) -> tuple[Optional[int], Optional[int]]:
    """Acepta la fecha de inicio solo si el documento declara una obra vigente.

    El estado y la fecha pueden estar en paginas distintas. Se valida la condicion
    ``EN CONSTRUCCION`` o ``PRIMER CONSTRUYO`` a nivel del documento antes de
    admitir una fecha que indique el inicio de la obra.
    """
    page_texts = [norm_up(page.get_text("text")) for page in doc]
    document_text = " ".join(page_texts)
    if "EN CONSTRUCCION" not in document_text and "PRIMER CONSTRUYO" not in document_text:
        return None, None

    start_re = re.compile(
        r"(?:FECHA\s+DE\s+)?INICIO\s+DE\s+(?:LA\s+)?(?:OBRA|CONSTRUCCION)(.*)",
        re.I,
    )
    for page_index, text in enumerate(page_texts):
        match = start_re.search(text)
        if not match:
            continue
        tail = match.group(1)[:100]
        date = re.search(r"\b\d{1,2}[/-]\d{1,2}[/-](\d{2}|19\d{2}|20\d{2})\b", tail)
        year = date.group(1) if date else next(iter(re.findall(r"\b(19\d{2}|20\d{2})\b", tail)), "")
        if year:
            parsed = int(year)
            return (2000 + parsed if len(year) == 2 else parsed), page_index + 1
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
        # En los formatos OP-D la lectura lineal puede ordenar primero el
        # encabezado y luego la fecha de caducidad. Se asocia el valor con la
        # etiqueta por su misma línea y por su posición a la derecha.
        words = get_words(page)
        for header in get_blocks(page):
            if "FECHA DE EXPEDICION" not in header["up"]:
                continue
            candidates = [
                word for word in words
                if abs(word["y0"] - header["y0"]) <= 3
                and word["x0"] >= header["x1"] - 5
                and DATE_YEAR_RE.search(word["up"])
            ]
            if candidates:
                candidates.sort(key=lambda word: (abs(word["y0"] - header["y0"]), word["x0"]))
                match = DATE_YEAR_RE.search(candidates[0]["up"])
                return int(match.group(1)), page_index + 1

        text = norm_up(page.get_text("text"))
        # Respaldo para documentos cuyo valor aparece en el mismo flujo de
        # texto que la etiqueta y no como una palabra posicionada aparte.
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
            # Una azotea puede aparecer entre ambos valores, por ejemplo,
            # "5 pisos, mas azotea y 2 sotanos". Es una cobertura y no
            # incrementa el total declarado de pisos.
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
        "Tasadora id": "",
        "Tasadora detectada": "",
        "Origen tasadora": "",
        "Perfil plantilla": "generic-v1",
        "Version perfil": "1",
        "Template id": "",
        "Familia layout": "",
        "Estrategia extraccion": "",
        "Confianza perfil": 0.0,
        "Coincidencias perfil": "",
        "Tipo documento": "DESCONOCIDO",
        "Motivo tipo documento": "",
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
        "Candidatos valor comercial": "",
        "Valor reconstruccion US$": "",
        "Valor reconstruccion S/": "",
        "Pagina valor reconstruccion": "",
        "Candidatos valor reconstruccion": "",
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
            page_texts = tuple(page.get_text("text") for page in doc)
            document_classification = classify_document(page_texts)
            ocr_texts: tuple[str, ...] = ()
            if (
                document_classification.document_type == "DESCONOCIDO"
                and text_is_insufficient(page_texts)
            ):
                ocr_texts = tuple(iter_provider_ocr_texts(doc))
                if ocr_texts:
                    document_classification = classify_document((*page_texts, *ocr_texts))
            profile = detect_document_profile(page_texts, ocr_texts)
            result["Tipo documento"] = document_classification.document_type
            result["Motivo tipo documento"] = document_classification.reason_code
            result.update({
                "Tasadora id": profile.provider_id,
                "Tasadora detectada": profile.provider_name,
                "Origen tasadora": profile.provider_source,
                "Perfil plantilla": profile.profile_id,
                "Version perfil": profile.version,
                "Template id": profile.template_id,
                "Familia layout": profile.layout_family,
                "Estrategia extraccion": ",".join(profile.strategies),
                "Confianza perfil": profile.confidence,
                "Coincidencias perfil": ",".join(profile.matched_terms),
            })
            if document_classification.document_type != "TASACION":
                result["Observacion extraccion"] = document_classification.reason_code
                return result
            if not profile.provider_id:
                if not ocr_texts:
                    ocr_texts = tuple(iter_provider_ocr_texts(doc))
                profile = detect_document_profile(page_texts, ocr_texts)
            direccion, page_direccion = extract_address(doc)
            solicitud_direccion, solicitud_page = extract_solicitud_construyo_address(doc)
            if solicitud_direccion and not has_complete_administrative_location(direccion):
                direccion, page_direccion = solicitud_direccion, solicitud_page
            tipo, tipo_texto, page_tipo = extract_tipo_inmueble(doc, direccion)
            commercial_candidates = extract_value_candidates(
                doc,
                VALOR_COMERCIAL_RE,
                field="commercial_value",
                aliases=profile_anchor_aliases(profile, "commercial_value"),
            )
            commercial_selection = select_value_candidates(
                commercial_candidates,
                issue_code="VALOR_COMERCIAL_AMBIGUO",
                preferred_sections=profile_selection_sections(profile, "commercial_value"),
            )
            reconstruction_candidates = extract_value_candidates(
                doc,
                VALOR_RECONSTRUCCION_RE,
                field="reconstruction_value",
                aliases=profile_anchor_aliases(profile, "reconstruction_value"),
            )
            if profile_uses_strategy(profile, "braschi_construyo_total_table"):
                reconstruction_candidates = (
                    *extract_braschi_construyo_total_candidates(doc),
                    *reconstruction_candidates,
                )
            reconstruction_selection = select_value_candidates(
                reconstruction_candidates,
                issue_code="VALOR_RECONSTRUCCION_AMBIGUO",
                preferred_sections=profile_selection_sections(profile, "reconstruction_value"),
            )
            commercial_usd, commercial_pen, page_commercial = (
                commercial_selection.usd, commercial_selection.pen, commercial_selection.page,
            )
            reconstruction_usd, reconstruction_pen, page_reconstruction = (
                reconstruction_selection.usd, reconstruction_selection.pen, reconstruction_selection.page,
            )
            anio, page_anio = extract_anio_construccion(doc)
            inicio_obra, page_inicio_obra = extract_anio_inicio_obra(doc)
            edad_efectiva, page_edad_efectiva = extract_edad_efectiva(doc)
            anio_expedicion, page_anio_expedicion = extract_anio_expedicion(doc)
            pisos, sotanos, page_pisos = extract_pisos_sotanos(doc)
            if pisos is None and profile_uses_strategy(profile, "braschi_floor_table_ocr"):
                ocr_floors = extract_braschi_floor_table_ocr(doc)
                if ocr_floors is not None:
                    pisos, sotanos, page_pisos = ocr_floors
            # Cloud Run no toma ni infiere PRESTAMO ni SEGURO INMUEBLE desde el
            # PDF. En lotes con control, PRESTAMO llega después desde la
            # proyección autorizada; los lotes heredados lo conservan vacío.
            prestamo = ""
            address_conflict = detect_address_conflict(doc, direccion)
            floors_conflict = detect_pisos_sotanos_conflict(doc)
    except Exception as error:
        result["Observacion extraccion"] = f"ERROR_EXTRACCION_{type(error).__name__.upper()}"
        return result

    if tipo == "DEPARTAMENTO":
        chosen_type, chosen_usd, chosen_pen = "VALOR COMERCIAL", commercial_usd, commercial_pen
        observations.extend(operational_selection_issues(commercial_selection))
    elif tipo == "CASA":
        chosen_type, chosen_usd, chosen_pen = "VALOR DE RECONSTRUCCION", reconstruction_usd, reconstruction_pen
        observations.extend(operational_selection_issues(reconstruction_selection))
    else:
        chosen_type, chosen_usd, chosen_pen = "", None, None
        observations.extend(commercial_selection.issues)
        observations.extend(reconstruction_selection.issues)

    origen_anio = "AÑO DE CONSTRUCCIÓN" if anio is not None else ""
    if anio is None and edad_efectiva is not None and anio_expedicion is not None:
        calculated_year = anio_expedicion - edad_efectiva
        # No se rellena con una inferencia temporal imposible o fuera de un
        # intervalo razonable de construcción.
        if 1900 <= calculated_year <= anio_expedicion:
            anio = calculated_year
            page_anio = page_edad_efectiva
            origen_anio = "EDAD EFECTIVA"
    # En una obra declarada en construcción, el inicio explícito documenta
    # el año operativo incluso si una tabla trae otro año de referencia.
    if inicio_obra is not None:
        anio = inicio_obra
        page_anio = page_inicio_obra
        origen_anio = "INICIO DE OBRA"

    result.update({
        "Tasadora id": profile.provider_id,
        "Tasadora detectada": profile.provider_name,
        "Origen tasadora": profile.provider_source,
        "Perfil plantilla": profile.profile_id,
        "Version perfil": profile.version,
        "Template id": profile.template_id,
        "Familia layout": profile.layout_family,
        "Estrategia extraccion": "; ".join(profile.strategies),
        "Confianza perfil": profile.confidence,
        "Coincidencias perfil": "; ".join(profile.matched_terms),
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
        "Candidatos valor comercial": candidates_for_control(commercial_selection.candidates),
        "Valor reconstruccion US$": reconstruction_usd if reconstruction_usd is not None else "",
        "Valor reconstruccion S/": reconstruction_pen if reconstruction_pen is not None else "",
        "Pagina valor reconstruccion": page_reconstruction or "",
        "Candidatos valor reconstruccion": candidates_for_control(reconstruction_selection.candidates),
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
