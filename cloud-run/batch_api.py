"""API de control para lotes formados por PDFs individuales.

No lee OneDrive ni contenido documental. Power Automate obtiene cada PDF y usa
un ticket firmado de un solo objeto para escribirlo directamente en GCS.
"""
from __future__ import annotations

from datetime import timedelta
import hmac
import json
import os
import re
from typing import Any, Callable

import google.auth
from flask import Response
from google.auth.transport.requests import AuthorizedSession, Request as GoogleAuthRequest
from google.cloud import storage

from batch_lotes import (
    BATCH_COMPLETED,
    BATCH_DELIVERED,
    BATCH_FAILED,
    BATCH_PROCESSING,
    BATCH_READY,
    BATCH_SOURCE_CHANGED,
    FILE_FAILED,
    FILE_SOURCE_CHANGED,
    FILE_UPLOADED,
    FILE_UPLOADING,
    PDF_CONTENT_TYPE,
    BatchError,
    BatchLimits,
    BatchStore,
    batch_registration_status,
    build_manifest,
    find_file,
    orchestration_lease_seconds,
    public_batch_status,
    refresh_manifest_progress,
    state_store_from_environment,
    utc_timestamp,
    utc_timestamp_after,
    update_manifest,
)


UPLOAD_TTL_SECONDS = 15 * 60
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Batch-Control-Token",
}
_LOTE_PATH = re.compile(r"^/v1/lotes/([^/]+)$")
_TICKET_PATH = re.compile(r"^/v1/lotes/([^/]+)/archivos/([^/]+)/upload-ticket$")
_CONFIRM_PATH = re.compile(r"^/v1/lotes/([^/]+)/archivos/([^/]+)/confirmar$")
_START_PATH = re.compile(r"^/v1/lotes/([^/]+)/iniciar$")
_RESULT_TICKET_PATH = re.compile(r"^/v1/lotes/([^/]+)/resultado-ticket$")
_DELIVERY_PATH = re.compile(r"^/v1/lotes/([^/]+)/entrega$")
_ORCHESTRATION_CLAIM_PATH = re.compile(r"^/v1/lotes/([^/]+)/orquestacion/reclamar$")
_ORCHESTRATION_RENEW_PATH = re.compile(r"^/v1/lotes/([^/]+)/orquestacion/renovar$")
_ORCHESTRATION_RELEASE_PATH = re.compile(r"^/v1/lotes/([^/]+)/orquestacion/liberar$")


def _json_response(payload: dict[str, Any], status: int = 200) -> Response:
    response = Response(json.dumps(payload, ensure_ascii=False), status=status, mimetype="application/json")
    response.headers.update(CORS_HEADERS)
    return response


def _error_response(error: BatchError) -> Response:
    return _json_response({"status": "error", "codigo": error.code, "mensaje": str(error)}, error.status)


def _request_payload(request) -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise BatchError("El cuerpo JSON debe ser un objeto")
    return payload


def batch_upload_bucket_name() -> str:
    return os.getenv("BATCH_STORAGE_BUCKET", "").strip() or os.getenv("GCS_UPLOAD_BUCKET", "").strip()


def signing_service_account() -> str:
    return os.getenv("BATCH_SIGNING_SERVICE_ACCOUNT", "").strip() or os.getenv("GCS_SIGNING_SERVICE_ACCOUNT", "").strip()


