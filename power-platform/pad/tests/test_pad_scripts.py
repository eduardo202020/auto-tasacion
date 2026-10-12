"""Static checks for local PAD helper scripts.

These checks keep the helpers runnable through ``powershell.exe -File`` on
Windows PowerShell, where ``$PSScriptRoot`` is not safe as a parameter default.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


PAD_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PAD_ROOT.parents[1]
LOCATIONS = REPOSITORY_ROOT / "config" / "automation-locations.json"


class PadHelperScriptTests(unittest.TestCase):
    def test_scripts_resolve_script_root_inside_their_body(self) -> None:
        for name in (
            "New-PadSimulationConfig.ps1",
            "Test-AutomationLocations.ps1",
            "Start-PadSimulationMonitor.ps1",
            "Stop-PadSimulationMonitor.ps1",
        ):
            script = (PAD_ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("= (Join-Path $PSScriptRoot", script, name)
            self.assertIn("Join-Path $PSScriptRoot", script, name)

        for name in ("Start-PadSimulationMonitor.ps1", "Stop-PadSimulationMonitor.ps1"):
            script = (PAD_ROOT / name).read_text(encoding="utf-8")
            self.assertIn("Resolve-PadRuntimeDirectory", script, name)
            self.assertIn("location_profile", script, name)

    def test_bundle_excludes_local_state_and_python_caches(self) -> None:
        script = (PAD_ROOT / "New-PadSimulationBundle.ps1").read_text(encoding="utf-8")
        self.assertIn("config.local.json", script)
        self.assertIn("__pycache__", script)
        self.assertIn(".venv", script)
        self.assertIn("runtime", script)

    def test_location_profiles_keep_runtime_outside_shared_input(self) -> None:
        locations = json.loads(LOCATIONS.read_text(encoding="utf-8-sig"))
        self.assertEqual(
            locations["onedrive"]["base_folder"],
            "/automatizaciones-jhglazar/auto-tasaciones",
        )
        for name, profile in locations["pad"]["profiles"].items():
            input_path = Path(profile["input_directory"])
            runtime_path = Path(profile["runtime_directory"])
            self.assertNotEqual(input_path, runtime_path, name)
            self.assertNotIn(str(input_path).lower(), str(runtime_path).lower(), name)

    def test_development_runtime_config_refers_to_the_central_profile(self) -> None:
        for filename, profile in (
            ("config.development.json", "development"),
            ("config.production.example.json", "production"),
        ):
            config = json.loads((PAD_ROOT / filename).read_text(encoding="utf-8-sig"))
            self.assertEqual(config["location_profile"], profile)
            self.assertEqual(config["locations_config_path"], "../../config/automation-locations.json")
            self.assertNotIn("input_directory", config)
            self.assertNotIn("runtime_directory", config)


if __name__ == "__main__":
    unittest.main()
