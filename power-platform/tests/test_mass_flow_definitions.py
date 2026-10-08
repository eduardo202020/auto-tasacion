"""Regression checks for the Power Automate flow-definition generator."""

from pathlib import Path
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "deploy-mass-flows.ps1"
)
CONTROL_JSON_EXPRESSION = (
    "@json(base64ToString(outputs('Obtener_control_lote')?['body']?['$content']))"
)
CONTROL_JSON_POWERSHELL_LITERAL = (
    "return '@json(base64ToString(outputs(''Obtener_control_lote'')?"
    "[''body'']?[''$content'']))'"
)


class ControlFileParseDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.script = SCRIPT.read_text(encoding="utf-8")

    def test_control_file_content_is_decoded_from_binary_base64(self):
        self.assertIn("function Get-ControlJsonContentExpression", self.script)
        self.assertIn(CONTROL_JSON_POWERSHELL_LITERAL, self.script)
        self.assertIn("base64ToString", CONTROL_JSON_EXPRESSION)
        self.assertIn("['$content']", CONTROL_JSON_EXPRESSION)

    def test_both_flows_use_the_control_file_decoder(self):
        self.assertEqual(
            self.script.count("content = Get-ControlJsonContentExpression"),
            2,
            "cargar-lotes and entregar-lote must decode the control file first",
        )
        self.assertNotIn(
            'content = "@body(\'Obtener_control_lote\')"',
            self.script,
        )

    def test_control_file_schema_remains_id_lote_only(self):
        self.assertGreaterEqual(self.script.count("required = @('id_lote')"), 2)


if __name__ == "__main__":
    unittest.main()
