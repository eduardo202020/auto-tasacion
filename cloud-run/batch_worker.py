"""Worker local para Cloud Run Job de lotes masivos.

Este módulo no descarga desde OneDrive ni expone una API. Recibe un ZIP como
archivo seekable, normalmente montado por Cloud Storage FUSE, procesa un PDF a
la vez y escribe el mismo XLSX contractual que el endpoint HTTP existente.
La integración Microsoft Graph y el lanzamiento autenticado del Job son capas
separadas que requieren las aprobaciones de seguridad definidas en el diseño.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from service import build_workbook, process_zip_file


INPUT_ZIP_ENV = "BATCH_INPUT_ZIP"
OUTPUT_XLSX_ENV = "BATCH_OUTPUT_XLSX"


def process_batch_file(input_zip: str | Path, output_xlsx: str | Path) -> dict[str, int | str]:
    """Procesa un ZIP montado y publica el XLSX solo cuando está completo."""
    output_path = Path(output_xlsx)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ready_rows, review_rows, control_rows = process_zip_file(input_zip)
    workbook = build_workbook(ready_rows, review_rows, control_rows)

    temporary_path = output_path.with_name(f".{output_path.name}.{uuid4().hex}.tmp")
    try:
        with temporary_path.open("wb") as destination:
            destination.write(workbook.getbuffer())
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return {
        "estado": "COMPLETADO",
        "para_procesar": len(ready_rows),
        "revision_ia": len(review_rows),
        "control": len(control_rows),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Procesa un lote ZIP montado para tasaciones.")
    parser.add_argument("--input-zip", default=os.getenv(INPUT_ZIP_ENV), help="Ruta local o GCS FUSE al ZIP.")
    parser.add_argument("--output-xlsx", default=os.getenv(OUTPUT_XLSX_ENV), help="Ruta de salida del XLSX.")
    arguments = parser.parse_args()
    if not arguments.input_zip or not arguments.output_xlsx:
        parser.error("--input-zip y --output-xlsx son obligatorios")
    return arguments


def main() -> int:
    arguments = parse_args()
    try:
        summary = process_batch_file(arguments.input_zip, arguments.output_xlsx)
    except ValueError as error:
        # No se registran rutas, nombres de PDFs ni contenido documental.
        print(json.dumps({"estado": "FALLIDO", "codigo": "ZIP_INVALIDO", "mensaje": str(error)}, ensure_ascii=False))
        return 2
    except Exception:
        print(json.dumps({"estado": "FALLIDO", "codigo": "ERROR_INTERNO"}, ensure_ascii=False))
        return 1
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
