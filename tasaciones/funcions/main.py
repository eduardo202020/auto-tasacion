"""Cloud Run source-deployment entry point.

Google's Python functions buildpack discovers main.py. The implementation
remains in google-funcion.py to preserve the local development filename.
"""
import importlib.util
from pathlib import Path

_path = Path(__file__).with_name("google-funcion.py")
_spec = importlib.util.spec_from_file_location("tasacion_impl", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

procesar_tasaciones = _module.procesar_tasaciones
