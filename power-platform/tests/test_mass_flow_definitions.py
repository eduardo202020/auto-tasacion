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

    def test_all_control_consumers_use_the_control_file_decoder(self):
        self.assertEqual(
            self.script.count("content = Get-ControlJsonContentExpression"),
            3,
            "all control consumers must decode the binary OneDrive payload first",
        )
        self.assertNotIn(
            'content = "@body(\'Obtener_control_lote\')"',
            self.script,
        )

    def test_control_file_schema_remains_id_lote_only(self):
        self.assertGreaterEqual(self.script.count("required = @('id_lote')"), 3)


class FlowDeploymentLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.script = SCRIPT.read_text(encoding="utf-8")

    def test_active_unpublished_flow_is_drafted_before_definition_replacement(self):
        """Avoid a direct PATCH of clientdata against an ActiveUnpublished flow."""
        deactivate = "statecode = 0\n                statuscode = 1"
        update_definition = "clientdata = $clientdata"
        reactivate = "statecode = 1\n                statuscode = 2"
        publish = "Publish-WorkflowDraft -WorkflowId ([string] $existing.workflowid)"
        self.assertIn("function Publish-WorkflowDraft", self.script)
        self.assertIn("-Path 'PublishXml'", self.script)
        self.assertIn(publish, self.script)
        self.assertIn(deactivate, self.script)
        self.assertIn(reactivate, self.script)
        self.assertLess(
            self.script.index(publish),
            self.script.index(deactivate),
        )
        self.assertLess(
            self.script.index(deactivate),
            self.script.index(update_definition),
        )

    def test_can_deploy_one_named_flow_without_touching_the_others(self):
        self.assertIn("[string[]] $FlowName", self.script)
        self.assertIn("if ($FlowName)", self.script)
        self.assertIn("$unknownFlowNames", self.script)
        self.assertIn("$selectedFlows[$name] = $flows[$name]", self.script)


class ConsultarLoteDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.script = SCRIPT.read_text(encoding="utf-8")
        start = self.script.index("'auto-tasacion-consultar-lote'")
        end = self.script.index("'auto-tasacion-orquestar-lote'", start)
        self.definition = self.script[start:end]

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
            "fecha_inicio": "string",
            "fecha_fin": "string",
            "duracion_segundos": "integer",
        }
        for field, field_type in fields.items():
            self.assertIn(
                f"{field} = \"@body('HTTP_Consultar_Lote')?['{field}']\"",
                self.definition,
            )
            self.assertIn(f"{field} = [ordered]@{{", self.definition)
            self.assertIn(f"type = '{field_type}'", self.definition)
        self.assertNotIn("estadojson", self.definition)

    def test_start_flow_returns_the_persisted_start_timestamp(self):
        start = self.script.index("'auto-tasacion-iniciar-lote'")
        end = self.script.index("'auto-tasacion-consultar-lote'", start)
        definition = self.script[start:end]
        self.assertIn(
            'fecha_inicio = "@{body(\'HTTP_Registrar_Lote\')?[\'fecha_inicio\']}"',
            definition,
        )
        self.assertIn("fecha_inicio = [ordered]@{", definition)

    def test_does_not_return_file_metadata_or_transfer_secrets_to_power_apps(self):
        for forbidden in ("archivos", "url_carga", "url_descarga", "objeto_gcs"):
            self.assertNotIn(forbidden, self.definition)


