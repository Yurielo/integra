"""Exercise the AppKit bridge's read-only catalog operation with four products."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import tests.test_seminar_library as library_fixtures


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "macos/Resources/bridge.py"


class SeminarLibraryBridgeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = library_fixtures.SeminarLibraryTests("test_multi_product_read_only_deterministic_preview")
        self.fixture.setUp()
        self.specs = self.fixture.fixtures()
        self.data_root = self.fixture.root / "never-created-app-data"

    def tearDown(self):
        self.fixture.tearDown()

    def invoke(self, rows):
        process = subprocess.run(
            [sys.executable, "-B", str(BRIDGE), "seminar-library-preview"],
            input=json.dumps({"manifests": rows}), text=True, capture_output=True,
            env={**os.environ, "INTEGRA_APP_DATA_ROOT": str(self.data_root),
                 "PYTHONDONTWRITEBYTECODE": "1"}, cwd=ROOT, check=False,
        )
        self.assertFalse(self.data_root.exists())
        self.assertEqual(process.stderr, "")
        return process.returncode, json.loads(process.stdout)

    def rows(self):
        return [{"owner": owner, "path": str(path)} for owner, path in self.specs]

    def test_four_product_projection_is_deterministic_and_does_not_change_inputs(self):
        before = {path: path.read_bytes() for path in self.fixture.root.rglob("*") if path.is_file() and not path.is_symlink()}
        code, first = self.invoke(self.rows())
        self.assertEqual(code, 0)
        self.assertTrue(first["ok"])
        result = first["result"]
        self.assertEqual(result["summary"]["project_count"], 4)
        self.assertEqual(result["summary"]["owner_products"],
                         ["booktext", "integra", "seminartext", "videotext"])
        self.assertTrue(any(row["native_id"] is None for row in result["sources"]))
        self.assertTrue(any(row["availability"] in {"MISSING", "SYMLINK"} for row in result["sources"]))
        self.assertEqual(self.invoke(self.rows()), (code, first))
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_bad_manifest_fails_without_returning_old_catalog(self):
        broken = self.fixture.root / "broken.json"
        broken.write_text("{", encoding="utf-8")
        code, response = self.invoke([{"owner": "integra", "path": str(broken)}])
        self.assertEqual(code, 2)
        self.assertFalse(response["ok"])
        self.assertNotIn("result", response)
        self.assertIn("malformed manifest", response["error"])

    def test_unsupported_version_stays_a_diagnostic(self):
        wrong = self.fixture.write("unsupported.json", {"schemaVersion": 999})
        code, response = self.invoke([{"owner": "videotext", "path": str(wrong)}])
        self.assertEqual(code, 0)
        self.assertEqual(response["result"]["summary"]["unsupported_manifests"], 1)
        self.assertEqual(response["result"]["summary"]["project_count"], 0)

    def test_explicit_owner_and_unique_path_are_required(self):
        rows = self.rows()
        for invalid in ([rows[0], rows[0]], [{"owner": "unknown", "path": rows[0]["path"]}],
                        [{"owner": "integra", "path": "relative.json"}]):
            code, response = self.invoke(invalid)
            self.assertEqual(code, 2)
            self.assertFalse(response["ok"])


if __name__ == "__main__":
    unittest.main()
