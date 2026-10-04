"""Lectura de catálogos de ubicación usados por la macro MASIVO.

El libro se conserva junto al servicio para que la imagen desplegada no dependa
de un archivo local del operador. Solo se devuelve un código cuando existe una
coincidencia explícita; nunca se completa con Lima u otro valor por defecto.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import unicodedata

from openpyxl import load_workbook


CATALOG_PATH = Path(__file__).parent / "reference-data" / "catalogos_tasaciones.xlsx"


def normalize(value: object) -> str:
    text = "" if value is None else str(value)
    text = "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return " ".join(text.upper().split())


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, dict]:
    """Carga los tres niveles geográficos desde el catálogo corporativo."""
    if not CATALOG_PATH.exists():
        return {"departments": {}, "provinces": {}, "districts": {}, "district_names": {}}

    workbook = load_workbook(CATALOG_PATH, read_only=True, data_only=True)
    sheet = workbook.active
    departments: dict[str, str] = {}
    provinces: dict[tuple[str, str], str] = {}
    districts: dict[tuple[str, str, str], str] = {}
    district_names: dict[str, set[tuple[str, str, str]]] = {}
    province_department = {}
    current_province_department = ""
    current_province = ""
    current_district_department = ""
    current_district_province = ""

    # El catálogo tiene tres listas paralelas: B:C (departamentos), E:G
    # (departamento/provincia/código) e I:J (distritos por provincia).
    for row in sheet.iter_rows(min_row=3, values_only=True):
        department, department_code = row[1], row[2]
        group_department, province, province_code = row[4], row[5], row[6]
        district, district_code = row[8], row[9]

        normalized_department = normalize(department)
        if normalized_department and department_code is not None and str(department_code).strip():
            departments[normalized_department] = str(department_code).strip().zfill(2)

        normalized_group_department = normalize(group_department)
        if normalized_group_department:
            current_province_department = normalized_group_department
        normalized_province = normalize(province)
        if normalized_province and current_province_department and province_code is not None and str(province_code).strip():
            key = (current_province_department, normalized_province)
            provinces[key] = str(province_code).strip().zfill(2)
            province_department.setdefault(normalized_province, set()).add(current_province_department)

        normalized_district = normalize(district)
        if normalized_district.startswith("DISTRITOS "):
            current_district_province = normalized_district.removeprefix("DISTRITOS ").strip()
            owners = province_department.get(current_district_province, set())
            current_district_department = next(iter(owners)) if len(owners) == 1 else ""
            continue
        if normalized_district and district_code is not None and str(district_code).strip():
            # La primera lista de distritos de Lima no tiene encabezado propio;
            # conserva el último departamento/provincia declarado en E:G.
            if not current_district_province:
                current_district_department = current_province_department
                current_district_province = normalized_province
            if current_district_department and current_district_province:
                code = str(district_code).strip().zfill(3)
                key = (current_district_department, current_district_province, normalized_district)
                districts[key] = code
                district_names.setdefault(normalized_district, set()).add(key)

    workbook.close()
    return {
        "departments": departments,
        "provinces": provinces,
        "districts": districts,
        "district_names": district_names,
    }


def lookup_location(department: object, province: object, district: object) -> dict[str, str]:
    """Obtiene códigos de departamento, provincia y distrito sin adivinar."""
    catalog = load_catalog()
    dept = normalize(department)
    prov = normalize(province)
    dist = normalize(district)
    result = {
        "DEPARTAMENTO": dept,
        "PROVINCIA": prov,
        "DISTRITO": dist,
        "DEPARTAMENTO_COD": catalog["departments"].get(dept, ""),
        "PROVINCIA_COD": catalog["provinces"].get((dept, prov), ""),
        "DISTRITO_COD": catalog["districts"].get((dept, prov, dist), ""),
    }

    # Un distrito inequívoco puede resolverse aunque el PDF no indique uno de
    # los niveles superiores; si tiene más de una ubicación se deja vacío.
    if not result["DISTRITO_COD"] and dist:
        matches = catalog["district_names"].get(dist, set())
        if len(matches) == 1:
            dep, pro, _ = next(iter(matches))
            result["DEPARTAMENTO"] = result["DEPARTAMENTO"] or dep
            result["PROVINCIA"] = result["PROVINCIA"] or pro
            result["DEPARTAMENTO_COD"] = catalog["departments"].get(dep, "")
            result["PROVINCIA_COD"] = catalog["provinces"].get((dep, pro), "")
            result["DISTRITO_COD"] = catalog["districts"].get((dep, pro, dist), "")
    return result
