import io
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import fitz
from flask import Flask, request
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog import (
    lookup_class_code,
    lookup_currency_code,
    lookup_direction_code,
    lookup_location,
    lookup_property_codes,
)
from pdf_extractor import extract_pdf
from service import MACRO_COLUMNS, PARA_PROCESAR_COLUMNS, build_workbook, procesar_tasaciones, process_zip


def build_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        """Dirección: Avenida Prueba 123, Miraflores, Lima
Tipo de inmueble: Departamento
Valor Comercial
US$ 125,000.00
S/ 475,000.00
Año de construcción: 2018
El edificio consta de 7 pisos y 3 sótanos.
Nro de pisos: 8
Nro de sótanos: 2
Préstamo: 12345678901234567890""",
        fontsize=10,
    )
    content = document.tobytes()
    document.close()
    return content


def build_pdf_with_effective_age() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Edad Efectiva (años)", fontsize=10)
    page.insert_text((72, 88), "12", fontsize=10)
    page.insert_text((72, 110), "Fecha de Expedición 15/08/2025", fontsize=10)
    content = document.tobytes()
    document.close()
    return content


def build_pdf_with_year_in_adjacent_cell() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Año de construcción", fontsize=10)
    page.insert_text((230, 72), "2025", fontsize=10)
    content = document.tobytes()
    document.close()
    return content


def build_zip(name: str = "D01.pdf", content: bytes | None = None) -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(name, content or build_pdf())
    return archive.getvalue()


def complete_row(extracted: dict) -> tuple[list, list[str]]:
    """Aísla el enrutamiento de las variaciones del parser de direcciones."""
    row = [""] * len(MACRO_COLUMNS)
    values = {
        "TIPO DE INMUEBLE": "C", "VALOR DEL BIEN": 125000.0, "MONEDA": "USD", "IMPORTE": 125000.0,
        "DIRECCION": "AV.", "DIRECCION1": "PRUEBA", "MUNICIPIO": "WANCHAQ", "DIST_COD": "008",
        "PROV_COD": "01", "DEPT_COD": "08", "CLASE": "2", "PISOS": 7, "SOTANOS": 2,
        "AÑO": extracted.get("Año construccion", ""),
    }
    for field, value in values.items():
        row[MACRO_COLUMNS.index(field)] = value
    return row, []


class FakeReviewer:
    model_name = "gemini-prueba"

    def review(self, _pdf, **_kwargs):
        return {
            "decision": "RESUELTO",
            "reason": "Año identificado en el PDF",
            "corrections": [{
                "field": "Año construccion", "value": "2018", "page": 1,
                "evidence": "Año de construcción: 2018", "rule": "Año explícito",
            }],
        }


class UnsafeReviewer:
    model_name = "gemini-prueba"

    def review(self, _pdf, **_kwargs):
        return {
            "decision": "RESUELTO",
            "reason": "Sin fuente comprobable",
            "corrections": [{"field": "Año construccion", "value": "2018", "page": 1, "evidence": ""}],
        }


class NeverCalledReviewer:
    model_name = "gemini-prueba"

    def review(self, *_args, **_kwargs):
        raise AssertionError("Un conflicto sin regla aprobada no debe enviarse a IA")