class EventOrchestratorDefinitionTests(unittest.TestCase):
    def setUp(self):
        script = SCRIPT.read_text(encoding="utf-8")
        start = script.index("'auto-tasacion-orquestar-lote'")
        end = script.index("'auto-tasacion-cargar-lotes'", start)
        self.definition = script[start:end]
        self.script = script

    def test_uses_the_properties_only_created_file_trigger_in_the_control_folder(self):
        self.assertIn("function New-OneDriveControlCreatedTrigger", self.script)
        self.assertIn("operationId = 'OnNewFilesV2'", self.script)
        self.assertIn("folderId = $FolderId", self.script)
        self.assertIn("splitOn = \"@triggerOutputs()?['body/value']\"", self.script)
        self.assertIn("$ControlFolder = '/auto-tasaciones/Controles'", self.script)
        self.assertIn("folderPath = $ControlFolder", self.script)

    def test_targets_only_the_triggered_control_and_does_not_scan_all_batches(self):
        self.assertIn("path = \"@triggerBody()?['Path']\"", self.definition)
        self.assertIn("id = \"@triggerBody()?['Id']\"", self.definition)
        self.assertNotIn("ListFolderV2", self.definition)
        self.assertNotIn("Por_cada_control", self.definition)
        self.assertNotIn("New-RecurrenceTrigger", self.definition)

    def test_claim_is_acquired_and_renewed_before_transfer_job_and_delivery(self):
        for suffix in ("/orquestacion/reclamar", "/orquestacion/renovar"):
            self.assertIn(suffix, self.definition)
        self.assertIn("@equals(body('Reclamar_orquestacion')?['reclamado'], true)", self.definition)
        self.assertIn("Renovar_claim_antes_de_archivo", self.definition)
        self.assertIn("Renovar_claim_antes_de_iniciar_job", self.definition)
        self.assertIn("Renovar_claim_antes_de_entrega", self.definition)
        self.assertIn("@workflow()?['run']?['name']", self.definition)

    def test_serial_uploads_wait_with_bounded_backoff_and_deliver_in_order(self):
        self.assertIn("repetitions = 1", self.definition)
        self.assertIn("type = 'Until'", self.definition)
        self.assertIn("timeout = 'PT2H'", self.definition)
        self.assertIn("Esperar_con_backoff", self.definition)
        self.assertIn("Aumentar_espera_hasta_cinco_minutos", self.definition)
        self.assertIn("/orquestacion/liberar", self.definition)
        self.assertLess(self.definition.index("HTTP_Iniciar_Job"), self.definition.index("Esperar_resultado_del_lote"))
        self.assertLess(self.definition.index("Buscar_excel_final_existente"), self.definition.index("Excel_final_ya_existe"))
        self.assertLess(self.definition.index("Solicitar_ticket_resultado"), self.definition.index("Crear_excel_final"))
        self.assertLess(self.definition.index("Crear_excel_final"), self.definition.index("Confirmar_entrega_nuevo"))
        self.assertLess(self.definition.index("Confirmar_entrega_nuevo"), self.definition.index("Eliminar_control_lote_nuevo"))

    def test_backoff_update_does_not_self_reference_the_target_variable(self):
        start = self.definition.index("Aumentar_espera_hasta_cinco_minutos")
        end = self.definition.index("Lote_alcanzo_estado_terminal", start)
        backoff_update = self.definition[start:end]
        self.assertIn("variables('intentos_espera')", backoff_update)
        self.assertNotIn("variables('espera_segundos')", backoff_update)

    def test_recovery_after_creating_the_xlsx_confirms_the_existing_artifact(self):
        self.assertIn("OperationId 'FindFilesByPath'", self.definition)
        self.assertIn("findMode = 'Pattern'", self.definition)
        self.assertNotIn("findMode = 'RegularExpressionPatternMatch'", self.definition)
        self.assertIn("@greater(length(body('Buscar_excel_final_existente')), 0)", self.definition)
        self.assertIn("Confirmar_entrega_existente", self.definition)
        self.assertIn("Eliminar_control_lote_existente", self.definition)
        self.assertEqual(self.definition.count("Crear_excel_final = New-OneDriveAction"), 1)

    def test_duplicate_event_cleans_only_a_delivered_control_left_by_a_crash(self):
        self.assertIn("Limpiar_control_de_lote_entregado", self.definition)
        self.assertIn("@equals(body('Reclamar_orquestacion')?['estado'], 'ENTREGADO')", self.definition)
        self.assertIn("Eliminar_control_lote_entregado", self.definition)

    def test_initializes_polling_variables_before_entering_conditional_scopes(self):
        self.assertLess(self.definition.index("Inicializar_estado_lote"), self.definition.index("Es_control_de_lote"))
        self.assertIn("Asignar_estado_lote_inicial", self.definition)
        self.assertIn("Reiniciar_espera_segundos", self.definition)

    def test_retries_skip_a_second_put_when_the_api_reuses_a_verified_upload(self):
        self.assertIn("Carga_PDF_requerida", self.definition)
        self.assertIn("@equals(body('Solicitar_ticket_de_carga')?['requiere_carga'], true)", self.definition)
        self.assertIn("Metadatos_finales", self.definition)
        self.assertLess(self.definition.index("Carga_PDF_requerida"), self.definition.index("Metadatos_finales"))


