"""Valida el catálogo de tasadoras y perfiles de plantilla versionados."""
from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cloud-run"))

from profile_registry import load_profiles, load_providers, validate_reference_data


def main() -> int:
    issues = validate_reference_data()
    summary = {
        "perfiles": [profile.profile_id for profile in load_profiles()],
        "tasadoras": sorted(load_providers()),
        "errores": len(issues),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for issue in issues:
        print(f"ERROR: {issue}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
