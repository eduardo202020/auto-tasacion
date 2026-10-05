"""Revisión excepcional de tasaciones mediante Gemini.

La IA nunca recibe el lote completo ni decide por sí misma que un caso es
operable. Solo analiza el PDF de un caso excepcional y devuelve propuestas
estructuradas con evidencia. ``service.py`` valida cada propuesta contra el
contrato de integración y los catálogos antes de mover una fila a
``PARA_PROCESAR``.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol


AI_FIELDS = (
    "Direccion extraida",
    "Tipo inmueble",
    "Valor elegido US$",
    "Valor elegido S/",
    "Nro pisos edificio",
    "Nro sotanos edificio",
    "Año construccion",
)


class AiReviewUnavailable(RuntimeError):
    """La revisión IA fue solicitada pero no puede ejecutarse."""


class CaseReviewer(Protocol):
    """Interfaz inyectable para revisar una única excepción."""

    model_name: str

    def review(
        self,
        pdf_content: bytes,
        *,
        case_id: str,
        requested_fields: list[str],
        observations: list[str],
        extracted: dict[str, Any],
        approved_rules: list[str],
    ) -> dict[str, Any]: ...


REVIEW_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "decision": {"type": "STRING", "enum": ["RESUELTO", "SIN_EVIDENCIA"]},
        "reason": {"type": "STRING"},
        "corrections": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "field": {"type": "STRING", "enum": list(AI_FIELDS)},
                    "value": {"type": "STRING"},
                    "page": {"type": "INTEGER"},
                    "evidence": {"type": "STRING"},
                    "rule": {"type": "STRING"},
                },
                "required": ["field", "value", "page", "evidence"],
            },
        },
    },
    "required": ["decision", "reason", "corrections"],
}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "si", "sí", "yes"}


def _parse_json_response(value: object) -> dict[str, Any]:
    raw = str(value or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise AiReviewUnavailable("La IA no devolvió una respuesta JSON válida") from error
    if not isinstance(parsed, dict):
        raise AiReviewUnavailable("La IA no devolvió un objeto de revisión válido")
    return parsed


class GeminiReviewer:
    """Cliente Gemini de uso puntual, sin registro de PDFs ni secretos."""

    def __init__(self, api_key: str, model_name: str):
        self._api_key = api_key
        self.model_name = model_name

    def review(
        self,
        pdf_content: bytes,
        *,
        case_id: str,
        requested_fields: list[str],
        observations: list[str],
        extracted: dict[str, Any],
        approved_rules: list[str],
    ) -> dict[str, Any]:
        if not requested_fields:
            return {
                "decision": "SIN_EVIDENCIA",
                "reason": "No existe un campo faltante autorizable para revisión IA",
                "corrections": [],
            }
        try:
            from google import genai
            from google.genai import types
        except ImportError as error:
            raise AiReviewUnavailable("La dependencia google-genai no está disponible") from error

        prompt = self._build_prompt(
            case_id=case_id,
            requested_fields=requested_fields,
            observations=observations,
            extracted=extracted,
            approved_rules=approved_rules,
        )
        try:
            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self.model_name,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=pdf_content, mime_type="application/pdf"),
                ],
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=REVIEW_SCHEMA,
                ),
            )
        except Exception as error:
            raise AiReviewUnavailable("No fue posible completar la revisión IA") from error
        return _parse_json_response(getattr(response, "text", ""))

    @staticmethod
    def _build_prompt(
        *,
        case_id: str,
        requested_fields: list[str],
        observations: list[str],
        extracted: dict[str, Any],
        approved_rules: list[str],
    ) -> str:
        safe_extracted = {
            key: extracted.get(key, "")
            for key in (
                "ID / Codigo PDF", "Direccion extraida", "Tipo inmueble",
                "Valor elegido tipo", "Valor elegido US$", "Valor elegido S/",
                "Nro pisos edificio", "Nro sotanos edificio", "Año construccion",
                "Año expedicion", "Edad efectiva",
            )
        }
        rules = approved_rules or ["No hay una regla de negocio aprobada para resolver conflictos entre fuentes."]
        return "\n".join(
            [
                "Eres un verificador documental de tasaciones hipotecarias.",
                "Revisa exclusivamente el PDF adjunto. No uses conocimiento externo ni inventes valores.",
                "Solo puedes proponer los campos solicitados. Cada corrección debe incluir una cita textual corta y la página del PDF.",
                "Si una fuente contradice otra y las reglas aprobadas no resuelven la prioridad, devuelve SIN_EVIDENCIA sin correcciones para ese campo.",
                "Los valores permitidos para Tipo inmueble son CASA o DEPARTAMENTO.",
                "Los importes deben ser números sin símbolo de moneda. Pisos, sótanos y año deben ser enteros.",
                f"ID técnico del caso: {case_id}",
                f"Campos solicitados: {json.dumps(requested_fields, ensure_ascii=False)}",
                f"Observaciones deterministas: {json.dumps(observations, ensure_ascii=False)}",
                f"Valores deterministas actuales: {json.dumps(safe_extracted, ensure_ascii=False)}",
                f"Reglas de negocio aprobadas: {json.dumps(rules, ensure_ascii=False)}",
                "Devuelve exclusivamente el JSON solicitado por el esquema.",
            ]
        )


def reviewer_from_environment() -> CaseReviewer | None:
    """Crea el revisor solo con habilitación explícita de entorno.

    La clave no se registra ni se escribe en el XLSX. Debe llegar a Cloud Run
    desde Secret Manager, nunca desde un archivo versionado.
    """
    if not _truthy(os.getenv("AI_REVIEW_ENABLED")):
        return None
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "").strip()
    if not api_key or not model_name:
        raise AiReviewUnavailable("La revisión IA está habilitada pero GEMINI_API_KEY o GEMINI_MODEL no están configurados")
    return GeminiReviewer(api_key=api_key, model_name=model_name)
