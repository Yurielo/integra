import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.test_publishing import fixtures


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = Path(os.environ.get("INTEGRA_TEST_BRIDGE", ROOT / "macos/Resources/bridge.py"))


class PublicationRouteTests(unittest.TestCase):
    def test_selected_onedrive_target_converts_package_and_replays_same_version(self):
        *_, manifest, files = fixtures()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "package"
            for name, data in files.items():
                path = package / "files" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (package / "package.json").write_text(json.dumps(manifest))
            target = root / "synthetic-onedrive"
            target.mkdir()
            environment = {**os.environ, "INTEGRA_APP_DATA_ROOT": str(root / "app-data")}
            request = {"package_dir": str(package), "target_dir": str(target), "publication_target": "onedrive"}

            def call(operation):
                result = subprocess.run([os.environ.get("INTEGRA_TEST_PYTHON", "python3"), str(BRIDGE), operation],
                    input=json.dumps(request), text=True, capture_output=True, env=environment, check=True)
                return json.loads(result.stdout)["result"]

            preview = call("package-preview")
            self.assertEqual(preview["state"], "DRY_RUN_AVAILABLE")
            self.assertFalse(list(target.rglob("COMPLETE.json")))
            published = call("package-publish")
            self.assertEqual(published["state"], "LOCALLY_PUBLISHED")
            self.assertFalse(published["cloud_verified"])
            self.assertEqual(preview["package_id"], published["package_id"])
            repeated = call("package-publish")
            self.assertEqual(repeated["package_id"], published["package_id"])
            self.assertEqual(len(list(target.rglob("COMPLETE.json"))), 1)
            request["publication_target"] = "unknown"
            with self.assertRaises(subprocess.CalledProcessError):
                call("package-preview")

    def test_native_ui_sends_selected_destination(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        self.assertIn('"publication_target": kind', source)
        self.assertIn('"build-reviewed-package"', source)


if __name__ == "__main__":
    unittest.main()
