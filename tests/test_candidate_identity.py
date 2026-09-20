import json
from pathlib import Path
import tempfile
import unittest

from integra_core.candidate_identity import candidate_id, validate_manifest, write_evidence


class CandidateIdentityTests(unittest.TestCase):
    def identity(self):
        return {"source": {"commit_sha": "a" * 40, "tree_sha": "b" * 40, "dirty": False, "dirty_diff_sha256": "c" * 64},
                "build_command": {"path": "scripts/build_macos_app.sh", "identity": "scripts/build_macos_app.sh", "script_sha256": "d" * 64},
                "components": {}, "execution": {}}

    def test_candidate_id_is_deterministic_and_manifest_binds_it(self):
        identity = self.identity()
        candidate = candidate_id(identity)
        self.assertEqual(candidate, candidate_id(dict(identity)))
        manifest = {"schema_version": "1.0", "candidate_id": candidate,
                    "identity_sha256": candidate.removeprefix("candidate-v1-"), "identity": identity,
                    "bundle": {"digest_algorithm": "sha256-tree-excluding-candidate-manifest", "digest": "e" * 64},
                    "build": {"timestamp": "2026-09-20T00:00:00Z", "build_id": "test"}}
        validate_manifest(manifest)
        manifest["candidate_id"] = "candidate-v1-" + "0" * 64
        with self.assertRaisesRegex(ValueError, "does not bind"):
            validate_manifest(manifest)

    def test_evidence_record_binds_candidate_and_locations(self):
        candidate = {"candidate_id": "candidate-v1-" + "a" * 64, "identity_sha256": "a" * 64,
                     "bundle": {"digest": "b" * 64}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate.json"
            value = write_evidence(path, candidate=candidate, gate_name="focused_gate", result="PASS",
                                   timestamp="2026-09-20T00:00:00Z", artifact_locations=["/evidence/log"], details={})
            self.assertEqual(json.loads(path.read_text()), value)
        self.assertEqual(value["candidate_id"], candidate["candidate_id"])