def _default_job_launcher(manifest: dict[str, Any]) -> str:
    """Inicia un Cloud Run Job ya configurado, sin esperar su finalización."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    region = os.getenv("BATCH_JOB_REGION", "").strip()
    job_name = os.getenv("BATCH_JOB_NAME", "").strip()
    if not all((project, region, job_name)):
        raise BatchError("El Cloud Run Job de lotes no está configurado", code="JOB_NO_CONFIGURADO", status=503)

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    endpoint = f"https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job_name}:run"
    overrides = {
        "containerOverrides": [{
            "env": [
                {"name": "BATCH_ID", "value": manifest["id_lote"]},
                {"name": "BATCH_INPUT_PREFIX", "value": f"ingresos/{manifest['id_lote']}/pdfs/"},
                {"name": "BATCH_OUTPUT_XLSX", "value": manifest["resultado_objeto"]},
            ],
        }],
    }
    response = session.post(endpoint, json={"overrides": overrides}, timeout=30)
    if response.status_code not in {200, 201}:
        raise BatchError("No fue posible iniciar el procesamiento del lote", code="JOB_NO_INICIADO", status=503)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return str(payload.get("name") or "ejecucion-iniciada")


class BatchControlApi:
    """Operaciones HTTP para registrar, cargar y ejecutar un manifiesto."""

    def __init__(
        self,
        store: BatchStore,
        *,
        upload_bucket: str,
        storage_client: storage.Client | None = None,
        limits: BatchLimits | None = None,
        signer_email: str | None = None,
        signed_url_factory: Callable[[str], str] | None = None,
        job_launcher: Callable[[dict[str, Any]], str] | None = None,
    ):
        if not upload_bucket:
            raise BatchError("El bucket de lotes no está configurado", code="CONFIGURACION_INVALIDA", status=500)
        self.store = store
        self.bucket = (storage_client or storage.Client()).bucket(upload_bucket)
        self.limits = limits or BatchLimits.from_environment()
        self.signer_email = signer_email if signer_email is not None else signing_service_account()
        self.signed_url_factory = signed_url_factory
        self.job_launcher = job_launcher or _default_job_launcher

    def create_batch(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        manifest = build_manifest(payload, limits=self.limits)
        existing = self.store.get(manifest["id_lote"])
        saved = self.store.create_if_absent(manifest)
        if saved.get("clave_idempotencia") != manifest["clave_idempotencia"]:
            raise BatchError("Colisión inesperada de identificador de lote", code="COLISION_ID_LOTE", status=500)
        return saved, existing is None

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        manifest = self.store.get(batch_id)
        if manifest is None:
            raise BatchError("El lote no existe", code="LOTE_NO_ENCONTRADO", status=404)
        return manifest

    def claim_orchestration(self, batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Reserva de forma atómica un lote para una ejecución del orquestador.

        Los triggers de OneDrive tienen entrega *at least once*. El claim vive
        en el mismo manifiesto con control optimista de generación, por lo que
        dos ejecuciones concurrentes no pueden ser propietarias del lote a la
        vez. El propietario debe renovar la lease durante transferencias y
        polling largos.
        """
        owner = self._orchestration_owner(payload)
        now = utc_timestamp()
        lease_until = utc_timestamp_after(orchestration_lease_seconds(), now=now)

        def claim(manifest: dict[str, Any]) -> dict[str, Any]:
            state = str(manifest.get("estado") or "")
            if state in {BATCH_DELIVERED, BATCH_FAILED, BATCH_SOURCE_CHANGED}:
                return {"reclamado": False, "resultado": "TERMINAL"}

            control = self._orchestration_block(manifest, now=now)
            current_owner = str(control.get("propietario") or "")
            current_lease = str(control.get("lease_hasta") or "")
            lease_active = self._lease_is_active(current_lease, now=now)
            if current_owner and current_owner != owner and lease_active:
                return {"reclamado": False, "resultado": "OCUPADO"}
            if current_owner == owner and lease_active:
                control["fase"] = "ORQUESTANDO"
                control["actualizado_en"] = now
                return {"reclamado": True, "resultado": "REUTILIZADO"}

            control.update({
                "propietario": owner,
                "lease_hasta": lease_until,
                "fase": "ORQUESTANDO",
                "intentos": int(control.get("intentos") or 0) + 1,
                "ultimo_error": "",
                "actualizado_en": now,
            })
            return {"reclamado": True, "resultado": "RECLAMADO"}

        saved, result = update_manifest(self.store, batch_id, claim)
        return {
            "id_lote": saved["id_lote"],
            "estado": saved["estado"],
            **result,
            "lease_hasta": str(saved.get("orquestacion", {}).get("lease_hasta") or ""),
        }

    def renew_orchestration(self, batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Extiende un claim solo si la misma ejecución aún es propietaria."""
        owner = self._orchestration_owner(payload)
        now = utc_timestamp()
        lease_until = utc_timestamp_after(orchestration_lease_seconds(), now=now)

        def renew(manifest: dict[str, Any]) -> None:
            if manifest.get("estado") in {BATCH_DELIVERED, BATCH_FAILED, BATCH_SOURCE_CHANGED}:
                raise BatchError(
                    "El lote ya alcanzó un estado terminal",
                    code="ORQUESTACION_FINALIZADA",
                    status=409,
                )
            control = self._orchestration_block(manifest, now=now)
            if str(control.get("propietario") or "") != owner:
                raise BatchError(
                    "Otra ejecución ya posee la orquestación del lote",
                    code="ORQUESTACION_NO_PROPIETARIA",
                    status=409,
                )
            control.update({
                "lease_hasta": lease_until,
                "fase": "ORQUESTANDO",
                "actualizado_en": now,
            })

        saved, _ = update_manifest(self.store, batch_id, renew)
        return {
            "id_lote": saved["id_lote"],
            "renovado": True,
            "lease_hasta": str(saved.get("orquestacion", {}).get("lease_hasta") or ""),
        }

    def release_orchestration(self, batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Libera un claim interrumpido sin retroceder el estado del lote."""
        owner = self._orchestration_owner(payload)
        reason = str(payload.get("motivo") or "ORQUESTACION_INTERRUMPIDA").strip()[:240]
        now = utc_timestamp()

        def release(manifest: dict[str, Any]) -> bool:
            if manifest.get("estado") in {BATCH_DELIVERED, BATCH_FAILED, BATCH_SOURCE_CHANGED}:
                return False
            control = self._orchestration_block(manifest, now=now)
            if str(control.get("propietario") or "") != owner:
                return False
            control.update({
                "lease_hasta": now,
                "fase": "REINTENTO_REQUERIDO",
                "ultimo_error": reason,
                "actualizado_en": now,
            })
            if manifest.get("estado") not in {BATCH_DELIVERED, BATCH_FAILED, BATCH_SOURCE_CHANGED}:
                manifest["mensaje"] = "La orquestación requiere reintento: " + reason
            return True

        saved, released = update_manifest(self.store, batch_id, release)
        return {"id_lote": saved["id_lote"], "liberado": released, "estado": saved["estado"]}

    @staticmethod
    def _orchestration_owner(payload: dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            raise BatchError("El cuerpo JSON debe ser un objeto")
        owner = str(payload.get("id_ejecucion") or "").strip()
        if not owner or len(owner) > 512:
            raise BatchError("id_ejecucion es obligatorio", code="EJECUCION_INVALIDA")
        return owner

    @staticmethod
    def _orchestration_block(manifest: dict[str, Any], *, now: str) -> dict[str, Any]:
        control = manifest.get("orquestacion")
        if not isinstance(control, dict):
            control = {}
            manifest["orquestacion"] = control
        control.setdefault("propietario", "")
        control.setdefault("lease_hasta", "")
        control.setdefault("fase", "PENDIENTE")
        control.setdefault("intentos", 0)
        control.setdefault("ultimo_error", "")
        control.setdefault("actualizado_en", now)
        return control

    @staticmethod
    def _lease_is_active(lease_until: str, *, now: str) -> bool:
        # ISO UTC is lexicographically ordered. Both values originate in this
        # module and use the same canonical format, avoiding a second clock.
        return bool(lease_until) and lease_until > now

    def upload_ticket(self, batch_id: str, file_id: str) -> dict[str, Any]:
        def mark_uploading(manifest: dict[str, Any]) -> dict[str, Any]:
            if manifest.get("estado") in {BATCH_FAILED, "FALLIDO_ORIGEN_CAMBIO", BATCH_PROCESSING, BATCH_COMPLETED, BATCH_DELIVERED}:
                raise BatchError("El lote no acepta más cargas", code="LOTE_NO_DISPONIBLE", status=409)
            item = find_file(manifest, file_id)
            if item.get("estado") == FILE_UPLOADED:
                raise BatchError("El PDF ya fue confirmado", code="ARCHIVO_YA_CARGADO", status=409)
            if item.get("estado") in {FILE_FAILED, FILE_SOURCE_CHANGED}:
                raise BatchError("El PDF falló y no se puede cargar", code="ARCHIVO_NO_DISPONIBLE", status=409)
            was_uploading = item.get("estado") == FILE_UPLOADING
            item["estado"] = FILE_UPLOADING
            item["mensaje"] = ""
            refresh_manifest_progress(manifest)
            return {"item": item, "was_uploading": was_uploading}

        manifest, operation = update_manifest(self.store, batch_id, mark_uploading)
        item = operation["item"]
        object_name = str(item.get("objeto_gcs") or "")
        if not object_name:
            raise BatchError("El manifiesto no contiene destino para el PDF", code="ESTADO_CORRUPTO", status=500)
        # A retry can arrive after the PUT succeeded but before Power Automate
        # called confirmar. Reuse only an object that already matches the
        # declared size and MIME type; the final OneDrive eTag is still checked
        # by confirm_upload before the item becomes CARGADO.
        reuse_existing_object = operation["was_uploading"] and self._is_expected_uploaded_pdf(item)
        return {
            "id_lote": manifest["id_lote"],
            "id_archivo": item["id_archivo"],
            "estado": item["estado"],
            "requiere_carga": not reuse_existing_object,
            # Preserve the ticket contract for the recurrent migration flows.
            # The event orchestrator obeys requiere_carga and skips this URL
            # when it can safely reuse the object.
            "url_carga": self._signed_pdf_upload_url(object_name),
            "encabezados_carga": {"Content-Type": PDF_CONTENT_TYPE},
            "vence_en_segundos": UPLOAD_TTL_SECONDS,
        }

    def confirm_upload(self, batch_id: str, file_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise BatchError("El cuerpo JSON debe ser un objeto")
        confirmed_etag = str(payload.get("etag_confirmado") or "").strip()
        if not confirmed_etag:
            raise BatchError("etag_confirmado es obligatorio")
        manifest = self.get_batch(batch_id)
        if manifest.get("estado") in {BATCH_FAILED, "FALLIDO_ORIGEN_CAMBIO", BATCH_PROCESSING, BATCH_COMPLETED, BATCH_DELIVERED}:
            raise BatchError("El lote no acepta más confirmaciones", code="LOTE_NO_DISPONIBLE", status=409)
        item = find_file(manifest, file_id)
        if item.get("estado") == FILE_UPLOADED and item.get("etag_confirmado") == confirmed_etag:
            return public_batch_status(manifest)
        if confirmed_etag != item.get("etag"):
            failed = self._mark_upload_failed(
                batch_id, file_id, FILE_SOURCE_CHANGED,
                "El PDF cambió en OneDrive durante la transferencia",
            )
            raise BatchError(
                failed.get("mensaje") or "El PDF cambió durante la transferencia",
                code="ORIGEN_CAMBIO", status=409,
            )

        try:
            self._verify_uploaded_pdf(item)
        except BatchError as error:
            self._mark_upload_failed(batch_id, file_id, FILE_FAILED, str(error))
            raise

        def mark_uploaded(current: dict[str, Any]) -> None:
            current_item = find_file(current, file_id)
            if current_item.get("estado") == FILE_UPLOADED and current_item.get("etag_confirmado") == confirmed_etag:
                return
            if current_item.get("etag") != confirmed_etag:
                current_item["estado"] = FILE_SOURCE_CHANGED
                current_item["mensaje"] = "El PDF cambió en OneDrive durante la transferencia"
                refresh_manifest_progress(current)
                raise BatchError("El PDF cambió en OneDrive durante la transferencia", code="ORIGEN_CAMBIO", status=409)
            current_item["estado"] = FILE_UPLOADED
            current_item["etag_confirmado"] = confirmed_etag
            current_item["mensaje"] = ""
            refresh_manifest_progress(current)

        saved, _ = update_manifest(self.store, batch_id, mark_uploaded)
        return public_batch_status(saved)

    def start_batch(self, batch_id: str) -> dict[str, Any]:
        def mark_processing(current: dict[str, Any]) -> bool:
            if current.get("estado") == BATCH_PROCESSING:
                return False
            if current.get("estado") != BATCH_READY:
                raise BatchError("El lote no tiene todos los PDFs confirmados", code="LOTE_INCOMPLETO", status=409)
            current["estado"] = BATCH_PROCESSING
            current["mensaje"] = ""
            return True

        # Persist EN_PROCESO before submitting the Cloud Run Job. A Job can
        # begin immediately after the run request succeeds; launching it first
        # allowed it to read LISTO_PARA_PROCESAR and exit before this mutation.
        manifest, started = update_manifest(self.store, batch_id, mark_processing)
        if not started:
            return public_batch_status(manifest)

        try:
            execution = self.job_launcher(manifest)
        except BatchError:
            self._mark_job_launch_failed(batch_id)
            raise
        except Exception:
            self._mark_job_launch_failed(batch_id)
            raise

        def record_execution(current: dict[str, Any]) -> None:
            # The Job can complete before the launch endpoint returns. Preserve
            # that terminal progress while still retaining its execution id.
            if current.get("estado") in {BATCH_PROCESSING, BATCH_COMPLETED, BATCH_DELIVERED}:
                current["ejecucion_job"] = str(execution)

        saved, _ = update_manifest(self.store, batch_id, record_execution)
        return public_batch_status(saved)

    def _mark_job_launch_failed(self, batch_id: str) -> None:
        def fail(current: dict[str, Any]) -> None:
            # Never overwrite a result produced by a Job that did start despite
            # a transient response failure from the launch request.
            if current.get("estado") != BATCH_PROCESSING:
                return
            current["estado"] = BATCH_FAILED
            current["mensaje"] = "No fue posible iniciar el Cloud Run Job"

        try:
            update_manifest(self.store, batch_id, fail)
        except BatchError:
            # Preserve the launch error and avoid leaking implementation detail.
            pass

    def result_ticket(self, batch_id: str) -> dict[str, Any]:
        """Emite una URL temporal de solo lectura para el XLSX completado."""
        manifest = self.get_batch(batch_id)
        if manifest.get("estado") not in {BATCH_COMPLETED, BATCH_DELIVERED} or not manifest.get("resultado_disponible"):
            raise BatchError("El resultado del lote a?n no est? disponible", code="RESULTADO_NO_DISPONIBLE", status=409)
        object_name = str(manifest.get("resultado_objeto") or "")
        if not object_name:
            raise BatchError("El manifiesto no contiene resultado", code="ESTADO_CORRUPTO", status=500)
        blob = self.bucket.blob(object_name)
        if not blob.exists():
            raise BatchError("El resultado no existe en Cloud Storage", code="RESULTADO_NO_ENCONTRADO", status=409)
        return {
            "id_lote": manifest["id_lote"],
            "url_descarga": self._signed_result_download_url(object_name),
            "vence_en_segundos": UPLOAD_TTL_SECONDS,
        }

    def confirm_delivery(self, batch_id: str) -> dict[str, Any]:
        def mark_delivered(manifest: dict[str, Any]) -> None:
            if manifest.get("estado") == BATCH_DELIVERED:
                return
            if manifest.get("estado") != BATCH_COMPLETED or not manifest.get("resultado_disponible"):
                raise BatchError("El resultado del lote aún no está disponible", code="RESULTADO_NO_DISPONIBLE", status=409)
            manifest["estado"] = BATCH_DELIVERED
            manifest["mensaje"] = ""
            control = self._orchestration_block(manifest, now=utc_timestamp())
            control.update({
                "lease_hasta": utc_timestamp(),
                "fase": "ENTREGADO",
                "ultimo_error": "",
                "actualizado_en": utc_timestamp(),
            })

        saved, _ = update_manifest(self.store, batch_id, mark_delivered)
        return public_batch_status(saved)

    def _mark_upload_failed(self, batch_id: str, file_id: str, state: str, message: str) -> dict[str, Any]:
        def fail(manifest: dict[str, Any]) -> None:
            item = find_file(manifest, file_id)
            item["estado"] = state
            item["mensaje"] = message
            manifest["mensaje"] = message
            refresh_manifest_progress(manifest)

        saved, _ = update_manifest(self.store, batch_id, fail)
        return saved

    def _verify_uploaded_pdf(self, item: dict[str, Any]) -> None:
        object_name = str(item.get("objeto_gcs") or "")
        if not object_name:
            raise BatchError("El manifiesto no contiene destino para el PDF", code="ESTADO_CORRUPTO", status=500)
        blob = self.bucket.blob(object_name)
        if not blob.exists():
            raise BatchError("El PDF no existe en Cloud Storage", code="OBJETO_NO_ENCONTRADO", status=409)
        blob.reload()
        if int(blob.size or 0) != int(item["tamano_bytes"]):
            raise BatchError("El tamaño del PDF en Cloud Storage no coincide", code="TAMANO_NO_COINCIDE", status=409)
        content_type = getattr(blob, "content_type", None)
        if isinstance(content_type, str) and content_type and content_type.lower() != PDF_CONTENT_TYPE:
            raise BatchError("El objeto cargado no tiene tipo PDF", code="OBJETO_NO_PDF", status=409)

    def _is_expected_uploaded_pdf(self, item: dict[str, Any]) -> bool:
        """Indica si una transferencia interrumpida dejó un objeto reutilizable."""
        object_name = str(item.get("objeto_gcs") or "")
        if not object_name:
            return False
        blob = self.bucket.blob(object_name)
        if not blob.exists():
            return False
        blob.reload()
        if int(blob.size or 0) != int(item["tamano_bytes"]):
            return False
        content_type = getattr(blob, "content_type", None)
        return not isinstance(content_type, str) or not content_type or content_type.lower() == PDF_CONTENT_TYPE

    def _signed_result_download_url(self, object_name: str) -> str:
        if self.signed_url_factory is not None:
            return self.signed_url_factory(object_name)
        if not self.signer_email:
            raise BatchError("La cuenta de firma de Cloud Storage no est? configurada", code="CONFIGURACION_INVALIDA", status=500)
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(GoogleAuthRequest())
        blob = self.bucket.blob(object_name)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=UPLOAD_TTL_SECONDS),
            method="GET",
            service_account_email=self.signer_email,
            access_token=credentials.token,
        )

    def _signed_pdf_upload_url(self, object_name: str) -> str:
        if self.signed_url_factory is not None:
            return self.signed_url_factory(object_name)
        if not self.signer_email:
            raise BatchError("La cuenta de firma de Cloud Storage no está configurada", code="CONFIGURACION_INVALIDA", status=500)
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(GoogleAuthRequest())
        blob = self.bucket.blob(object_name)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=UPLOAD_TTL_SECONDS),
            method="PUT",
            content_type=PDF_CONTENT_TYPE,
            query_parameters={"ifGenerationMatch": "0"},
            service_account_email=self.signer_email,
            access_token=credentials.token,
        )


