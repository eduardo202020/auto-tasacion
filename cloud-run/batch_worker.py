"""Worker de Cloud Run Job para lotes de PDFs individuales en Cloud Storage.

El manifiesto determina qué objetos están confirmados. El worker descarga un
solo PDF por iteración, comparte las reglas de extracción del endpoint ZIP
heredado y publica el mismo contrato XLSX.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import traceback
from typing import Any, Iterator

from google.cloud import storage

from batch_lotes import (
    BATCH_COMPLETED,
    BATCH_DELIVERED,
    BATCH_FAILED,
    BATCH_PROCESSING,
    BATCH_SOURCE_CHANGED,
    FILE_UPLOADED,
    BatchLimits,
    PDF_CONTENT_TYPE,
    BatchError,
    BatchStore,
    state_store_from_environment,
    update_manifest,
)
from service import build_workbook, process_pdf_entries


BATCH_ID_ENV = "BATCH_ID"
BATCH_INPUT_PREFIX_ENV = "BATCH_INPUT_PREFIX"
BATCH_OUTPUT_XLSX_ENV = "BATCH_OUTPUT_XLSX"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _log_event(event: str, **fields: Any) -> None:
    """Emite telemetría estructurada sin contenido documental ni secretos."""
    print(json.dumps({"evento": event, **fields}, ensure_ascii=False, separators=(",", ":")), flush=True)


def _safe_traceback(error: BaseException) -> list[dict[str, int | str]]:
    """Devuelve solo marcos de código, nunca ``str(error)`` ni valores de PDFs."""
    return [
        {"archivo": Path(frame.filename).name, "linea": frame.lineno, "funcion": frame.name}
        for frame in traceback.extract_tb(error.__traceback__)
    ]


def _safe_internal_message(stage: str, error: BaseException) -> str:
    """Mensaje útil para el manifiesto que no filtra contenido de documentos."""
    return f"Error interno durante {stage} ({type(error).__name__})"


def batch_storage_bucket_name() -> str:
    return os.getenv("BATCH_STORAGE_BUCKET", "").strip() or os.getenv("GCS_UPLOAD_BUCKET", "").strip()


def _verified_pdf_bytes(bucket: Any, item: dict[str, Any]) -> bytes:
    blob = bucket.blob(item["objeto_gcs"])
    if not blob.exists():
        raise BatchError("Un PDF confirmado ya no existe en Cloud Storage", code="OBJETO_NO_ENCONTRADO", status=500)
    blob.reload()
    if int(blob.size or 0) != int(item["tamano_bytes"]):
        raise BatchError("El tamaño de un PDF confirmado ya no coincide", code="TAMANO_NO_COINCIDE", status=500)
    if int(blob.size or 0) > BatchLimits.from_environment().max_pdf_bytes:
        raise BatchError("Un PDF confirmado excede el límite individual", code="PDF_DEMASIADO_GRANDE", status=500)
    content_type = getattr(blob, "content_type", None)
    if isinstance(content_type, str) and content_type and content_type.lower() != PDF_CONTENT_TYPE:
        raise BatchError("Un objeto confirmado no tiene tipo PDF", code="OBJETO_NO_PDF", status=500)
    content = blob.download_as_bytes()
    if len(content) != int(item["tamano_bytes"]):
        raise BatchError("No fue posible leer un PDF completo", code="LECTURA_INCOMPLETA", status=500)
    return content


def _mark_processed(store: BatchStore, batch_id: str) -> None:
    def increment(manifest: dict[str, Any]) -> None:
        if manifest.get("estado") != BATCH_PROCESSING:
            raise BatchError("El lote no está en proceso", code="ESTADO_INVALIDO", status=409)
        manifest["pdfs_procesados"] = min(
            int(manifest.get("pdfs_procesados", 0)) + 1,
            int(manifest.get("total_pdfs", 0)),
        )

    update_manifest(store, batch_id, increment)


def _mark_failed(store: BatchStore, batch_id: str, message: str) -> None:
    def fail(manifest: dict[str, Any]) -> None:
        if manifest.get("estado") in {BATCH_COMPLETED, BATCH_DELIVERED, BATCH_FAILED, BATCH_SOURCE_CHANGED}:
            return
        manifest["estado"] = BATCH_FAILED
        manifest["mensaje"] = message

    try:
        update_manifest(store, batch_id, fail)
    except BatchError:
        # No sustituir el error principal ni imprimir información documental.
        pass


def process_batch_gcs(
    batch_id: str,
    *,
    store: BatchStore | None = None,
    storage_client: storage.Client | None = None,
    bucket_name: str | None = None,
    expected_input_prefix: str | None = None,
    expected_output_object: str | None = None,
    use_environment_reviewer: bool = True,
) -> dict[str, int | str]:
    """Procesa exclusivamente los PDFs confirmados en el manifiesto indicado."""
    stage = "VALIDANDO_LOTE"
    store = store or state_store_from_environment()
    manifest = store.get(batch_id)
    if manifest is None:
        raise BatchError("El lote no existe", code="LOTE_NO_ENCONTRADO", status=404)
    if manifest.get("estado") != BATCH_PROCESSING:
        # A Job invoked against a non-terminal state must leave an observable
        # failure instead of stranding the manifest in an intermediate state.
        # Completed and delivered batches can only be stale duplicate Jobs.
        if manifest.get("estado") not in {BATCH_COMPLETED, BATCH_DELIVERED, BATCH_FAILED, BATCH_SOURCE_CHANGED}:
            _mark_failed(store, batch_id, "El Job se ejecutó antes de que el lote estuviera en proceso")
        raise BatchError("El lote no está listo para ejecución", code="ESTADO_INVALIDO", status=409)

    confirmed = [item for item in manifest.get("archivos", []) if item.get("estado") == FILE_UPLOADED]
    if len(confirmed) != int(manifest.get("total_pdfs", 0)):
        _mark_failed(store, batch_id, "El lote no tenía todos los PDFs confirmados al iniciar el Job")
        raise BatchError("El lote no tiene todos los PDFs confirmados", code="LOTE_INCOMPLETO", status=409)

    expected_prefix = f"ingresos/{batch_id}/pdfs/"
    if expected_input_prefix and expected_input_prefix != expected_prefix:
        _mark_failed(store, batch_id, "La configuración de entrada del Job no coincide con el manifiesto")
        raise BatchError("La configuración de entrada del Job no coincide", code="CONFIGURACION_INVALIDA", status=500)
    output_object = str(manifest.get("resultado_objeto") or "")
    if expected_output_object and expected_output_object != output_object:
        _mark_failed(store, batch_id, "La configuración de salida del Job no coincide con el manifiesto")
        raise BatchError("La configuración de salida del Job no coincide", code="CONFIGURACION_INVALIDA", status=500)

    resolved_bucket_name = bucket_name or batch_storage_bucket_name()
    if not resolved_bucket_name:
        raise BatchError("El bucket de lotes no está configurado", code="CONFIGURACION_INVALIDA", status=500)
    bucket = (storage_client or storage.Client()).bucket(resolved_bucket_name)

    def pdf_entries() -> Iterator[tuple[str, bytes]]:
        for item in confirmed:
            yield item["nombre"], _verified_pdf_bytes(bucket, item)

    try:
        _log_event("JOB_INICIADO", id_lote=batch_id, total_pdfs=len(confirmed))
        stage = "PROCESANDO_PDFS"
        ready_rows, review_rows, control_rows = process_pdf_entries(
            pdf_entries(),
            use_environment_reviewer=use_environment_reviewer,
            on_processed=lambda: _mark_processed(store, batch_id),
        )
        _log_event(
            "PDFS_PROCESADOS",
            id_lote=batch_id,
            total_pdfs=len(confirmed),
            para_procesar=len(ready_rows),
            revision_ia=len(review_rows),
            control=len(control_rows),
        )
        stage = "CONSTRUYENDO_XLSX"
        _log_event("CONSTRUYENDO_XLSX", id_lote=batch_id)
        workbook = build_workbook(ready_rows, review_rows, control_rows)
        _log_event("XLSX_CONSTRUIDO", id_lote=batch_id, tamano_bytes=len(workbook.getbuffer()))
        stage = "SUBIENDO_XLSX"
        _log_event("SUBIENDO_XLSX", id_lote=batch_id)
        bucket.blob(output_object).upload_from_file(
            workbook,
            rewind=True,
            content_type=XLSX_CONTENT_TYPE,
        )
        _log_event("XLSX_SUBIDO", id_lote=batch_id)

        def complete(current: dict[str, Any]) -> None:
            if current.get("estado") != BATCH_PROCESSING:
                raise BatchError("El estado del lote cambió durante el procesamiento", code="ESTADO_INVALIDO", status=409)
            current["pdfs_procesados"] = int(current.get("total_pdfs", 0))
            current["estado"] = BATCH_COMPLETED
            current["resultado_disponible"] = True
            current["mensaje"] = ""

        stage = "ACTUALIZANDO_MANIFIESTO"
        _log_event("ACTUALIZANDO_MANIFIESTO", id_lote=batch_id)
        completed, _ = update_manifest(store, batch_id, complete)
        _log_event("COMPLETADO", id_lote=batch_id, total_pdfs=len(confirmed))
    except BatchError as error:
        _mark_failed(store, batch_id, str(error))
        _log_event(
            "JOB_FALLIDO",
            estado=BATCH_FAILED,
            codigo=error.code,
            etapa=stage,
            tipo_error=type(error).__name__,
            mensaje=str(error),
            traceback=_safe_traceback(error),
        )
        raise
    except Exception as error:
        safe_message = _safe_internal_message(stage, error)
        _mark_failed(store, batch_id, safe_message)
        _log_event(
            "JOB_FALLIDO",
            estado=BATCH_FAILED,
            codigo="ERROR_INTERNO",
            etapa=stage,
            tipo_error=type(error).__name__,
            mensaje=safe_message,
            traceback=_safe_traceback(error),
        )
        raise RuntimeError(safe_message) from error

    return {
        "id_lote": completed["id_lote"],
        "estado": completed["estado"],
        "para_procesar": len(ready_rows),
        "revision_ia": len(review_rows),
        "control": len(control_rows),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Procesa un lote de PDFs individuales desde Cloud Storage.")
    parser.add_argument("--batch-id", default=os.getenv(BATCH_ID_ENV), help="ID del lote registrado.")
    parser.add_argument("--input-prefix", default=os.getenv(BATCH_INPUT_PREFIX_ENV), help="Prefijo esperado de PDFs en GCS.")
    parser.add_argument("--output-xlsx", default=os.getenv(BATCH_OUTPUT_XLSX_ENV), help="Objeto esperado de salida XLSX.")
    arguments = parser.parse_args()
    if not arguments.batch_id:
        parser.error("--batch-id es obligatorio")
    return arguments


def main() -> int:
    arguments = parse_args()
    try:
        summary = process_batch_gcs(
            arguments.batch_id,
            expected_input_prefix=arguments.input_prefix or None,
            expected_output_object=arguments.output_xlsx or None,
        )
    except BatchError as error:
        print(json.dumps({"estado": BATCH_FAILED, "codigo": error.code, "mensaje": str(error)}, ensure_ascii=False))
        return 2
    except Exception:
        print(json.dumps({"estado": BATCH_FAILED, "codigo": "ERROR_INTERNO"}, ensure_ascii=False))
        return 1
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
