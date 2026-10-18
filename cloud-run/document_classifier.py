"""Clasificación conservadora del tipo documental antes de extraer campos.

No intenta adivinar si un PDF es una tasación. Una firma inequívoca de
``ESTUDIO DE TÍTULOS`` se excluye antes de la extracción operativa; una
tasación requiere al menos una señal propia del informe. El resultado solo
contiene códigos seguros para trazabilidad, nunca fragmentos del documento.
"""
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


def classify_document(page_texts: Iterable[str]) -> DocumentClassification:
    """Clasifica exclusivamente con evidencia textual inequívoca."""
    text = _normalize(" ".join(str(page or "") for page in page_texts))
    if re.search(r"\bESTUDIO\s+DE\s+TITULOS?\b", text):
        return DocumentClassification("ESTUDIO_TITULOS", "DOCUMENTO_NO_TASACION")

    tasacion_markers = (
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
    if any(re.search(marker, text) for marker in tasacion_markers):
        return DocumentClassification("TASACION", "")
    return DocumentClassification("DESCONOCIDO", "DOCUMENTO_TIPO_DESCONOCIDO")
