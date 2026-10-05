"""Endpoint Power Automate -> Cloud Run -> OneDrive para tasaciones.

El XLSX separa la cola operable de las excepciones:

* ``PARA_PROCESAR``: única tabla que Power Automate puede enviar a IBM 3270.
* ``REVISION_IA``: casos sin resolver tras validación determinista e IA.
* ``CONTROL``: trazabilidad completa de todos los PDFs del lote.

Ninguna respuesta de IA llega directamente a la cola de operación: se vuelve a
validar contra el contrato y los catálogos antes de incorporarla.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import zipfile
from typing import Any

import functions_framework
import pandas as pd
from flask import Response
from openpyxl.worksheet.table import Table, TableStyleInfo

import address_parser
from ai_reviewer import AI_FIELDS, AiReviewUnavailable, CaseReviewer, reviewer_from_environment
from catalog import (
    lookup_class_code,
    lookup_currency_code,
    lookup_direction_code,
    lookup_location,
    lookup_property_codes,
)
from pdf_extractor import extract_pdf


MAX_PDFS_PER_BATCH = 300
MAX_ZIP_BYTES = 75 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
# Gemini admite PDFs inline de hasta 50 MB. Los mayores deben pasar por el
# mecanismo corporativo aprobado (por ejemplo, OCR o File API), nunca forzarse.
MAX_INLINE_AI_PDF_BYTES = 50 * 1024 * 1024

PARA_PROCESAR_SHEET = "PARA_PROCESAR"
REVISION_IA_SHEET = "REVISION_IA"
CONTROL_SHEET = "CONTROL"

MACRO_COLUMNS = [
    "PRESTAMO", "TIPO DE INMUEBLE", "VALOR DEL BIEN", "MONEDA", "IMPORTE", "COL_F",
    "DIRECCION", "DIRECCION1", "EXTERIOR", "INTERIOR", "REFERENCIA", "COL_L",
    "UBICACION", "UBICACION1", "MUNICIPIO", "DIST_COD", "COL_Q", "PROV_COD",
    "COL_S", "DEPT_COD", "CLASE", "PISOS", "SOTANOS", "AÑO",
]
# Se añade al final para no desplazar las 24 columnas heredadas de MASIVO.
# Ahora que no hay macro, Power Automate usa esta llave para trazar el resultado
# de IBM 3270 contra CONTROL.
PARA_PROCESAR_COLUMNS = [*MACRO_COLUMNS, "ID_CASO"]

# PRESTAMO se obtiene después de la operación en IBM 3270. Las columnas COL_*
# son reservadas. Los demás campos son el mínimo codificado para operar.
REQUIRED_MACRO_COLUMNS = (
    "TIPO DE INMUEBLE", "VALOR DEL BIEN", "MONEDA", "IMPORTE",
    "DIRECCION", "DIRECCION1", "MUNICIPIO", "DIST_COD", "PROV_COD",
    "DEPT_COD", "CLASE", "PISOS", "SOTANOS", "AÑO",
)

CONTROL_COLUMNS = [
    "ID_CASO", "ID / Codigo PDF", "PDF_Archivo", "PRESTAMO", "Direccion extraida", "Pagina direccion",
    "Tipo inmueble", "Tipo inmueble texto", "Pagina tipo inmueble", "Valor elegido tipo",
    "Valor elegido US$", "Valor elegido S/", "Valor comercial US$", "Valor comercial S/",
    "Pagina valor comercial", "Valor reconstruccion US$", "Valor reconstruccion S/",
    "Pagina valor reconstruccion", "Año construccion", "Pagina año construccion",
    "Origen año construccion", "Edad efectiva", "Pagina edad efectiva",
    "Año expedicion", "Pagina año expedicion", "Codigo tipo inmueble", "Codigo MASIVO",
    "Codigo valor del bien", "Nro pisos edificio", "Nro sotanos edificio", "Pagina pisos/sotanos",
    "Observacion extraccion", "Campos faltantes", "Incidencias de validacion", "Ruta final",
    "Revision IA ejecutada", "Modelo IA", "Campos enviados a IA", "Motivo IA",
    "Correcciones IA", "Evidencia IA", "Fila PARA_PROCESAR",
]

REVIEW_COLUMNS = [
    "ID_CASO", "PDF_Archivo", "Estado", "Campos faltantes", "Incidencias de validacion",
    "Campos enviados a IA", "Motivo IA", "Correcciones IA", "Evidencia IA", "Modelo IA",
    "Siguiente accion",
]

AI_TARGETS_BY_MACRO_FIELD = {
    "TIPO DE INMUEBLE": ("Tipo inmueble",),
    "VALOR DEL BIEN": ("Valor elegido US$", "Valor elegido S/"),
    "MONEDA": ("Valor elegido US$", "Valor elegido S/"),
    "IMPORTE": ("Valor elegido US$", "Valor elegido S/"),
    "DIRECCION": ("Direccion extraida",),
    "DIRECCION1": ("Direccion extraida",),
    "MUNICIPIO": ("Direccion extraida",),
    "DIST_COD": ("Direccion extraida",),
    "PROV_COD": ("Direccion extraida",),
    "DEPT_COD": ("Direccion extraida",),
    "CLASE": ("Nro pisos edificio",),
    "PISOS": ("Nro pisos edificio",),
    "SOTANOS": ("Nro sotanos edificio",),
    "AÑO": ("Año construccion",),
}

TRANSIENT_EXTRACTION_OBSERVATIONS = (
    "Dirección no encontrada", "Tipo de inmueble no determinado", "Valor comercial no encontrado",
    "Valor de reconstrucción no encontrado", "Año de construcción", "Número de pisos no encontrado",
    "Número de sótanos no encontrado", "Préstamo de 20 dígitos no encontrado",
)
RULES_PATH = Path(__file__).parent / "reference-data" / "reglas_operativas.json"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def as_excel_value(value: Any) -> Any:
    return "" if value is None else value


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if item and item.strip()))


def json_cell(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ": ")) if value else ""


def build_case_id(filename: str, content: bytes) -> str:
    """Identificador técnico estable para trazar el PDF sin alterar MASIVO."""
    return f"TAS-{hashlib.sha256(content).hexdigest()[:16].upper()}"


def load_approved_rules() -> list[str]:
    """Lee exclusivamente reglas aprobadas y versionadas para la IA."""
    if not RULES_PATH.exists():
        return []
    try:
        payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rules = payload.get("rules", []) if isinstance(payload, dict) else []
    return [str(rule).strip() for rule in rules if str(rule).strip()]


def choose_value(extracted: dict[str, Any]) -> tuple[Any, str]:
    usd = extracted.get("Valor elegido US$")
    pen = extracted.get("Valor elegido S/")
    if not is_blank(usd):
        return usd, "USD"
    if not is_blank(pen):
        return pen, "PEN"
    return "", ""


def parse_address(extracted: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    observations: list[str] = []
    raw_address = str(extracted.get("Direccion extraida") or "")
    if not raw_address:
        return {}, ["No se puede estructurar la dirección porque no fue extraída"]
    try:
        parsed = address_parser.parse_direccion(raw_address)
    except Exception:
        return {}, ["No se pudo estructurar la dirección"]

    parsed.update(lookup_location(
        parsed.get("DEPARTAMENTO", ""), parsed.get("PROVINCIA", ""), parsed.get("DISTRITO", ""),
    ))
    for field, label in (
        ("DISTRITO_COD", "código de distrito"),
        ("PROVINCIA_COD", "código de provincia"),
        ("DEPARTAMENTO_COD", "código de departamento"),
    ):
        if not parsed.get(field):
            observations.append(f"{label.capitalize()} no encontrado en catálogo")
    return parsed, observations


def to_macro_row(extracted: dict[str, Any]) -> tuple[list[Any], list[str]]:
    """Crea una fila compatible con Power Automate sin clasificarla aún."""
    parsed, observations = parse_address(extracted)
    value, currency = choose_value(extracted)
    pisos = extracted.get("Nro pisos edificio", "")
    tipo = str(extracted.get("Tipo inmueble") or "")
    property_codes = lookup_property_codes(tipo)
    currency_code = lookup_currency_code(currency)
    via_code = lookup_direction_code(parsed.get("TIPO VIA 1", ""))
    ubicacion_code = lookup_direction_code(parsed.get("UBICACION TIPO", ""))

    extracted["Codigo tipo inmueble"] = property_codes["tipo_inmueble"]
    extracted["Codigo MASIVO"] = property_codes["masivo"]
    extracted["Codigo valor del bien"] = property_codes["valor_del_bien"]
    if tipo and not property_codes["masivo"]:
        observations.append("Tipo de inmueble sin código autorizado en DATOS")
    if currency and not currency_code:
        observations.append("Moneda sin código autorizado en DATOS")
    if parsed.get("TIPO VIA 1") and not via_code:
        observations.append("Tipo de vía sin abreviatura autorizada en DATOS")
    if parsed.get("UBICACION TIPO") and not ubicacion_code:
        observations.append("Ubicación sin abreviatura autorizada en DATOS")

    row = [""] * len(MACRO_COLUMNS)
    row[0] = extracted.get("PRESTAMO", "")
    row[1] = property_codes["masivo"]
    row[2] = as_excel_value(value)
    row[3] = currency_code
    row[4] = as_excel_value(value)
    row[6] = via_code
    row[7] = parsed.get("DOMICILIO 1", "")
    row[8] = parsed.get("N. EXTERIOR", "")
    row[9] = parsed.get("N. INTERIOR", "")
    row[10] = parsed.get("REFERENCIA", "")
    row[12] = ubicacion_code
    row[13] = parsed.get("UBICACION 1", "")
    row[14] = parsed.get("DISTRITO", "")
    row[15] = parsed.get("DISTRITO_COD", "")
    row[17] = parsed.get("PROVINCIA_COD", "")
    row[19] = parsed.get("DEPARTAMENTO_COD", "")
    row[20] = lookup_class_code(pisos)
    row[21] = as_excel_value(pisos)
    row[22] = as_excel_value(extracted.get("Nro sotanos edificio", ""))
    row[23] = as_excel_value(extracted.get("Año construccion", ""))
    return row, observations


def persistent_extraction_observations(extracted: dict[str, Any]) -> list[str]:
    """Conserva conflictos y errores, no vacíos que la IA podría corregir."""
    observations = [item.strip() for item in str(extracted.get("Observacion extraccion") or "").split(";") if item.strip()]
    return [item for item in observations if not any(item.startswith(prefix) for prefix in TRANSIENT_EXTRACTION_OBSERVATIONS)]


def assess_case(extracted: dict[str, Any]) -> tuple[list[Any], list[str], list[str]]:
    row, address_observations = to_macro_row(extracted)
    field_values = dict(zip(MACRO_COLUMNS, row))
    missing = [field for field in REQUIRED_MACRO_COLUMNS if is_blank(field_values[field])]
    issues = unique([*persistent_extraction_observations(extracted), *address_observations])
    return row, missing, issues


def ai_targets(missing_fields: list[str], issues: list[str]) -> list[str]:
    targets: list[str] = []
    for field in missing_fields:
        targets.extend(AI_TARGETS_BY_MACRO_FIELD.get(field, ()))
    if any(any(word in issue.lower() for word in ("dirección", "distrito", "provincia", "ubicación")) for issue in issues):
        targets.append("Direccion extraida")
    return [target for target in AI_FIELDS if target in set(targets)]


def has_business_conflict(issues: list[str]) -> bool:
    return any(issue.startswith("Conflicto ") for issue in issues)


def _integer_value(value: object, *, lower: int, upper: int) -> int | None:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if lower <= parsed <= upper else None


def _amount_value(value: object) -> float | None:
    try:
        parsed = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def apply_ai_corrections(
    extracted: dict[str, Any],
    response: dict[str, Any],
    *,
    requested_fields: list[str],
    page_count: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Acepta solo correcciones solicitadas, tipadas y con evidencia."""
    accepted: list[dict[str, Any]] = []
    rejected: list[str] = []
    raw_corrections = response.get("corrections", [])
    if not isinstance(raw_corrections, list):
        return accepted, ["La IA devolvió correcciones con una estructura inválida"]

    for correction in raw_corrections:
        if not isinstance(correction, dict):
            rejected.append("La IA devolvió una corrección inválida")
            continue
        field = str(correction.get("field", "")).strip()
        evidence = str(correction.get("evidence", "")).strip()
        page = _integer_value(correction.get("page"), lower=1, upper=page_count)
        if field not in requested_fields or field not in AI_FIELDS:
            rejected.append("La IA propuso un campo no solicitado")
            continue
        if not evidence or page is None:
            rejected.append(f"La corrección IA para {field} no tiene evidencia de página válida")
            continue

        value: Any = correction.get("value", "")
        if field == "Tipo inmueble":
            value = str(value).strip().upper()
            if value not in {"CASA", "DEPARTAMENTO"}:
                rejected.append("La IA propuso un tipo de inmueble no autorizado")
                continue
            extracted["Tipo inmueble texto"] = value
            extracted["Valor elegido tipo"] = "VALOR COMERCIAL" if value == "DEPARTAMENTO" else "VALOR DE RECONSTRUCCION"
        elif field in {"Valor elegido US$", "Valor elegido S/"}:
            value = _amount_value(value)
            if value is None:
                rejected.append(f"La corrección IA para {field} no es un importe positivo")
                continue
        elif field == "Nro pisos edificio":
            value = _integer_value(value, lower=1, upper=150)
            if value is None:
                rejected.append("La corrección IA para pisos no es válida")
                continue
        elif field == "Nro sotanos edificio":
            value = _integer_value(value, lower=0, upper=50)
            if value is None:
                rejected.append("La corrección IA para sótanos no es válida")
                continue
        elif field == "Año construccion":
            value = _integer_value(value, lower=1900, upper=2100)
            if value is None:
                rejected.append("La corrección IA para año de construcción no es válida")
                continue
            extracted["Origen año construccion"] = "IA CON EVIDENCIA"
        else:
            value = str(value).strip()
            if len(value) < 8 or len(value) > 500:
                rejected.append("La corrección IA para dirección no es válida")
                continue

        extracted[field] = value
        accepted.append({
            "field": field, "value": value, "page": page, "evidence": evidence,
            "rule": str(correction.get("rule", "")).strip(),
        })
    return accepted, rejected


