import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud-run"))
sys.path.insert(0, str(ROOT))

from service import MACRO_COLUMNS, build_workbook
from tools.verify_workbook import validate


class WorkbookContractValidatorTests(unittest.TestCase):
    def complete_row(self) -> list[object]:
        values = {
            "TIPO DE INMUEBLE": "DEPARTAMENTO",
            "VALOR DEL BIEN": "",
            "MONEDA": "PEN",
            "IMPORTE": "475,000.00",
            "DIRECCION": "AV.",
            "DIRECCION1": "PRUEBA",
            "MUNICIPIO": "WANCHAQ",
            "DIST_COD": "008",
            "PROV_COD": "01",
            "DEPT_COD": "08",
            "CLASE": "2",
            "PISOS": 7,
            "SOTANOS": 2,
            "AÑO": 2018,
        }
        return [values.get(column, "") for column in MACRO_COLUMNS]

    def test_accepts_a_workbook_emitted_by_the_service(self):
        workbook = build_workbook(
            [[*self.complete_row(), "TAS-TEST"]],
            [],
            [{"ID_CASO": "TAS-TEST", "PDF_Archivo": "D01.pdf", "Ruta final": "LISTO_DETERMINISTA"}],
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "Resultado_Final.xlsx"
            output.write_bytes(workbook.getvalue())
            self.assertEqual(validate(output), [])

    def test_rejects_non_xlsx_input(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "no-es-excel.xlsx"
            output.write_bytes(b"no es un archivo OOXML")
            self.assertTrue(validate(output))


if __name__ == "__main__":
    unittest.main()
