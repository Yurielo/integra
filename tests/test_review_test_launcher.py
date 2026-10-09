"""Review test collection must never write into supplied runtime dependencies."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/run_review_tests.sh"


def inventory(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


class ReviewTestLauncherTests(unittest.TestCase):
    def test_normal_quality_gate_uses_guarded_entrypoint(self):
        workflow = (ROOT / ".github/workflows/quality-gate.yml").read_text()
        self.assertIn("./scripts/run_review_tests.sh", workflow)
        self.assertNotIn("python3 -m unittest discover", workflow)

    def test_startup_collection_and_child_import_leave_archive_unchanged(self):
        for inherited_guard in (None, "0"):
            with self.subTest(inherited_guard=inherited_guard), tempfile.TemporaryDirectory() as temporary:
                fixture = Path(temporary)
                archive = fixture / "protected-archive" / "site-packages"
                archive.mkdir(parents=True)
                guard = (
                    "import os, sys\n"
                    "assert sys.dont_write_bytecode, 'missing interpreter startup guard'\n"
                    "assert os.environ.get('PYTHONDONTWRITEBYTECODE') == '1', 'missing child guard'\n"
                )
                # sitecustomize executes before unittest or test-module collection.
                (archive / "sitecustomize.py").write_text(guard, encoding="utf-8")
                package = archive / "protected_review_dependency"
                package.mkdir()
                (package / "__init__.py").write_text(guard + "VALUE = 'collection-imported'\n", encoding="utf-8")
                collected = fixture / "tests"
                collected.mkdir()
                (collected / "test_collection_guard.py").write_text(
                    "import os, subprocess, sys, unittest\n"
                    "import protected_review_dependency\n"
                    "class CollectionGuard(unittest.TestCase):\n"
                    "    def test_inherited_guard(self):\n"
                    "        self.assertTrue(sys.dont_write_bytecode)\n"
                    "        self.assertEqual(protected_review_dependency.VALUE, 'collection-imported')\n"
                    "        subprocess.run([sys.executable, '-c', "
                    "'import protected_review_dependency'], check=True, env=os.environ.copy())\n",
                    encoding="utf-8",
                )
                before = inventory(fixture)
                environment = os.environ.copy()
                # No real archive dependency is visible to this synthetic proof.
                environment.pop("PYTHONDONTWRITEBYTECODE", None)
                environment.pop("PYTHONPYCACHEPREFIX", None)
                if inherited_guard is not None:
                    environment["PYTHONDONTWRITEBYTECODE"] = inherited_guard
                environment["INTEGRA_TEST_REVIEW_PYTHONPATH"] = str(archive)
                environment["PYTHONPATH"] = str(ROOT)
                environment["INTEGRA_REVIEW_TEST_PYTHON"] = sys.executable
                result = subprocess.run(
                    ["/bin/bash", str(LAUNCHER), "discover", "-s", str(collected), "-v"],
                    env=environment, text=True, capture_output=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Ran 1 test", result.stderr)
                self.assertNotIn("Error in sitecustomize", result.stderr)
                self.assertEqual(inventory(fixture), before)
                self.assertEqual(list(fixture.rglob("__pycache__")), [])
                self.assertEqual(list(fixture.rglob("*.pyc")), [])


if __name__ == "__main__":
    unittest.main()
