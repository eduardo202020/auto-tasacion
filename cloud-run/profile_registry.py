"""Registro versionado de perfiles de formato para informes de tasación.

Un perfil identifica la plantilla documental y solo puede aportar alias de
etiquetas de extracción. No modifica prioridades de negocio, catálogos ni el
enrutamiento de un caso. Si no hay coincidencia, se usa siempre el perfil
genérico para conservar el comportamiento existente.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable


REFERENCE_DATA = Path(__file__).parent / "reference-data"
PROFILES_DIR = REFERENCE_DATA / "profiles"
PROVIDERS_FILE = REFERENCE_DATA / "tasadoras.json"


@dataclass(frozen=True)
class ProfileDefinition:
    profile_id: str
    version: str
    is_default: bool
    priority: int
    provider_id: str
    all_terms: tuple[str, ...]
    any_terms: tuple[str, ...]
    anchor_aliases: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class DocumentProfile:
    """Perfil seleccionado y metadatos seguros para la trazabilidad."""

    profile_id: str
    version: str
    provider_id: str
    provider_name: str
    confidence: float
    matched_terms: tuple[str, ...]
    anchor_aliases: dict[str, tuple[str, ...]]


GENERIC_PROFILE = DocumentProfile(
    profile_id="generic-v1",
    version="1",
    provider_id="",
    provider_name="",
    confidence=0.0,
    matched_terms=(),
    anchor_aliases={},
)


def normalize(text: object) -> str:
    plain = "".join(
        char for char in unicodedata.normalize("NFKD", str(text or ""))
        if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", plain.upper()).strip()


def _as_terms(value: object, field: str, profile_path: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{profile_path.name}: {field} debe ser una lista de textos")
    return tuple(term for term in (normalize(item) for item in value) if term)


def _load_profile(path: Path) -> ProfileDefinition:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"No se pudo leer el perfil {path.name}: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: el perfil debe ser un objeto JSON")

    profile_id = str(raw.get("id", "")).strip()
    version = str(raw.get("version", "")).strip()
    if not profile_id or not version:
        raise ValueError(f"{path.name}: id y version son obligatorios")
    match = raw.get("match", {})
    extraction = raw.get("extraction", {})
    if not isinstance(match, dict) or not isinstance(extraction, dict):
        raise ValueError(f"{path.name}: match y extraction deben ser objetos")
    aliases = extraction.get("anchor_aliases", {})
    if not isinstance(aliases, dict):
        raise ValueError(f"{path.name}: extraction.anchor_aliases debe ser un objeto")

    normalized_aliases: dict[str, tuple[str, ...]] = {}
    for field, values in aliases.items():
        if not isinstance(field, str) or not field.strip():
            raise ValueError(f"{path.name}: cada alias debe indicar un campo")
        normalized_aliases[field.strip()] = _as_terms(values, f"anchor_aliases.{field}", path)

    all_terms = _as_terms(match.get("all_terms"), "match.all_terms", path)
    any_terms = _as_terms(match.get("any_terms"), "match.any_terms", path)
    is_default = bool(raw.get("default", False))
    if not is_default and not all_terms and not any_terms:
        raise ValueError(f"{path.name}: un perfil no predeterminado requiere una firma")

    return ProfileDefinition(
        profile_id=profile_id,
        version=version,
        is_default=is_default,
        priority=int(raw.get("priority", 0)),
        provider_id=str(raw.get("provider_id", "")).strip(),
        all_terms=all_terms,
        any_terms=any_terms,
        anchor_aliases=normalized_aliases,
    )


@lru_cache(maxsize=1)
def load_profiles() -> tuple[ProfileDefinition, ...]:
    """Carga perfiles declarativos y confirma un único respaldo genérico."""
    try:
        profiles = tuple(_load_profile(path) for path in sorted(PROFILES_DIR.glob("*.json")))
    except Exception:
        # Un error de configuración no puede detener un lote ni cambiar la
        # decisión existente: el extractor genérico sigue siendo seguro.
        return ()
    defaults = [profile for profile in profiles if profile.is_default]
    if len(defaults) != 1:
        return ()
    return profiles


@lru_cache(maxsize=1)
def load_providers() -> dict[str, tuple[str, tuple[str, ...]]]:
    """Carga la lista aprobada de tasadoras, vacía hasta contar con altas."""
    try:
        raw = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
        providers = raw.get("providers", []) if isinstance(raw, dict) else []
        result: dict[str, tuple[str, tuple[str, ...]]] = {}
        for provider in providers:
            if not isinstance(provider, dict):
                continue
            provider_id = str(provider.get("id", "")).strip()
            name = str(provider.get("name", "")).strip()
            aliases = provider.get("aliases", [])
            if not provider_id or not name or not isinstance(aliases, list):
                continue
            normalized_aliases = tuple(
                alias for alias in (normalize(value) for value in aliases if isinstance(value, str)) if alias
            )
            if normalized_aliases:
                result[provider_id] = (name, normalized_aliases)
        return result
    except (OSError, json.JSONDecodeError):
        return {}


def _provider_for(text: str, preferred_id: str) -> tuple[str, str]:
    providers = load_providers()
    if preferred_id and preferred_id in providers:
        return preferred_id, providers[preferred_id][0]
    matches = [
        (provider_id, name)
        for provider_id, (name, aliases) in providers.items()
        if any(alias in text for alias in aliases)
    ]
    return matches[0] if len(matches) == 1 else ("", "")


def _matching_terms(profile: ProfileDefinition, text: str) -> tuple[str, ...] | None:
    if any(term not in text for term in profile.all_terms):
        return None
    matched_any = tuple(term for term in profile.any_terms if term in text)
    if profile.any_terms and not matched_any:
        return None
    return (*profile.all_terms, *matched_any)


def detect_document_profile(page_texts: Iterable[str]) -> DocumentProfile:
    """Selecciona el perfil con firma explícita; sin firma devuelve genérico.

    El puntaje solo resuelve perfiles técnicos que ya declararon su firma.
    No se infiere una tasadora ni se crean reglas desde el contenido del PDF.
    """
    text = normalize(" ".join(page_texts))
    profiles = load_profiles()
    if not profiles:
        return GENERIC_PROFILE
    candidates: list[tuple[int, int, ProfileDefinition, tuple[str, ...]]] = []
    for profile in profiles:
        matched = _matching_terms(profile, text)
        if matched is None:
            continue
        score = len(matched)
        candidates.append((score, profile.priority, profile, matched))
    if not candidates:
        return GENERIC_PROFILE
    score, _, selected, matched = max(candidates, key=lambda item: (item[0], item[1], item[2].profile_id))
    if selected.is_default and score == 0:
        provider_id, provider_name = _provider_for(text, "")
        return DocumentProfile(
            profile_id=GENERIC_PROFILE.profile_id,
            version=GENERIC_PROFILE.version,
            provider_id=provider_id,
            provider_name=provider_name,
            confidence=GENERIC_PROFILE.confidence,
            matched_terms=GENERIC_PROFILE.matched_terms,
            anchor_aliases=GENERIC_PROFILE.anchor_aliases,
        )
    provider_id, provider_name = _provider_for(text, selected.provider_id)
    confidence = min(0.95, round(0.6 + (0.15 * score), 2))
    return DocumentProfile(
        profile_id=selected.profile_id,
        version=selected.version,
        provider_id=provider_id,
        provider_name=provider_name,
        confidence=confidence,
        matched_terms=matched,
        anchor_aliases=selected.anchor_aliases,
    )


def profile_anchor_aliases(profile: DocumentProfile, field: str) -> tuple[str, ...]:
    """Devuelve aliases normalizados para un ancla sin cambiar la regla base."""
    return profile.anchor_aliases.get(field, ())
