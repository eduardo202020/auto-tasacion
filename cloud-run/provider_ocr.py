"""OCR local y acotado para reconocer logotipos de tasadoras.

Solo se inspeccionan encabezado y pie de las primeras páginas. El texto OCR no
se registra, no se envía a servicios externos y únicamente se compara con las
firmas versionadas de ``tasadoras.json``.
"""
from __future__ import annotations

import re
from collections.abc import Iterator

import fitz

try:  # La ausencia de OCR mantiene el respaldo genérico sin detener un lote.
    import pytesseract
    from PIL import Image
except ImportError:  # pragma: no cover - se cubre en la imagen de Cloud Run.
    pytesseract = None
    Image = None


_REGIONS = (
    ("encabezado", (0.0, 0.0, 1.0, 0.22)),
    ("pie", (0.0, 0.72, 1.0, 1.0)),
)
_MAX_PAGES = 3
_OCR_CONFIG = "--psm 11"
_TABLE_OCR_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789"
_BRASCHI_FLOORS_TERMS = ("PISOS", "EN", "EL", "EDIFICIO")
_BRASCHI_BASEMENTS_TERMS = ("SOTANOS", "Y/O", "SEMISOTANOS")


def _relative_rect(page: fitz.Page, region: tuple[float, float, float, float]) -> fitz.Rect:
    x0, y0, x1, y1 = region
    bounds = page.rect
    return fitz.Rect(
        bounds.x0 + (bounds.width * x0),
        bounds.y0 + (bounds.height * y0),
        bounds.x0 + (bounds.width * x1),
        bounds.y0 + (bounds.height * y1),
    )


def iter_provider_ocr_texts(document: fitz.Document) -> Iterator[str]:
    """Devuelve fragmentos OCR locales aptos para identificar una tasadora.

    El OCR es deliberadamente opcional: si la dependencia, el binario o el
    idioma no están disponibles, la extracción continúa con ``generic-v1``.
    """
    if pytesseract is None or Image is None:
        return
    for page_index in range(min(_MAX_PAGES, len(document))):
        page = document[page_index]
        for _, region in _REGIONS:
            try:
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(2, 2),
                    clip=_relative_rect(page, region),
                    colorspace=fitz.csGRAY,
                    alpha=False,
                )
                image = Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
                text = pytesseract.image_to_string(image, lang="eng", config=_OCR_CONFIG)
            except Exception:
                return
            normalized = re.sub(r"\s+", " ", str(text or "")).strip()
            if normalized:
                yield normalized[:512]


def _normalized_word(value: object) -> str:
    text = str(value or "").upper()
    return re.sub(r"[^A-Z0-9/]", "", text.translate(str.maketrans("ÁÉÍÓÚÜÑ", "AEIOUUN")))


def _same_text_line(words: list[tuple[float, float, float, float, str, int, int, int]]) -> list[list[tuple[float, float, float, float, str, int, int, int]]]:
    lines: list[list[tuple[float, float, float, float, str, int, int, int]]] = []
    for word in sorted(words, key=lambda item: (item[1], item[0])):
        for line in lines:
            if abs(line[0][1] - word[1]) <= 3:
                line.append(word)
                break
        else:
            lines.append([word])
    for line in lines:
        line.sort(key=lambda item: item[0])
    return lines


def _header_rect(page: fitz.Page, terms: tuple[str, ...]) -> fitz.Rect | None:
    words = page.get_text("words", sort=True)
    for line in _same_text_line(words):
        normalized = [_normalized_word(word[4]) for word in line]
        width = len(terms)
        for index in range(len(normalized) - width + 1):
            if tuple(normalized[index:index + width]) != terms:
                continue
            matched = line[index:index + width]
            x0 = max(page.rect.x0, min(word[0] for word in matched) - 12)
            x1 = min(page.rect.x1, max(word[2] for word in matched) + 12)
            y0 = min(page.rect.y1, max(word[3] for word in matched) + 3)
            y1 = min(page.rect.y1, y0 + 55)
            if x1 > x0 and y1 > y0:
                return fitz.Rect(x0, y0, x1, y1)
    return None


def _ocr_integer(page: fitz.Page, rect: fitz.Rect, *, lower: int, upper: int) -> int | None:
    if pytesseract is None or Image is None:
        return None
    try:
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(4, 4),
            clip=rect,
            colorspace=fitz.csGRAY,
            alpha=False,
        )
        image = Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
        text = pytesseract.image_to_string(image, lang="eng", config=_TABLE_OCR_CONFIG)
    except Exception:
        return None
    values = {int(value) for value in re.findall(r"\d{1,3}", str(text or ""))}
    if len(values) != 1:
        return None
    value = values.pop()
    return value if lower <= value <= upper else None


def extract_braschi_floor_table_ocr(document: fitz.Document) -> tuple[int, int, int] | None:
    """Lee la tabla Braschi de pisos y sótanos mediante OCR local y acotado.

    La estrategia se limita a una plantilla reconocida: busca ambos encabezados
    estructurales, recorta únicamente sus celdas contiguas y exige un entero
    único para cada campo. Cualquier lectura incompleta o ambigua se descarta.
    """
    if pytesseract is None or Image is None:
        return None
    for page_index in range(min(len(document), 10)):
        page = document[page_index]
        floor_rect = _header_rect(page, _BRASCHI_FLOORS_TERMS)
        basement_rect = _header_rect(page, _BRASCHI_BASEMENTS_TERMS)
        if floor_rect is None or basement_rect is None:
            continue
        floors = _ocr_integer(page, floor_rect, lower=1, upper=150)
        basements = _ocr_integer(page, basement_rect, lower=0, upper=50)
        if floors is not None and basements is not None:
            return floors, basements, page_index + 1
    return None
