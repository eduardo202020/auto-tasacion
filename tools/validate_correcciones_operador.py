"""Valida la bitácora de correcciones manuales de perfiles de tasación.

La bitácora no cambia perfiles ni reglas operativas. Sirve para que una
corrección tenga la llave del caso, evidencia y responsable antes de analizar
si debe convertirse en una mejora técnica.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import date
import json
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = (
    "ID_CASO", "PDF_Archivo", "Perfil plantilla", "Campo", "Valor extraido",
    "Valor final", "Pagina", "Evidencia", "Motivo", "Operador", "Fecha",
)
REQUIRED_VALUES = (
    "ID_CASO", "PDF_Archivo", "Perfil plantilla", "Campo", "Valor final",
    "Pagina", "Evidencia", "Motivo", "Operador", "Fecha",
)


def _blank(value: object) -> bool:
    return value is None or not str(value).strip()


def validate(path: Path) -> tuple[dict[str, Any], list[str]]:
    """Entrega resumen seguro y errores de estructura de una bitácora CSV."""
    issues: list[str] = []
    summary: dict[str, Any] = {"filas_validas": 0, "por_perfil": {}, "por_campo": {}}
    if not path.is_file():
        return summary, [f"No existe el archivo: {path}"]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, delimiter=";")
            headers = tuple(reader.fieldnames or ())
            missing_columns = [column for column in REQUIRED_COLUMNS if column not in headers]
            if missing_columns:
                return summary, [f"Faltan columnas obligatorias: {', '.join(missing_columns)}"]
            per_profile: Counter[str] = Counter()
            per_field: Counter[str] = Counter()
            for row_number, row in enumerate(reader, start=2):
                if all(_blank(row.get(column)) for column in headers):
                    continue
                missing_values = [column for column in REQUIRED_VALUES if _blank(row.get(column))]
                if missing_values:
                    issues.append(f"Fila {row_number}: faltan valores en {', '.join(missing_values)}")
                    continue
                case_id = str(row["ID_CASO"]).strip()
                if not case_id.startswith("TAS-"):
                    issues.append(f"Fila {row_number}: ID_CASO debe iniciar con TAS-")
                    continue
                try:
                    page = int(str(row["Pagina"]).strip())
                    if page < 1:
                        raise ValueError
                except ValueError:
                    issues.append(f"Fila {row_number}: Pagina debe ser un entero mayor o igual a 1")
                    continue
                try:
                    date.fromisoformat(str(row["Fecha"]).strip())
                except ValueError:
                    issues.append(f"Fila {row_number}: Fecha debe usar el formato AAAA-MM-DD")
                    continue
                profile = str(row["Perfil plantilla"]).strip()
                field = str(row["Campo"]).strip()
                per_profile[profile] += 1
                per_field[field] += 1
                summary["filas_validas"] += 1
            summary["por_perfil"] = dict(sorted(per_profile.items()))
            summary["por_campo"] = dict(sorted(per_field.items()))
    except UnicodeDecodeError:
        return summary, ["El CSV debe estar codificado como UTF-8"]
    except csv.Error as error:
        return summary, [f"No se pudo leer el CSV: {error}"]
    return summary, issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida una bitácora de correcciones de tasaciones")
    parser.add_argument("csv_file", type=Path, help="Ruta al CSV separado por punto y coma")
    args = parser.parse_args()
    summary, issues = validate(args.csv_file)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for issue in issues:
        print(f"ERROR: {issue}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
