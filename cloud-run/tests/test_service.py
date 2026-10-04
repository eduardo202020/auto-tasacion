import io
import sys
import unittest
import zipfile
from pathlib import Path

import fitz
from flask import Flask, request
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdf_extractor import extract_pdf
from service import build_workbook, procesar_tasaciones, process_zip


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
Nro de pisos: 8
Nro de sótanos: 2
Préstamo: 12345678901234567890""",
        fontsize=10,
    )
    content = document.tobytes()
    document.close()
    return content


class TasacionesServiceTests(unittest.TestCase):
    def test_extracts_core_fields_from_pdf(self):
        result = extract_pdf(build_pdf(), "D01.pdf")
        self.assertEqual(result["PRESTAMO"], "12345678901234567890")
        self.assertEqual(result["Tipo inmueble"], "DEPARTAMENTO")
        self.assertEqual(result["Valor elegido US$"], 125000.0)
        self.assertEqual(result["Valor elegido S/"], 475000.0)
        self.assertEqual(result["Año construccion"], 2018)
        self.assertEqual(result["Nro pisos edificio"], 8)
        self.assertEqual(result["Nro sotanos edificio"], 2)

    def test_creates_macro_and_control_sheets(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr("D01.pdf", build_pdf())
        macro_rows, control_rows = process_zip(archive.getvalue())
        self.assertEqual(macro_rows[0][0], "12345678901234567890")
        self.assertEqual(macro_rows[0][1], "C")
        self.assertEqual(macro_rows[0][2], 125000.0)
        self.assertEqual(macro_rows[0][3], "USD")
        self.assertEqual(macro_rows[0][21], 8)
        self.assertEqual(macro_rows[0][22], 2)
        self.assertEqual(macro_rows[0][23], 2018)
        workbook = load_workbook(io.BytesIO(build_workbook(macro_rows, control_rows).read()), data_only=True)
        self.assertEqual(workbook.sheetnames, ["MASIVO", "CONTROL_EXTRACCION"])
        self.assertEqual(workbook["MASIVO"]["A2"].value, "12345678901234567890")

    def test_endpoint_accepts_raw_zip_and_returns_xlsx(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr("D01.pdf", build_pdf())
        app = Flask(__name__)
        with app.test_request_context(
            "/",
            method="POST",
            data=archive.getvalue(),
            content_type="application/zip",
        ):
            response = procesar_tasaciones(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.mimetype,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("Resultado_Final.xlsx", response.headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
