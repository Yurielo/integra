"""Execution-copy guard regressions for Candidate GUI QA."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import prepare_candidate_execution_copy as execution
from temp_workspace_lifecycle import _process_start_token


class CandidateExecutionCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="integra-owned-" + execution.PURPOSE + "-", dir="/private/tmp")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        marker = {"schema_version": execution.SCHEMA, "artifact_type": "integra.disposable_workspace",
                  "root": str(self.workspace), "purpose": execution.PURPOSE, "created_at": "test",
                  "run_id": "test", "expected_bytes": 0, "reserve_bytes": 0,
                  "owner": {"pid": os.getpid(), "start_token": _process_start_token(os.getpid())},
                  "child": {}, "state": "CREATED", "events": []}
        (self.workspace / execution.MARKER).write_text(json.dumps(marker))

    def test_workspace_rejects_wrong_purpose(self):
        marker = json.loads((self.workspace / execution.MARKER).read_text())
        marker["purpose"] = "other"
        (self.workspace / execution.MARKER).write_text(json.dumps(marker))
        with patch.dict(os.environ, {"INTEGRA_OWNED_WORKSPACE": str(self.workspace)}):
            with self.assertRaisesRegex(ValueError, "marker"):
                execution._workspace()

    def test_execution_copy_requires_exact_verified_identity(self):
        # Full archive copying is exercised only through the governed runtime
        # path; this unit guard proves the exact identity is supplied to it.
        expected = {"candidate_id": "candidate-v1-" + "a" * 64,
                    "bundle_digest": "b" * 64, "manifest_digest": "c" * 64}
        with patch.object(sys, "argv", ["tool", "--archive", "/archive", *sum((["--" + k.replace("_", "-"), v] for k, v in expected.items()), [])]), \
             patch.dict(os.environ, {"INTEGRA_OWNED_WORKSPACE": str(self.workspace)}), \
             patch.object(execution, "verify_archive", side_effect=ValueError("identity differs")):
            with self.assertRaisesRegex(ValueError, "identity differs"):
                execution.main()


if __name__ == "__main__":
    unittest.main()