class DeliveryFlowDefinitionTests(unittest.TestCase):
    def setUp(self):
        script = SCRIPT.read_text(encoding="utf-8")
        start = script.index("'auto-tasacion-entregar-lote'")
        end = script.index("default { throw", start)
        self.definition = script[start:end]

    def test_enters_delivery_only_for_a_completed_available_result(self):
        condition = (
            "@and(equals(body('HTTP_Consultar_Lote')?['estado'], 'COMPLETADO'), "
            "equals(body('HTTP_Consultar_Lote')?['resultado_disponible'], true))"
        )
        self.assertIn(condition, self.definition)
        self.assertLess(
            self.definition.index("Solicitar_ticket_resultado"),
            self.definition.index("Crear_excel_final"),
        )
        self.assertLess(
            self.definition.index("Crear_excel_final"),
            self.definition.index("Confirmar_entrega"),
        )

    def test_uses_the_id_from_each_control_file_for_its_backend_request(self):
        request = (
            "@concat('$ServiceUrl/v1/lotes/', "
            "body('Leer_control_lote')?['id_lote'])"
        )
        self.assertIn(request, self.definition)


class CanvasPollingGuideTests(unittest.TestCase):
    def setUp(self):
        self.guide = POLLING_GUIDE.read_text(encoding="utf-8")

    def test_uses_the_typed_query_contract_and_ten_second_timer(self):
        self.assertIn("`Button5.OnSelect`", self.guide)
        self.assertIn("'auto-tasacion-iniciar-lote'.Run(", self.guide)
        self.assertIn("'auto-tasacion-consultar-lote'.Run(varIdLote)", self.guide)
        self.assertIn("`Duration = 10000`", self.guide)
        for field in ("fecha_inicio", "fecha_fin", "duracion_segundos"):
            self.assertIn(field, self.guide)
        self.assertNotIn("estadojson", self.guide)

    def test_stops_only_after_delivery_or_a_real_terminal_failure(self):
        self.assertIn('varEstadoLote = "ENTREGADO"', self.guide)
        self.assertIn('varEstadoLote = "FALLIDO"', self.guide)
        self.assertIn('varEstadoLote = "FALLIDO_ORIGEN_CAMBIO"', self.guide)
        self.assertIn("`COMPLETADO` no detiene el polling", self.guide)

    def test_keeps_the_lot_id_on_a_transient_query_error(self):
        self.assertIn("IfError(", self.guide)
        self.assertIn("varErrorConsultaReportado", self.guide)
        self.assertIn("Conserva el último estado ante", self.guide)
        self.assertIn("Set(varMonitorearLote; false)", self.guide)
        self.assertIn("`btnReanudarLote`", self.guide)
        self.assertIn("Set(varIdLote; Trim(txtIdLote.Text));;", self.guide)

    def test_resets_all_previous_tracking_state_before_starting_a_new_batch(self):
        button_start = self.guide.index("## Boton **Ejecutar**")
        timer_start = self.guide.index("## Timer de polling", button_start)
        button_formula = self.guide[button_start:timer_start]
        start_flow = button_formula.index("'auto-tasacion-iniciar-lote'.Run(")
        for reset in (
            "Set(varMonitorearLote; false);;",
            "Set(varIdLote; Blank());;",
            "Set(varConsultaLote; Blank());;",
            "Set(varConsultaIntento; Blank());;",
            "Set(varEstadoLote; Blank());;",
            "Set(varResultadoDisponible; false);;",
            "Set(varFechaFinProceso; Blank());;",
            "Set(varFinProceso; Blank());;",
            "Set(varPasoActivo; 0);;",
            "Set(varPasoError; Blank());;",
        ):
            self.assertIn(reset, button_formula)
            self.assertLess(button_formula.index(reset), start_flow)

    def test_documents_a_visual_only_timer_and_all_step_states(self):
        self.assertIn("`tmrVistaLote`", self.guide)
        self.assertIn("`Duration` | `750`", self.guide)
        self.assertIn("Set(varBlinkPasoActivo; !varBlinkPasoActivo)", self.guide)
        for state in (
            "RECIBIDO",
            "CARGANDO_PDFS",
            "LISTO_PARA_PROCESAR",
            "EN_PROCESO",
            "COMPLETADO",
            "ENTREGADO",
            "FALLIDO",
            "FALLIDO_ORIGEN_CAMBIO",
        ):
            self.assertIn(f'"{state}"', self.guide)


if __name__ == "__main__":
    unittest.main()
