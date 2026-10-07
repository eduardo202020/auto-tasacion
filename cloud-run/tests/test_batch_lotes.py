import io
import os
import sys
import unittest
from pathlib import Path

import fitz
from flask import Flask, request
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from batch_api import BatchControlApi, handle_request
from batch_lotes import (
    BATCH_COMPLETED,
    BATCH_FAILED,
    BATCH_PROCESSING,
    BATCH_READY,
    BATCH_SOURCE_CHANGED,
    FILE_UPLOADED,
    MAX_BATCH_TOTAL_BYTES,
    MAX_PDF_BYTES,
    BatchError,
    InMemoryBatchStore,
    build_manifest,
    manifest_idempotency_key,
    update_manifest,
)
from batch_worker import process_batch_gcs
from service import CONTROL_COLUMNS, PARA_PROCESAR_COLUMNS, REVIEW_COLUMNS, process_pdf_entries


class FakeBlob:
    def __init__(self, name):
        self.name = name
        self.data = None
        self.size = None
        self.content_type = None

    def exists(self):
        return self.data is not None

    def reload(self):
        if self.data is not None:
            self.size = len(self.data)

    def download_as_bytes(self):
        return self.data

    def upload_from_file(self, source, rewind=False, content_type=None, **_kwargs):
        if rewind:
            source.seek(0)
        self.data = source.read()
        self.size = len(self.data)
        self.content_type = content_type


class FakeBucket:
    def __init__(self):
        self.blobs = {}

    def blob(self, name):
        if name not in self.blobs:
            self.blobs[name] = FakeBlob(name)
        return self.blobs[name]


class FakeStorageClient:
    def __init__(self):
        self.buckets = {}

    def bucket(self, name):
        if name not in self.buckets:
            self.buckets[name] = FakeBucket()
        return self.buckets[name]


def make_pdf(text="Tasación sintética"):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=10)
    content = document.tobytes()
    document.close()
    return content


def file_item(index, *, etag=None, size=1024, name=None):
    return {
        "item_id": f"onedrive-item-{index}",
        "nombre": name or f"tasacion-{index}.pdf",
        "etag": etag or f"etag-{index}",
        "tamano_bytes": size,
    }


def payload(files):
    return {"carpeta_origen": "/auto-tasaciones", "archivos": files}


class BatchManifestTests(unittest.TestCase):
    def test_allows_three_hundred_pdfs_and_rejects_three_hundred_one(self):
        manifest = build_manifest(payload([file_item(index) for index in range(300)]))
        self.assertEqual(manifest["total_pdfs"], 300)
        self.assertEqual(manifest["estado"], "RECIBIDO")
        with self.assertRaisesRegex(BatchError, "máximo de 300"):
            build_manifest(payload([file_item(index) for index in range(301)]))

    def test_rejects_total_over_two_gibibytes(self):
        files = [file_item(1, size=MAX_BATCH_TOTAL_BYTES), file_item(2, size=1)]
        with self.assertRaisesRegex(BatchError, "tamaño total"):
            build_manifest(payload(files))

    def test_individual_pdf_over_limit_is_recorded_as_failed_without_ticket(self):
        manifest = build_manifest(payload([file_item(1, size=MAX_PDF_BYTES + 1)]))
        self.assertEqual(manifest["estado"], BATCH_FAILED)
        self.assertEqual(manifest["archivos"][0]["estado"], BATCH_FAILED)
        self.assertIn("individual", manifest["mensaje"])

    def test_rejects_non_pdf_manifest_entry(self):
        with self.assertRaisesRegex(BatchError, "PDF"):
            build_manifest(payload([file_item(1, name="tasacion.exe")]))

    def test_idempotency_is_order_independent_and_etag_sensitive(self):
        first = build_manifest(payload([file_item(1), file_item(2)]))
        reordered = build_manifest(payload([file_item(2), file_item(1)]))
        changed = build_manifest(payload([file_item(1, etag="etag-nuevo"), file_item(2)]))
        self.assertEqual(first["clave_idempotencia"], reordered["clave_idempotencia"])
        self.assertEqual(first["id_lote"], reordered["id_lote"])
        self.assertNotEqual(first["clave_idempotencia"], changed["clave_idempotencia"])
        self.assertNotIn("drive_id", first)


class BatchControlApiTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryBatchStore()
        self.storage = FakeStorageClient()
        self.api = BatchControlApi(
            self.store,
            upload_bucket="tasaciones-prueba",
            storage_client=self.storage,
            signed_url_factory=lambda name: f"https://signed.invalid/{name}",
            job_launcher=lambda _manifest: "operations/prueba",
        )

    def _create_one_file_batch(self):
        content = make_pdf()
        manifest, created = self.api.create_batch(payload([file_item(1, size=len(content))]))
        self.assertTrue(created)
        return manifest, content

    def test_identical_manifest_reuses_same_batch(self):
        first, created = self.api.create_batch(payload([file_item(1)]))
        second, second_created = self.api.create_batch(payload([file_item(1)]))
        self.assertTrue(created)
        self.assertFalse(second_created)
        self.assertEqual(first["id_lote"], second["id_lote"])

    def test_does_not_start_partial_batch(self):
        manifest, _ = self._create_one_file_batch()
        with self.assertRaisesRegex(BatchError, "todos los PDFs confirmados"):
            self.api.start_batch(manifest["id_lote"])

    def test_upload_ticket_and_confirmation_moves_batch_to_ready(self):
        manifest, content = self._create_one_file_batch()
        item = manifest["archivos"][0]
        ticket = self.api.upload_ticket(manifest["id_lote"], item["id_archivo"])
        self.assertEqual(ticket["encabezados_carga"], {"Content-Type": "application/pdf"})
        self.assertNotIn("objeto", ticket)
        blob = self.storage.bucket("tasaciones-prueba").blob(item["objeto_gcs"])
        blob.data = content
        blob.content_type = "application/pdf"
        status = self.api.confirm_upload(manifest["id_lote"], item["id_archivo"], {"etag_confirmado": item["etag"]})
        self.assertEqual(status["estado"], BATCH_READY)
        self.assertEqual(status["pdfs_cargados"], 1)
        started = self.api.start_batch(manifest["id_lote"])
        self.assertEqual(started["estado"], BATCH_PROCESSING)

    def test_http_api_registers_and_reads_batch_status(self):
        app = Flask(__name__)
        with app.test_request_context("/v1/lotes", method="POST", json=payload([file_item(1)])):
            response = handle_request(request, self.api)
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertTrue(body["id_lote"].startswith("TAS-"))
        with app.test_request_context(f"/v1/lotes/{body['id_lote']}", method="GET"):
            response = handle_request(request, self.api)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["estado"], "RECIBIDO")

    def test_http_api_records_and_rejects_oversized_pdf(self):
        app = Flask(__name__)
        with app.test_request_context(
            "/v1/lotes", method="POST",
            json=payload([file_item(8, size=MAX_PDF_BYTES + 1)]),
        ):
            response = handle_request(request, self.api)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()["estado"], BATCH_FAILED)

    def test_http_api_rejects_invalid_json_body(self):
        app = Flask(__name__)
        with app.test_request_context("/v1/lotes", method="POST", data="{", content_type="application/json"):
            response = handle_request(request, self.api)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["codigo"], "MANIFIESTO_INVALIDO")

    def test_http_api_requires_configured_control_token(self):
        app = Flask(__name__)
        previous = os.environ.get("BATCH_CONTROL_API_TOKEN")
        os.environ["BATCH_CONTROL_API_TOKEN"] = "secreto-sintetico"
        try:
            with app.test_request_context("/v1/lotes", method="POST", json=payload([file_item(9)])):
                denied = handle_request(request, self.api, require_authentication=True)
            self.assertEqual(denied.status_code, 401)
            with app.test_request_context(
                "/v1/lotes", method="POST", json=payload([file_item(9)]),
                headers={"X-Batch-Control-Token": "secreto-sintetico"},
            ):
                accepted = handle_request(request, self.api, require_authentication=True)
            self.assertEqual(accepted.status_code, 201)
        finally:
            if previous is None:
                os.environ.pop("BATCH_CONTROL_API_TOKEN", None)
            else:
                os.environ["BATCH_CONTROL_API_TOKEN"] = previous

    def test_missing_gcs_object_marks_batch_failed(self):
        manifest, _ = self._create_one_file_batch()
        item = manifest["archivos"][0]
        self.api.upload_ticket(manifest["id_lote"], item["id_archivo"])
        with self.assertRaisesRegex(BatchError, "no existe"):
            self.api.confirm_upload(manifest["id_lote"], item["id_archivo"], {"etag_confirmado": item["etag"]})
        self.assertEqual(self.store.get(manifest["id_lote"])["estado"], BATCH_FAILED)

    def test_changed_etag_marks_batch_as_source_changed(self):
        manifest, _ = self._create_one_file_batch()
        item = manifest["archivos"][0]
        self.api.upload_ticket(manifest["id_lote"], item["id_archivo"])
        with self.assertRaisesRegex(BatchError, "cambió"):
            self.api.confirm_upload(manifest["id_lote"], item["id_archivo"], {"etag_confirmado": "etag-diferente"})
        saved = self.store.get(manifest["id_lote"])
        self.assertEqual(saved["estado"], BATCH_SOURCE_CHANGED)
        self.assertEqual(saved["archivos"][0]["estado"], BATCH_SOURCE_CHANGED)

    def test_wrong_gcs_size_marks_batch_failed(self):
        manifest, _ = self._create_one_file_batch()
        item = manifest["archivos"][0]
        self.api.upload_ticket(manifest["id_lote"], item["id_archivo"])
        blob = self.storage.bucket("tasaciones-prueba").blob(item["objeto_gcs"])
        blob.data = b"%PDF-incompleto"
        blob.content_type = "application/pdf"
        with self.assertRaisesRegex(BatchError, "tamaño"):
            self.api.confirm_upload(manifest["id_lote"], item["id_archivo"], {"etag_confirmado": item["etag"]})
        self.assertEqual(self.store.get(manifest["id_lote"])["estado"], BATCH_FAILED)


class BatchWorkerTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryBatchStore()
        self.storage = FakeStorageClient()
        self.api = BatchControlApi(
            self.store,
            upload_bucket="tasaciones-prueba",
            storage_client=self.storage,
            signed_url_factory=lambda _name: "https://signed.invalid/upload",
            job_launcher=lambda _manifest: "operations/prueba",
        )

    def _confirmed_batch(self):
        first_pdf = make_pdf("PDF sintético uno")
        second_pdf = make_pdf("PDF sintético dos")
        manifest, _ = self.api.create_batch(payload([
            file_item(1, size=len(first_pdf)), file_item(2, size=len(second_pdf)),
        ]))
        bucket = self.storage.bucket("tasaciones-prueba")
        for item, content in zip(manifest["archivos"], (first_pdf, second_pdf)):
            self.api.upload_ticket(manifest["id_lote"], item["id_archivo"])
            blob = bucket.blob(item["objeto_gcs"])
            blob.data = content
            blob.content_type = "application/pdf"
            self.api.confirm_upload(manifest["id_lote"], item["id_archivo"], {"etag_confirmado": item["etag"]})
        self.api.start_batch(manifest["id_lote"])
        return self.store.get(manifest["id_lote"])

    def test_worker_processes_confirmed_pdfs_one_by_one_and_preserves_workbook_contract(self):
        manifest = self._confirmed_batch()
        summary = process_batch_gcs(
            manifest["id_lote"],
            store=self.store,
            storage_client=self.storage,
            bucket_name="tasaciones-prueba",
            expected_input_prefix=f"ingresos/{manifest['id_lote']}/pdfs/",
            expected_output_object=manifest["resultado_objeto"],
            use_environment_reviewer=False,
        )
        self.assertEqual(summary["estado"], BATCH_COMPLETED)
        saved = self.store.get(manifest["id_lote"])
        self.assertEqual(saved["pdfs_procesados"], 2)
        self.assertTrue(saved["resultado_disponible"])
        output = self.storage.bucket("tasaciones-prueba").blob(manifest["resultado_objeto"]).data
        workbook = load_workbook(io.BytesIO(output), data_only=True)
        self.assertEqual(workbook.sheetnames, ["PARA_PROCESAR", "REVISION_IA", "CONTROL"])
        self.assertEqual([cell.value for cell in workbook["PARA_PROCESAR"][1]], PARA_PROCESAR_COLUMNS)
        self.assertEqual([cell.value for cell in workbook["REVISION_IA"][1]], REVIEW_COLUMNS)
        self.assertEqual([cell.value for cell in workbook["CONTROL"][1]], CONTROL_COLUMNS)

    def test_worker_rejects_manifest_without_all_confirmed_pdfs(self):
        manifest, _ = self.api.create_batch(payload([file_item(1)]))
        def force_processing(current):
            current["estado"] = BATCH_PROCESSING
        update_manifest(self.store, manifest["id_lote"], force_processing)
        with self.assertRaisesRegex(BatchError, "todos los PDFs confirmados"):
            process_batch_gcs(
                manifest["id_lote"],
                store=self.store,
                storage_client=self.storage,
                bucket_name="tasaciones-prueba",
                use_environment_reviewer=False,
            )

    def test_direct_pdf_entries_keep_distinct_case_ids_for_same_content_and_names(self):
        content = make_pdf()
        _, review_rows, control_rows = process_pdf_entries(
            [("D04.pdf", content), ("D05.pdf", content)],
            use_environment_reviewer=False,
        )
        self.assertEqual(len(review_rows), 2)
        self.assertEqual(len({row["ID_CASO"] for row in control_rows}), 2)


if __name__ == "__main__":
    unittest.main()
