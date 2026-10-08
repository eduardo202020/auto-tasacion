"""Regression checks for the Power Automate flow-definition generator."""

from pathlib import Path
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "deploy-mass-flows.ps1"
)
POLLING_GUIDE = (
    Path(__file__).resolve().parents[1] / "canvas" / "autoTasacionJG" / "POLLING.md"
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
        decoded_literal = (
            CONTROL_JSON_POWERSHELL_LITERAL.removeprefix("return '")
            .removesuffix("'")
            .replace("''", "'")
        )
        self.assertEqual(decoded_literal, CONTROL_JSON_EXPRESSION)

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


class ConsultarLoteDefinitionTests(unittest.TestCase):
    def setUp(self):
        script = SCRIPT.read_text(encoding="utf-8")
        start = script.index("'auto-tasacion-consultar-lote'")
        end = script.index("'auto-tasacion-cargar-lotes'", start)
        self.definition = script[start:end]

    def test_queries_the_batch_status_endpoint_with_the_power_apps_lot_id(self):
        self.assertIn(
            "@concat('$ServiceUrl/v1/lotes/', triggerBody()?['text'])",
            self.definition,
        )

    def test_returns_typed_safe_progress_fields_instead_of_serialized_json(self):
        fields = {
            "id_lote": "string",
            "estado": "string",
            "mensaje": "string",
            "total_pdfs": "integer",
            "pdfs_cargados": "integer",
            "pdfs_procesados": "integer",
            "pdfs_fallidos": "integer",
            "resultado_disponible": "boolean",
        }
        for field, field_type in fields.items():
            self.assertIn(
                f"{field} = \"@body('HTTP_Consultar_Lote')?['{field}']\"",
                self.definition,
            )
            self.assertIn(f"{field} = [ordered]@{{", self.definition)
            self.assertIn(f"type = '{field_type}'", self.definition)
        self.assertNotIn("estadojson", self.definition)

    def test_does_not_return_file_metadata_or_transfer_secrets_to_power_apps(self):
        for forbidden in ("archivos", "url_carga", "url_descarga", "objeto_gcs"):
            self.assertNotIn(forbidden, self.definition)


class CanvasPollingGuideTests(unittest.TestCase):
    def setUp(self):
        self.guide = POLLING_GUIDE.read_text(encoding="utf-8")

    def test_uses_the_typed_query_contract_and_ten_second_timer(self):
        self.assertIn("`Button5`", self.guide)
        self.assertIn("'auto-tasacion-iniciar-lote'.Run(", self.guide)
        self.assertIn("'auto-tasacion-consultar-lote'.Run(varIdLote)", self.guide)
        self.assertIn("| `Duration` | `10000` |", self.guide)
        self.assertNotIn("estadojson", self.guide)

    def test_stops_only_after_delivery_or_a_real_terminal_failure(self):
        self.assertIn('varEstadoLote = "ENTREGADO"', self.guide)
        self.assertIn('varEstadoLote = "FALLIDO"', self.guide)
        self.assertIn('varEstadoLote = "FALLIDO_ORIGEN_CAMBIO"', self.guide)
        self.assertIn("`COMPLETADO` no detiene\nel temporizador", self.guide)

    def test_keeps_the_lot_id_on_a_transient_query_error(self):
        self.assertIn("IfError(", self.guide)
        self.assertIn("varErrorConsultaReportado", self.guide)
        self.assertIn("Set(varIdLote; varLote.id_lote);;", self.guide)


if __name__ == "__main__":
    unittest.main()
