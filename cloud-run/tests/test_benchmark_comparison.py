"""Focused tests for privacy-safe semantic golden address comparison."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

import fitz


TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from run_extraction_benchmark import address_group_status, address_match_status, _macro_fields_from_extracted
from address_parser import extract_interior
from pdf_extractor import VALOR_RECONSTRUCCION_RE, detect_pisos_sotanos_conflict


class AddressComparisonTests(unittest.TestCase):
    def test_exact_address_value_is_exact_match(self):
        self.assertEqual(address_match_status("CIRO ALEGRIA", "CIRO ALEGRIA"), "EXACT_MATCH")

    def test_catalog_abbreviation_and_case_are_semantic_match(self):
        self.assertEqual(address_match_status("Av. Ciro Alegria", "AVENIDA CIRO ALEGRÍA"), "SEMANTIC_MATCH")

    def test_different_number_is_not_semantically_equivalent(self):
        self.assertEqual(address_match_status("MANUEL PRADO 470", "MANUEL PRADO 471"), "DIFFERENT")

    def test_group_is_different_when_any_structured_field_differs(self):
        self.assertEqual(
            address_group_status({"direccion": "EXACT_MATCH", "exterior": "DIFFERENT"}),
            "DIFFERENT",
        )

    def test_review_case_keeps_address_candidate_for_golden_comparison(self):
        fields = _macro_fields_from_extracted({
            "Direccion extraida": "MZ D LOTE 40 URB. LOS JAZMINES, DISTRITO PIURA, PROVINCIA PIURA, DEPARTAMENTO PIURA",
            "Tipo inmueble": "CASA",
        })
        self.assertEqual(fields["DIRECCION"], "AVENIDA")
        self.assertEqual(fields["EXTERIOR"], "MZ D")
        self.assertEqual(fields["REFERENCIA"], "LT 40")
        self.assertEqual(fields["DIST_COD"], "011")

    def test_geographic_department_is_not_an_interior(self):
        self.assertEqual(
            extract_interior("Avenida Prueba 214, Distrito Ejemplo, Provincia Ejemplo, Departamento Lima"),
            "",
        )
        self.assertEqual(extract_interior("Avenida Prueba, Departamento N° 101"), "101")

    def test_reconstruction_anchor_does_not_match_a_cost_method_name(self):
        self.assertIsNone(VALOR_RECONSTRUCCION_RE.search("Metodo de Costos o Reposicion"))
        self.assertIsNotNone(VALOR_RECONSTRUCCION_RE.search("V. Reconstruccion"))

    def test_conflicting_first_construyo_floor_distribution_is_flagged(self):
        document = fitz.open()
        page = document.new_page()
        page.insert_text(
            (72, 72),
            "Primer construyo proyectada a 2 pisos y azotea. - 1 piso: sala. - 2 piso: dormitorios. - 3 piso: azotea.",
        )
        self.assertIn("Conflicto documental de pisos", detect_pisos_sotanos_conflict(document))
        document.close()