def controller_from_environment() -> BatchControlApi:
    return BatchControlApi(
        state_store_from_environment(),
        upload_bucket=batch_upload_bucket_name(),
    )


def _authenticate_control_request(request) -> None:
    # Secret Manager puede conservar un salto de l?nea de una carga por stdin.
    expected = os.getenv("BATCH_CONTROL_API_TOKEN", "").strip()
    if not expected:
        raise BatchError("La API de control no está habilitada", code="API_NO_HABILITADA", status=503)
    received = request.headers.get("X-Batch-Control-Token", "").strip()
    if not hmac.compare_digest(received, expected):
        raise BatchError("No autorizado para operar lotes", code="NO_AUTORIZADO", status=401)


def handle_request(
    request,
    controller: BatchControlApi | None = None,
    *,
    require_authentication: bool | None = None,
) -> Response:
    """Despacha únicamente rutas /v1/lotes; las URLs firmadas nunca se registran."""
    if request.method == "OPTIONS":
        return "", 204, CORS_HEADERS
    try:
        if require_authentication is None:
            require_authentication = controller is None
        if require_authentication:
            _authenticate_control_request(request)
        api = controller or controller_from_environment()
        path = request.path.rstrip("/") or "/"
        if request.method == "POST" and path == "/v1/lotes":
            manifest, created = api.create_batch(_request_payload(request))
            payload = batch_registration_status(manifest)
            payload["reutilizado"] = not created
            if manifest.get("estado") == BATCH_FAILED:
                return _json_response(payload, 422)
            return _json_response(payload, 201 if created else 200)
        matched = _LOTE_PATH.fullmatch(path)
        if request.method == "GET" and matched:
            # The recurring Power Automate loader needs the per-file operational
            # state to select PENDIENTE entries.  This response deliberately
            # exposes only manifest metadata: it never includes PDF content,
            # GCS object paths, or signed URLs.
            return _json_response(batch_registration_status(api.get_batch(matched.group(1))))
        matched = _TICKET_PATH.fullmatch(path)
        if request.method == "POST" and matched:
            return _json_response(api.upload_ticket(matched.group(1), matched.group(2)))
        matched = _CONFIRM_PATH.fullmatch(path)
        if request.method == "POST" and matched:
            return _json_response(api.confirm_upload(matched.group(1), matched.group(2), _request_payload(request)))
        matched = _START_PATH.fullmatch(path)
        if request.method == "POST" and matched:
            return _json_response(api.start_batch(matched.group(1)))
        matched = _RESULT_TICKET_PATH.fullmatch(path)
        if request.method == "POST" and matched:
            return _json_response(api.result_ticket(matched.group(1)))
        matched = _DELIVERY_PATH.fullmatch(path)
        if request.method == "POST" and matched:
            return _json_response(api.confirm_delivery(matched.group(1)))
        matched = _ORCHESTRATION_CLAIM_PATH.fullmatch(path)
        if request.method == "POST" and matched:
            return _json_response(api.claim_orchestration(matched.group(1), _request_payload(request)))
        matched = _ORCHESTRATION_RENEW_PATH.fullmatch(path)
        if request.method == "POST" and matched:
            return _json_response(api.renew_orchestration(matched.group(1), _request_payload(request)))
        matched = _ORCHESTRATION_RELEASE_PATH.fullmatch(path)
        if request.method == "POST" and matched:
            return _json_response(api.release_orchestration(matched.group(1), _request_payload(request)))
        raise BatchError("Ruta o método no permitido", code="RUTA_NO_ENCONTRADA", status=404)
    except BatchError as error:
        return _error_response(error)
    except Exception:
        return _json_response({"status": "error", "codigo": "ERROR_INTERNO", "mensaje": "Error interno al procesar el lote"}, 500)