def pdf_page_count(content: bytes) -> int:
    import fitz

    with fitz.open(stream=content, filetype="pdf") as document:
        return max(len(document), 1)


def next_action(route: str) -> str:
    return {
        "PENDIENTE_IA": "Configurar o reintentar la revisión IA.",
        "REGLA_NEGOCIO_PENDIENTE": "Validar la regla de negocio y reprocesar.",
        "REVISION_HUMANA": "Completar o confirmar la evidencia antes de reprocesar.",
    }.get(route, "")


def validate_zip(raw_data: bytes) -> list[zipfile.ZipInfo]:
    if not raw_data.startswith(b"PK"):
        raise ValueError("El cuerpo debe ser un archivo ZIP válido")
    if len(raw_data) > MAX_ZIP_BYTES:
        raise ValueError("El ZIP excede el tamaño máximo permitido")
    with zipfile.ZipFile(io.BytesIO(raw_data)) as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir() and entry.filename.lower().endswith(".pdf")]
        if not entries:
            raise ValueError("El ZIP no contiene archivos PDF")
        if len(entries) > MAX_PDFS_PER_BATCH:
            raise ValueError(f"El ZIP supera el máximo de {MAX_PDFS_PER_BATCH} PDFs")
        if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("El contenido descomprimido excede el tamaño máximo permitido")
        if any(entry.flag_bits & 0x1 for entry in entries):
            raise ValueError("El ZIP contiene PDFs cifrados y no puede procesarse")
        return entries


