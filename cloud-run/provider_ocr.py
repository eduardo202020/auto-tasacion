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
