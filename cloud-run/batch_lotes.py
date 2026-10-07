"""Modelo persistente de lotes masivos compuestos por PDFs individuales.

Power Automate es el único componente que lee contenido desde OneDrive. Este
módulo no conoce Microsoft Graph, URLs de OneDrive ni contenido documental;
solo conserva el manifiesto, el estado de cada carga y la idempotencia.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from typing import Any, Callable, Protocol

from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage


MAX_PDFS_PER_BATCH = 300
MAX_BATCH_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_PDF_BYTES = 90_000_000
PDF_CONTENT_TYPE = "application/pdf"
DEFAULT_SOURCE_FOLDER = "/auto-tasaciones"
BATCH_STATE_PREFIX = "estado/lotes"
BATCH_INPUT_PREFIX = "ingresos"
BATCH_RESULT_PREFIX = "resultados"
_SAFE_OBJECT_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")

FILE_PENDING = "PENDIENTE"
FILE_UPLOADING = "SUBIENDO"
FILE_UPLOADED = "CARGADO"
FILE_FAILED = "FALLIDO"
FILE_SOURCE_CHANGED = "FALLIDO_ORIGEN_CAMBIO"

BATCH_RECEIVED = "RECIBIDO"
BATCH_UPLOADING = "CARGANDO_PDFS"
BATCH_READY = "LISTO_PARA_PROCESAR"
BATCH_PROCESSING = "EN_PROCESO"
BATCH_COMPLETED = "COMPLETADO"
BATCH_DELIVERED = "ENTREGADO"
BATCH_FAILED = "FALLIDO"
BATCH_SOURCE_CHANGED = "FALLIDO_ORIGEN_CAMBIO"


class BatchError(ValueError):
    """Error de contrato seguro para devolver a Power Automate."""

    def __init__(self, message: str, *, code: str = "MANIFIESTO_INVALIDO", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


class ConcurrentBatchUpdate(RuntimeError):
    """La versión del manifiesto cambió antes de persistir una actualización."""


@dataclass(frozen=True)
class BatchLimits:
    max_pdfs: int = MAX_PDFS_PER_BATCH
    max_total_bytes: int = MAX_BATCH_TOTAL_BYTES
    max_pdf_bytes: int = MAX_PDF_BYTES

    @classmethod
    def from_environment(cls) -> "BatchLimits":
        return cls(
            max_pdfs=_environment_positive_int("BATCH_MAX_PDFS", MAX_PDFS_PER_BATCH),
            max_total_bytes=_environment_positive_int("BATCH_MAX_TOTAL_BYTES", MAX_BATCH_TOTAL_BYTES),
            max_pdf_bytes=_environment_positive_int("BATCH_MAX_PDF_BYTES", MAX_PDF_BYTES),
        )


def _environment_positive_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise BatchError(f"La configuración {name} no es un entero válido", code="CONFIGURACION_INVALIDA", status=500) from error
    if parsed <= 0:
        raise BatchError(f"La configuración {name} debe ser positiva", code="CONFIGURACION_INVALIDA", status=500)
    return parsed


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def configured_source_folder() -> str:
    return normalize_folder(os.getenv("BATCH_ALLOWED_SOURCE_FOLDER", DEFAULT_SOURCE_FOLDER))


def normalize_folder(value: Any) -> str:
    folder = str(value or "").strip().replace("\\", "/")
    if not folder.startswith("/") or ".." in folder.split("/"):
        raise BatchError("La carpeta de origen no es válida")
    normalized = "/" + "/".join(part for part in folder.split("/") if part)
    if normalized == "/":
        raise BatchError("La carpeta de origen no es válida")
    return normalized


def safe_pdf_filename(value: Any) -> str:
    name = str(value or "").strip().replace("\\", "/")
    if not name or "/" in name or not name.lower().endswith(".pdf"):
        raise BatchError("Cada archivo del lote debe ser un PDF", code="ARCHIVO_NO_PDF")
    if len(name) > 240:
        raise BatchError("El nombre de un PDF excede el máximo permitido")
    return name


def safe_object_filename(filename: str) -> str:
    stem = _SAFE_OBJECT_FILENAME.sub("_", filename)
    return stem[:180] or "documento.pdf"


def _required_identifier(value: Any, label: str) -> str:
    identifier = str(value or "").strip()
    if not identifier or len(identifier) > 512:
        raise BatchError(f"{label} es obligatorio y debe tener un tamaño válido")
    return identifier


def _positive_size(value: Any) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError) as error:
        raise BatchError("tamano_bytes debe ser un entero válido") from error
    if size <= 0:
        raise BatchError("tamano_bytes debe ser mayor que cero")
    return size


def file_identity_key(item_id: str, etag: str) -> str:
    return f"{item_id}:{etag}"


def manifest_idempotency_key(source_folder: str, files: list[dict[str, Any]]) -> str:
    identities = sorted(file_identity_key(item["item_id"], item["etag"]) for item in files)
    source = f"{source_folder}|" + "|".join(identities)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def batch_id_from_key(idempotency_key: str) -> str:
    return f"TAS-{idempotency_key[:20].upper()}"


def file_id_from_identity(item_id: str, etag: str) -> str:
    digest = hashlib.sha256(file_identity_key(item_id, etag).encode("utf-8")).hexdigest()
    return f"ARC-{digest[:16].upper()}"


def batch_object_name(batch_id: str, file_id: str, filename: str) -> str:
    return f"{BATCH_INPUT_PREFIX}/{batch_id}/pdfs/{file_id}_{safe_object_filename(filename)}"


def batch_result_object_name(batch_id: str) -> str:
    return f"{BATCH_RESULT_PREFIX}/{batch_id}/Resultado_Final_{batch_id}.xlsx"


def build_manifest(payload: dict[str, Any], *, limits: BatchLimits | None = None, allowed_folder: str | None = None) -> dict[str, Any]:
    """Normaliza un manifiesto sin leer ni transportar contenido de PDFs."""
    if not isinstance(payload, dict):
        raise BatchError("El cuerpo JSON debe ser un objeto")
    limits = limits or BatchLimits.from_environment()
    source_folder = normalize_folder(payload.get("carpeta_origen"))
    if source_folder != (allowed_folder or configured_source_folder()):
        raise BatchError("La carpeta de origen no está autorizada", code="CARPETA_NO_AUTORIZADA", status=403)

    supplied_files = payload.get("archivos")
    if not isinstance(supplied_files, list) or not supplied_files:
        raise BatchError("El manifiesto debe contener al menos un PDF")
    if len(supplied_files) > limits.max_pdfs:
        raise BatchError(f"El lote supera el máximo de {limits.max_pdfs} PDFs", code="LIMITE_PDFS_EXCEDIDO")

    files: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()
    invalid_file_errors: list[str] = []
    for supplied in supplied_files:
        if not isinstance(supplied, dict):
            raise BatchError("Cada archivo del manifiesto debe ser un objeto")
        item_id = _required_identifier(supplied.get("item_id"), "item_id")
        etag = _required_identifier(supplied.get("etag"), "etag")
        if item_id in seen_item_ids:
            raise BatchError("Un item_id no puede repetirse dentro del mismo lote")
        seen_item_ids.add(item_id)
        filename = safe_pdf_filename(supplied.get("nombre"))
        size = _positive_size(supplied.get("tamano_bytes"))
        file_id = file_id_from_identity(item_id, etag)
        state = FILE_PENDING
        error = ""
        if size > limits.max_pdf_bytes:
            state = FILE_FAILED
            error = "El PDF excede el tamaño individual máximo permitido"
            invalid_file_errors.append(error)
        files.append({
            "id_archivo": file_id,
            "item_id": item_id,
            "nombre": filename,
            "etag": etag,
            "tamano_bytes": size,
            "objeto_gcs": "",
            "estado": state,
            "mensaje": error,
            "etag_confirmado": "",
        })

    total_bytes = sum(item["tamano_bytes"] for item in files)
    if total_bytes > limits.max_total_bytes:
        raise BatchError("El lote excede el tamaño total máximo permitido", code="LIMITE_TOTAL_EXCEDIDO")

    key = manifest_idempotency_key(source_folder, files)
    batch_id = batch_id_from_key(key)
    for item in files:
        item["objeto_gcs"] = batch_object_name(batch_id, item["id_archivo"], item["nombre"])

    now = utc_timestamp()
    manifest = {
        "version": 1,
        "id_lote": batch_id,
        "clave_idempotencia": key,
        "carpeta_origen": source_folder,
        "estado": BATCH_FAILED if invalid_file_errors else BATCH_RECEIVED,
        "mensaje": invalid_file_errors[0] if invalid_file_errors else "",
        "creado_en": now,
        "actualizado_en": now,
        "total_pdfs": len(files),
        "tamano_total_bytes": total_bytes,
        "pdfs_cargados": 0,
        "pdfs_procesados": 0,
        "pdfs_fallidos": len(invalid_file_errors),
        "resultado_objeto": batch_result_object_name(batch_id),
        "resultado_disponible": False,
        "ejecucion_job": "",
        "archivos": files,
    }
    refresh_manifest_progress(manifest)
    return manifest


def refresh_manifest_progress(manifest: dict[str, Any]) -> None:
    """Recalcula progreso y los estados derivados sin alterar estados finales."""
    files = manifest.get("archivos", [])
    manifest["total_pdfs"] = len(files)
    manifest["pdfs_cargados"] = sum(1 for item in files if item.get("estado") == FILE_UPLOADED)
    manifest["pdfs_fallidos"] = sum(1 for item in files if item.get("estado") in {FILE_FAILED, FILE_SOURCE_CHANGED})

    current = str(manifest.get("estado") or "")
    if current in {BATCH_PROCESSING, BATCH_COMPLETED, BATCH_DELIVERED}:
        return
    if any(item.get("estado") == FILE_SOURCE_CHANGED for item in files):
        manifest["estado"] = BATCH_SOURCE_CHANGED
    elif any(item.get("estado") == FILE_FAILED for item in files):
        manifest["estado"] = BATCH_FAILED
    elif files and all(item.get("estado") == FILE_UPLOADED for item in files):
        manifest["estado"] = BATCH_READY
    elif any(item.get("estado") == FILE_UPLOADING for item in files) or manifest["pdfs_cargados"]:
        manifest["estado"] = BATCH_UPLOADING
    else:
        manifest["estado"] = BATCH_RECEIVED


def public_batch_status(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "id_lote": manifest["id_lote"],
        "estado": manifest["estado"],
        "mensaje": manifest.get("mensaje", ""),
        "total_pdfs": manifest["total_pdfs"],
        "pdfs_cargados": manifest["pdfs_cargados"],
        "pdfs_procesados": manifest.get("pdfs_procesados", 0),
        "pdfs_fallidos": manifest["pdfs_fallidos"],
        "resultado_disponible": bool(manifest.get("resultado_disponible")),
    }


def find_file(manifest: dict[str, Any], file_id: str) -> dict[str, Any]:
    for item in manifest.get("archivos", []):
        if item.get("id_archivo") == file_id:
            return item
    raise BatchError("El archivo no pertenece al manifiesto", code="ARCHIVO_NO_ENCONTRADO", status=404)


class BatchStore(Protocol):
    def get(self, batch_id: str) -> dict[str, Any] | None: ...

    def create_if_absent(self, manifest: dict[str, Any]) -> dict[str, Any]: ...

    def save(self, manifest: dict[str, Any]) -> dict[str, Any]: ...


class InMemoryBatchStore:
    """Almacén de prueba. No se usa para ejecuciones desplegadas."""

    def __init__(self):
        self._batches: dict[str, dict[str, Any]] = {}

    def get(self, batch_id: str) -> dict[str, Any] | None:
        current = self._batches.get(batch_id)
        return deepcopy(current) if current else None

    def create_if_absent(self, manifest: dict[str, Any]) -> dict[str, Any]:
        batch_id = manifest["id_lote"]
        if batch_id not in self._batches:
            copy = deepcopy(manifest)
            copy["_store_generation"] = 1
            self._batches[batch_id] = copy
        return deepcopy(self._batches[batch_id])

    def save(self, manifest: dict[str, Any]) -> dict[str, Any]:
        batch_id = manifest["id_lote"]
        if batch_id not in self._batches:
            raise BatchError("El lote no existe", code="LOTE_NO_ENCONTRADO", status=404)
        expected = manifest.get("_store_generation")
        current = self._batches[batch_id]
        if expected is not None and expected != current.get("_store_generation"):
            raise ConcurrentBatchUpdate()
        copy = deepcopy(manifest)
        copy["_store_generation"] = int(current.get("_store_generation", 0)) + 1
        self._batches[batch_id] = copy
        return deepcopy(copy)


class GcsBatchStore:
    """Persistencia JSON en GCS con control optimista de concurrencia."""

    def __init__(self, bucket_name: str, *, client: storage.Client | None = None):
        if not bucket_name:
            raise BatchError("El bucket de estado de lotes no está configurado", code="CONFIGURACION_INVALIDA", status=500)
        self._bucket = (client or storage.Client()).bucket(bucket_name)

    @staticmethod
    def object_name(batch_id: str) -> str:
        return f"{BATCH_STATE_PREFIX}/{batch_id}.json"

    def get(self, batch_id: str) -> dict[str, Any] | None:
        blob = self._bucket.blob(self.object_name(batch_id))
        try:
            blob.reload()
            payload = json.loads(blob.download_as_bytes().decode("utf-8"))
        except NotFound:
            return None
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BatchError("El estado persistido del lote no es válido", code="ESTADO_CORRUPTO", status=500) from error
        if not isinstance(payload, dict):
            raise BatchError("El estado persistido del lote no es válido", code="ESTADO_CORRUPTO", status=500)
        payload["_store_generation"] = int(blob.generation or 0)
        return payload

    def create_if_absent(self, manifest: dict[str, Any]) -> dict[str, Any]:
        blob = self._bucket.blob(self.object_name(manifest["id_lote"]))
        try:
            blob.upload_from_string(_serialise_manifest(manifest), content_type="application/json", if_generation_match=0)
        except PreconditionFailed:
            existing = self.get(manifest["id_lote"])
            if existing is None:
                raise ConcurrentBatchUpdate()
            return existing
        created = self.get(manifest["id_lote"])
        if created is None:
            raise BatchError("No fue posible guardar el lote", code="ESTADO_NO_DISPONIBLE", status=500)
        return created

    def save(self, manifest: dict[str, Any]) -> dict[str, Any]:
        generation = manifest.get("_store_generation")
        if not generation:
            raise ConcurrentBatchUpdate()
        blob = self._bucket.blob(self.object_name(manifest["id_lote"]))
        try:
            blob.upload_from_string(
                _serialise_manifest(manifest),
                content_type="application/json",
                if_generation_match=int(generation),
            )
        except PreconditionFailed as error:
            raise ConcurrentBatchUpdate() from error
        saved = self.get(manifest["id_lote"])
        if saved is None:
            raise BatchError("No fue posible guardar el lote", code="ESTADO_NO_DISPONIBLE", status=500)
        return saved


def _serialise_manifest(manifest: dict[str, Any]) -> str:
    payload = {key: value for key, value in manifest.items() if not key.startswith("_store_")}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def state_bucket_name() -> str:
    return os.getenv("BATCH_STATE_BUCKET", "").strip() or os.getenv("GCS_UPLOAD_BUCKET", "").strip()


def state_store_from_environment() -> GcsBatchStore:
    return GcsBatchStore(state_bucket_name())


def update_manifest(
    store: BatchStore,
    batch_id: str,
    change: Callable[[dict[str, Any]], Any],
    *,
    attempts: int = 5,
) -> tuple[dict[str, Any], Any]:
    """Aplica una mutación idempotente y reintenta conflictos de versión."""
    for _ in range(attempts):
        manifest = store.get(batch_id)
        if manifest is None:
            raise BatchError("El lote no existe", code="LOTE_NO_ENCONTRADO", status=404)
        result = change(manifest)
        manifest["actualizado_en"] = utc_timestamp()
        try:
            return store.save(manifest), result
        except ConcurrentBatchUpdate:
            continue
    raise BatchError("El lote cambió durante la actualización; reintente", code="CONFLICTO_CONCURRENCIA", status=409)