def process_zip(
    raw_data: bytes,
    reviewer: CaseReviewer | None = None,
    *,
    use_environment_reviewer: bool = True,
) -> tuple[list[list[Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Clasifica el lote en cola operable, excepciones IA y control."""
    entries = validate_zip(raw_data)
    ready_rows: list[list[Any]] = []
    review_rows: list[dict[str, Any]] = []
    control_rows: list[dict[str, Any]] = []
    reviewer_error = ""
    if reviewer is None and use_environment_reviewer:
        try:
            reviewer = reviewer_from_environment()
        except AiReviewUnavailable as error:
            reviewer_error = str(error)
    approved_rules = load_approved_rules()

    with zipfile.ZipFile(io.BytesIO(raw_data)) as archive:
        for entry in entries:
            content = archive.read(entry)
            filename = entry.filename.rsplit("/", 1)[-1]
            case_id = build_case_id(entry.filename, content)
            if not content.startswith(b"%PDF-"):
                extracted: dict[str, Any] = {
                    "ID / Codigo PDF": filename.rsplit(".", 1)[0],
                    "PDF_Archivo": entry.filename,
                    "Observacion extraccion": "El archivo no tiene una firma PDF válida",
                }
            else:
                extracted = extract_pdf(content, filename)
            extracted["ID_CASO"] = case_id

            deterministic = dict(extracted)
            _, initial_missing, initial_issues = assess_case(deterministic)
            working = dict(deterministic)
            macro_row, missing_fields, issues = assess_case(working)
            route = "LISTO_DETERMINISTA" if not missing_fields and not issues else ""
            review_executed = False
            model_name = ""
            ai_reason = ""
            requested_fields = ai_targets(missing_fields, issues)
            accepted: list[dict[str, Any]] = []
            rejected: list[str] = []

            if not route:
                if has_business_conflict(issues) and not approved_rules:
                    route = "REGLA_NEGOCIO_PENDIENTE"
                    ai_reason = "Existe un conflicto entre fuentes sin una regla de negocio aprobada"
                elif len(content) > MAX_INLINE_AI_PDF_BYTES:
                    route = "PENDIENTE_IA"
                    ai_reason = "El PDF excede el límite de revisión IA inline y requiere una ruta aprobada"
                elif reviewer is None:
                    route = "PENDIENTE_IA"
                    ai_reason = reviewer_error or "La revisión IA no está habilitada"
                elif not requested_fields and has_business_conflict(issues):
                    route = "REGLA_NEGOCIO_PENDIENTE"
                    ai_reason = "Existe un conflicto entre fuentes sin una regla de negocio aprobada"
                elif not requested_fields:
                    route = "REVISION_HUMANA"
                    ai_reason = "No existe un campo autorizable para revisión IA"
                else:
                    review_executed = True
                    model_name = str(getattr(reviewer, "model_name", "IA"))
                    try:
                        response = reviewer.review(
                            content, case_id=case_id, requested_fields=requested_fields,
                            observations=issues, extracted=deterministic, approved_rules=approved_rules,
                        )
                        ai_reason = str(response.get("reason", "")).strip()
                        accepted, rejected = apply_ai_corrections(
                            working, response, requested_fields=requested_fields, page_count=pdf_page_count(content),
                        )
                        macro_row, missing_fields, issues = assess_case(working)
                        if not missing_fields and not issues:
                            route = "LISTO_IA_VERIFICADO"
                        elif has_business_conflict(issues):
                            route = "REGLA_NEGOCIO_PENDIENTE"
                        else:
                            route = "REVISION_HUMANA"
                    except AiReviewUnavailable as error:
                        route = "PENDIENTE_IA"
                        ai_reason = str(error)
                    except Exception:
                        route = "PENDIENTE_IA"
                        ai_reason = "La revisión IA no pudo completarse"

            ready_row_number: int | str = ""
            if route in {"LISTO_DETERMINISTA", "LISTO_IA_VERIFICADO"}:
                ready_rows.append([*macro_row, case_id])
                ready_row_number = len(ready_rows)
            else:
                review_rows.append({
                    "ID_CASO": case_id, "PDF_Archivo": entry.filename, "Estado": route,
                    "Campos faltantes": "; ".join(missing_fields),
                    "Incidencias de validacion": "; ".join(issues),
                    "Campos enviados a IA": "; ".join(requested_fields), "Motivo IA": ai_reason,
                    "Correcciones IA": json_cell(accepted),
                    "Evidencia IA": json_cell([
                        {"field": item["field"], "page": item["page"], "evidence": item["evidence"]}
                        for item in accepted
                    ]),
                    "Modelo IA": model_name, "Siguiente accion": next_action(route),
                })

            control = dict(deterministic)
            control.update({
                "ID_CASO": case_id, "Campos faltantes": "; ".join(missing_fields),
                "Incidencias de validacion": "; ".join(unique([*issues, *rejected])), "Ruta final": route,
                "Revision IA ejecutada": "SI" if review_executed else "NO", "Modelo IA": model_name,
                "Campos enviados a IA": "; ".join(requested_fields), "Motivo IA": ai_reason,
                "Correcciones IA": json_cell(accepted),
                "Evidencia IA": json_cell([
                    {"field": item["field"], "page": item["page"], "evidence": item["evidence"]}
                    for item in accepted
                ]),
                "Fila PARA_PROCESAR": ready_row_number,
            })
            control["Observacion extraccion"] = "; ".join(unique([
                str(deterministic.get("Observacion extraccion") or ""),
                *(f"Campo inicial faltante: {field}" for field in initial_missing), *initial_issues,
            ]))
            control_rows.append(control)
    return ready_rows, review_rows, control_rows


def _add_excel_table(worksheet, name: str) -> None:
    """Crea una tabla de Excel con nombre estable para Power Automate."""
    from openpyxl.utils import get_column_letter

    ref = f"A1:{get_column_letter(worksheet.max_column)}{worksheet.max_row}"
    table = Table(displayName=name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
        showRowStripes=True, showColumnStripes=False,
    )
    worksheet.add_table(table)


def _format_worksheet(worksheet) -> None:
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for column in worksheet.columns:
        values = ["" if cell.value is None else str(cell.value) for cell in column]
        width = min(max(max(map(len, values), default=10) + 2, 12), 42)
        worksheet.column_dimensions[column[0].column_letter].width = width


def build_workbook(
    ready_rows: list[list[Any]], review_rows: list[dict[str, Any]], control_rows: list[dict[str, Any]],
) -> io.BytesIO:
    """Genera las tres tablas que consume el flujo Microsoft."""
    output = io.BytesIO()
    ready_df = pd.DataFrame(ready_rows, columns=PARA_PROCESAR_COLUMNS)
    review_df = pd.DataFrame(review_rows).reindex(columns=REVIEW_COLUMNS)
    control_df = pd.DataFrame(control_rows).reindex(columns=CONTROL_COLUMNS)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        ready_df.to_excel(writer, sheet_name=PARA_PROCESAR_SHEET, index=False)
        review_df.to_excel(writer, sheet_name=REVISION_IA_SHEET, index=False)
        control_df.to_excel(writer, sheet_name=CONTROL_SHEET, index=False)
        table_names = {
            PARA_PROCESAR_SHEET: "tblParaProcesar", REVISION_IA_SHEET: "tblRevisionIa", CONTROL_SHEET: "tblControl",
        }
        for worksheet in writer.book.worksheets:
            _format_worksheet(worksheet)
            _add_excel_table(worksheet, table_names[worksheet.title])
    output.seek(0)
    return output


def json_error(message: str, status: int) -> Response:
    response = Response(json.dumps({"status": "error", "mensaje": message}, ensure_ascii=False), status=status, mimetype="application/json")
    response.headers.update(CORS_HEADERS)
    return response


@functions_framework.http
def procesar_tasaciones(request):
    if request.method == "OPTIONS":
        return "", 204, CORS_HEADERS
    if request.method != "POST":
        return json_error("Método no permitido", 405)
    try:
        ready_rows, review_rows, control_rows = process_zip(request.get_data(cache=False))
        response = Response(
            build_workbook(ready_rows, review_rows, control_rows).getvalue(), status=200,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response.headers["Content-Disposition"] = 'attachment; filename="Resultado_Final.xlsx"'
        response.headers.update(CORS_HEADERS)
        return response
    except ValueError as error:
        return json_error(str(error), 400)
    except Exception:
        return json_error("Error interno al procesar el lote de tasaciones", 500)
