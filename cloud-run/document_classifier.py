"""Clasificacion conservadora del tipo documental antes de extraer campos."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable


@dataclass(frozen=True)
class DocumentClassification:
    document_type: str
    reason_code: str


def _normalize(text: object) -> str:
    plain = "".join(
        char for char in unicodedata.normalize("NFKD", str(text or ""))
        if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", plain.upper()).strip()


TASACION_MARKERS = (
    r"\bTASACION\b",
    r"\bVALUACION\b",
    r"\bVALOR\s+COMERCIAL\b",
    r"\bVALOR(?:ES)?\s+DE\s+RECONSTRUCCION\b",
    r"\bVALOR\s+DE\s+REPOSICION\b",
    r"\bSOLICITUD\s+CONSTRUYO\b",
    r"\bEDAD\s+EFECTIVA\b",
    r"\bANO\s+DE\s+(?:CONSTRUCCION|EDIFICACION)\b",
    r"\bVIVIENDA\s+UNIFAMILIAR\b",
)
# A bare reference to a valuation is common in a legal title study. The
# remaining markers identify the valuation document itself.
STRONG_TASACION_MARKERS = TASACION_MARKERS[1:]
TITLE_STUDY_RE = re.compile(r"\bESTUDIO\s+DE\s+TITULOS?\b")
LEGAL_STUDY_MARKERS = (
    r"\bPARTIDA\s+(?:ELECTRONICA|REGISTRAL)\b",
    r"\bASIENTO(?:S)?\s+(?:REGISTRAL(?:ES)?|DE\s+INSCRIPCION)?\b",
    r"\bREGISTROS?\s+PUBLICOS\b",
    r"\bCARGAS?\s+Y\s+GRAVAMENES\b",
    r"\bTITULAR(?:IDAD)?\s+REGISTRAL\b",
    r"\bANTECEDENTES\s+REGISTRALES?\b",
)


def text_is_insufficient(page_texts: Iterable[str]) -> bool:
    """Whether the text layer is too thin to classify the document safely.

    This only allows bounded local OCR for classification and provider metadata;
    it never promotes OCR output to a critical extracted value.
    """
    normalized = _normalize(" ".join(str(page or "") for page in page_texts))
    return len(re.sub(r"[^A-Z0-9]", "", normalized)) < 80


def classify_document(page_texts: Iterable[str]) -> DocumentClassification:
    """Classify only when the document contains unambiguous textual evidence."""
    pages = tuple(_normalize(page) for page in page_texts)
    text = " ".join(pages)
    early_pages = " ".join(pages[:2])
    has_strong_valuation_evidence = any(re.search(marker, text) for marker in STRONG_TASACION_MARKERS)
    legal_evidence = sum(bool(re.search(marker, text)) for marker in LEGAL_STUDY_MARKERS)
    # A title study must identify itself on its first pages and carry a legal
    # marker. A strong valuation signal anywhere in the document prevents an
    # annex from changing the document type.
    if TITLE_STUDY_RE.search(early_pages) and legal_evidence >= 1 and not has_strong_valuation_evidence:
        return DocumentClassification("ESTUDIO_TITULOS", "DOCUMENTO_NO_TASACION")
    if any(re.search(marker, text) for marker in TASACION_MARKERS):
        return DocumentClassification("TASACION", "")
    return DocumentClassification("DESCONOCIDO", "DOCUMENTO_TIPO_DESCONOCIDO")
