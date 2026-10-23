"""Exercise the bundle's Knowledge View validator without source-tree fallback.

Synthetic provenance fixtures verify packaging mechanics, not semantic acceptance.
Run with --app after a native build to test the actual application resources.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_knowledge import CREATED, _evidence, _knowledge, _source_evidence


def fixture_payload():
    evidence = json.dumps(_evidence(), sort_keys=True)
    source = _source_evidence(json.loads(evidence))
    source["canonical_evidence"]["sha256"] = hashlib.sha256(evidence.encode()).hexdigest()
    source = json.dumps(source, sort_keys=True)
    knowledge = _knowledge(json.loads(evidence), hashlib.sha256(evidence.encode()).hexdigest(),
                           json.loads(source), hashlib.sha256(source.encode()).hexdigest())
    return dict(evidence=evidence, source=source, knowledge=json.dumps(knowledge, sort_keys=True))


PROBE = r'''
import json
from pathlib import Path
import sys
resources = Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(resources))
from integra_core import knowledge
assert Path(knowledge.__file__).resolve().is_relative_to(resources)
payload = json.load(sys.stdin)
args = [payload[name].encode() for name in ("evidence", "source", "knowledge")]
view = knowledge.build_knowledge_view(*args, created_at=sys.argv[2])
encoded = knowledge.dumps_knowledge_view(view, *args)
reopened = knowledge.loads_knowledge_view(encoded, *args)
assert reopened == view
assert view["records"]["concepts"][0]["status"] == "PROVISIONAL"
assert view["evidence"][0]["quote"] == "source term"
assert view["source_artifacts_modified"] is False
print(json.dumps({"module": knowledge.__file__, "view_id": view["view_id"],
                  "roundtrip": True, "semantic_acceptance": False}))
'''


def probe(resources):
    """The GUI interpreter loads only packaged core/schema, with isolated imports."""
    python = "/usr/bin/python3" if sys.platform == "darwin" else sys.executable
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("INTEGRA_") and key not in {"PYTHONPATH", "PYTHONHOME"}}
    with tempfile.TemporaryDirectory() as unrelated_cwd:
        return subprocess.run([python, "-I", "-B", "-c", PROBE, str(resources), CREATED],
                              input=json.dumps(fixture_payload()), text=True, capture_output=True,
                              cwd=unrelated_cwd, env=environment, timeout=30)


class PackagedKnowledgeViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.resources = Path(self.temp.name) / "Integra.app/Contents/Resources"
        shutil.copytree(ROOT / "integra_core", self.resources / "integra_core",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (self.resources / "schemas").mkdir()

    def install_schema(self):
        target = self.resources / "schemas/knowledge_view_v1.schema.json"
        shutil.copyfile(ROOT / "schemas/knowledge_view_v1.schema.json", target)
        return target

    def test_missing_bundle_schema_reproduces_failure_without_source_fallback(self):
        result = probe(self.resources)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FileNotFoundError", result.stderr)
        self.assertIn("knowledge_view_v1.schema.json", result.stderr)

    def test_bundled_schema_builds_and_reopens_real_knowledge_view(self):
        self.install_schema()
        result = probe(self.resources)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt["roundtrip"])
        self.assertFalse(receipt["semantic_acceptance"])
        self.assertEqual(Path(receipt["module"]).resolve(),
                         (self.resources / "integra_core/knowledge.py").resolve())

    def test_schema_is_executed_not_merely_present(self):
        target = self.install_schema()
        schema = json.loads(target.read_bytes())
        schema["required"].append("missing_packaged_regression_field")
        target.write_text(json.dumps(schema))
        result = probe(self.resources)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("knowledge view schema differs", result.stderr)


if __name__ == "__main__":
    if "--app" in sys.argv:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--app", type=Path, required=True)
        args = parser.parse_args()
        result = probe(args.app.resolve(strict=True) / "Contents/Resources")
        if result.returncode:
            raise SystemExit(result.stderr)
        print(result.stdout.strip())
        print("INTEGRA_PACKAGED_KNOWLEDGE_VIEW: PASS")
    else:
        unittest.main()
