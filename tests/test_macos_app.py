import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MacOSApplicationTests(unittest.TestCase):
    def test_reference_workflow_exposes_required_surfaces(self):
        workflow = json.loads((ROOT / "macos/Resources/reference_workflow.json").read_text())
        self.assertEqual([item["id"] for item in workflow["sections"]], [
            "projects", "transcript", "knowledge", "media", "navigation",
            "operations", "obsidian", "onedrive", "deferred",
        ])
        self.assertEqual(workflow["sections"][-1]["status"], "LATER_UNAVAILABLE")
        self.assertIn("#t=", workflow["navigation"]["source_locator"])

    def test_deferred_registry_has_no_actions(self):
        registry = json.loads((ROOT / "macos/Resources/deferred_features.json").read_text())
        self.assertFalse(registry["actions_available"])
        self.assertEqual(registry["status"], "DEFERRED_TO_LATER_WORK")
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        self.assertIn('section.id == "deferred"', source)
        self.assertIn("actionButton.isEnabled = false", source)

    def test_closed_bridge_rejects_unknown_and_previews_without_writes(self):
        bridge = ROOT / "macos/Resources/bridge.py"
        unknown = subprocess.run(["python3", str(bridge), "publish"], capture_output=True, text=True)
        self.assertNotEqual(unknown.returncode, 0)
        for operation in ("obsidian-preview", "onedrive-preview"):
            result = subprocess.run(["python3", str(bridge), operation], check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["writes_performed"]); self.assertFalse(payload["external_actions_performed"])
            self.assertFalse(payload["cloud_verified"])

    def test_reproducible_build_and_launch_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([str(ROOT / "scripts/test_macos_app.sh")], check=True,
                                    capture_output=True, text=True, timeout=60)
            self.assertIn("INTEGRA_MACOS_SELF_TEST: PASS", result.stdout)
            self.assertIn("INTEGRA_MACOS_LAUNCH_TEST: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