class TasacionesServiceTests(unittest.TestCase):
    def test_extracts_core_fields_and_detects_floor_conflict(self):
        result = extract_pdf(build_pdf(), "D01.pdf")
        self.assertEqual(result["PRESTAMO"], "12345678901234567890")
        self.assertEqual(result["Tipo inmueble"], "DEPARTAMENTO")
        self.assertEqual(result["Valor elegido US$"], 125000.0)
        self.assertEqual(result["Año construccion"], 2018)
        self.assertEqual(result["Nro pisos edificio"], 7)
        self.assertIn("Conflicto pisos/sótanos", result["Observacion extraccion"])

    def test_derives_construction_year_from_effective_age(self):
        result = extract_pdf(build_pdf_with_effective_age(), "D02.pdf")
        self.assertEqual(result["Edad efectiva"], 12)
        self.assertEqual(result["Año expedicion"], 2025)
        self.assertEqual(result["Año construccion"], 2013)
        self.assertEqual(result["Origen año construccion"], "EDAD EFECTIVA")

    def test_extracts_construction_year_from_adjacent_pdf_cell(self):
        result = extract_pdf(build_pdf_with_year_in_adjacent_cell(), "D02.pdf")
        self.assertEqual(result["Año construccion"], 2025)
        self.assertEqual(result["Origen año construccion"], "AÑO DE CONSTRUCCIÓN")

    def test_uses_only_codes_defined_in_datos_catalog(self):
        self.assertEqual(lookup_property_codes("DEPARTAMENTO"), {
            "tipo_inmueble": "D", "masivo": "C", "valor_del_bien": "C",
        })
        self.assertEqual(lookup_property_codes("CASA"), {
            "tipo_inmueble": "C", "masivo": "N", "valor_del_bien": "N",
        })
        self.assertEqual(lookup_currency_code("USD"), "USD")
        self.assertEqual(lookup_currency_code("PEN"), "PEN")
        self.assertEqual(lookup_direction_code("AVENIDA"), "AV.")
        self.assertEqual(lookup_location("CUSCO", "CUSCO", "WANCHAQ")["DISTRITO_COD"], "008")
        self.assertEqual(lookup_class_code(4), "1")
        self.assertEqual(lookup_class_code(5), "2")
        self.assertEqual(lookup_class_code(11), "3")

    def test_routes_unresolved_case_to_revision_ia_and_preserves_control(self):
        ready_rows, review_rows, control_rows = process_zip(
            build_zip(content=build_pdf_with_effective_age()), use_environment_reviewer=False,
        )
        self.assertEqual(ready_rows, [])
        self.assertEqual(len(review_rows), 1)
        self.assertEqual(review_rows[0]["Estado"], "PENDIENTE_IA")
        self.assertTrue(review_rows[0]["ID_CASO"].startswith("TAS-"))
        self.assertEqual(len(control_rows), 1)
        self.assertEqual(control_rows[0]["Ruta final"], "PENDIENTE_IA")
        self.assertEqual(control_rows[0]["Revision IA ejecutada"], "NO")

    def test_ia_result_is_revalidated_before_entering_para_procesar(self):
        extracted = {
            "ID / Codigo PDF": "D99", "PDF_Archivo": "D99.pdf", "Año construccion": "",
            "Observacion extraccion": "Año de construcción y edad efectiva no encontrados",
        }
        with patch("service.extract_pdf", return_value=extracted), patch("service.to_macro_row", side_effect=complete_row):
            ready_rows, review_rows, control_rows = process_zip(build_zip("D99.pdf"), reviewer=FakeReviewer())
        self.assertEqual(len(ready_rows), 1)
        self.assertEqual(ready_rows[0][PARA_PROCESAR_COLUMNS.index("AÑO")], 2018)
        self.assertTrue(ready_rows[0][PARA_PROCESAR_COLUMNS.index("ID_CASO")].startswith("TAS-"))
        self.assertEqual(review_rows, [])
        self.assertEqual(control_rows[0]["Ruta final"], "LISTO_IA_VERIFICADO")
        self.assertEqual(control_rows[0]["Revision IA ejecutada"], "SI")
        self.assertIn("Año construccion", control_rows[0]["Correcciones IA"])

    def test_ia_correction_without_evidence_never_enters_para_procesar(self):
        extracted = {
            "ID / Codigo PDF": "D98", "PDF_Archivo": "D98.pdf", "Año construccion": "",
            "Observacion extraccion": "Año de construcción y edad efectiva no encontrados",
        }
        with patch("service.extract_pdf", return_value=extracted), patch("service.to_macro_row", side_effect=complete_row):
            ready_rows, review_rows, control_rows = process_zip(build_zip("D98.pdf"), reviewer=UnsafeReviewer())
        self.assertEqual(ready_rows, [])
        self.assertEqual(review_rows[0]["Estado"], "REVISION_HUMANA")
        self.assertIn("evidencia de página válida", control_rows[0]["Incidencias de validacion"])

    def test_conflict_without_approved_rule_never_reaches_ai_or_para_procesar(self):
        extracted = {
            "ID / Codigo PDF": "D97", "PDF_Archivo": "D97.pdf", "Año construccion": 2018,
            "Observacion extraccion": "Conflicto pisos/sótanos entre descripción y tabla del PDF",
        }
        with patch("service.extract_pdf", return_value=extracted), patch("service.to_macro_row", side_effect=complete_row):
            ready_rows, review_rows, control_rows = process_zip(build_zip("D97.pdf"), reviewer=NeverCalledReviewer())
        self.assertEqual(ready_rows, [])
        self.assertEqual(review_rows[0]["Estado"], "REGLA_NEGOCIO_PENDIENTE")
        self.assertEqual(control_rows[0]["Revision IA ejecutada"], "NO")

    def test_builds_three_named_tables_for_power_automate(self):
        row, _ = complete_row({"Año construccion": 2018})
        control = {"ID_CASO": "TAS-TEST", "PDF_Archivo": "D01.pdf", "Ruta final": "LISTO_DETERMINISTA"}
        workbook = load_workbook(io.BytesIO(build_workbook([[*row, "TAS-TEST"]], [], [control]).read()), data_only=True)
        self.assertEqual(workbook.sheetnames, ["PARA_PROCESAR", "REVISION_IA", "CONTROL"])
        self.assertEqual(workbook["PARA_PROCESAR"]["B2"].value, "C")
        self.assertIn("tblParaProcesar", workbook["PARA_PROCESAR"].tables)
        self.assertIn("tblRevisionIa", workbook["REVISION_IA"].tables)
        self.assertIn("tblControl", workbook["CONTROL"].tables)

    def test_endpoint_accepts_raw_zip_and_returns_xlsx(self):
        app = Flask(__name__)
        with app.test_request_context("/", method="POST", data=build_zip(), content_type="application/zip"):
            response = procesar_tasaciones(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("Resultado_Final.xlsx", response.headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
