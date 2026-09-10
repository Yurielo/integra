import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from integra_core.adapter import (
    AdapterPreconditionError,
    CapabilitySpec,
    LocalComponentAdapter,
)
from integra_core.identity import derive_imported_id
from integra_core.protocol import CompatibilityError, content_sha256, validate_message


NOW = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.output = self.root / "output"
        self.source.mkdir()
        (self.source / "input.json").write_text('{"fixture":true}', encoding="utf-8")
        (self.source / "probe.py").write_text(
            "import pathlib, sys\n"
            "path = pathlib.Path(sys.argv[1])\n"
            "assert path.read_text(encoding='utf-8') == '{\"fixture\":true}'\n"
            "print('FAKE_PROBE_PASS')\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", self.source], check=True)
        subprocess.run(["git", "-C", self.source, "add", "."], check=True)
        subprocess.run(
            [
                "git", "-C", self.source, "-c", "user.name=Integra Test",
                "-c", "user.email=integra@example.invalid", "commit", "-qm", "fixture",
            ],
            check=True,
        )
        self.commit = self.git("rev-parse", "HEAD")
        self.tree = self.git("rev-parse", "HEAD^{tree}")
        self.identity = {
            "component_id": "seminartext",
            "repository": "Yurielo/seminartext",
            "commit_sha": self.commit,
            "tree_sha": self.tree,
            "version": "test",
            "contracts": ["fixture_v1"],
            "runtime": {"kind": "python", "version": "3.12", "architecture": "test"},
        }
        self.capability = CapabilitySpec(
            id="fixture.validate",
            version="1.0",
            input_schema_ids=("fixture_v1",),
            output_schema_ids=("adapter_probe_report_v1",),
            supports_resume=False,
            command=(sys.executable, "probe.py", "{input0}"),
            success_stdout_marker="FAKE_PROBE_PASS",
        )
        self.adapter = self.make_adapter(self.capability)
        self.handshake = self.make_handshake()
        self.job = self.make_job()

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", self.source, *arguments],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()

    def make_adapter(self, capability: CapabilitySpec) -> LocalComponentAdapter:
        return LocalComponentAdapter(
            identity=self.identity,
            source_root=self.source,
            output_root=self.output,
            capabilities=(capability,),
            clock=lambda: NOW,
        )

    def make_envelope(self, message_type: str, payload: dict, name: str) -> dict:
        correlation = "urn:integra:session:70000000-0000-0000-0000-000000000000"
        digest = content_sha256(payload)
        return {
            "protocol_version": "1.0",
            "message_id": derive_imported_id("message", "integra", name, digest),
            "correlation_id": correlation,
            "sent_at": "2026-09-10T15:00:00Z",
            "type": message_type,
            "payload": payload,
        }

    def make_handshake(self) -> dict:
        controller = {
            "component_id": "integra_control_plane",
            "repository": "Yurielo/integra",
            "commit_sha": "1" * 40,
            "tree_sha": "2" * 40,
            "version": "0.1.0",
            "contracts": ["worker_protocol_v1"],
            "runtime": {"kind": "python", "version": "3.12", "architecture": "test"},
        }
        return self.make_envelope(
            "HANDSHAKE_REQUEST",
            {
                "supported_protocol_versions": ["1.0"],
                "requested_capabilities": [self.capability.id],
                "controller": controller,
            },
            "handshake",
        )

    def make_job(self) -> dict:
        payload = (self.source / "input.json").read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        operation = derive_imported_id("operation", "seminartext", "fixture", digest)
        artifact = {
            "artifact_id": derive_imported_id("artifact", "seminartext", "input", digest),
            "kind": "fixture",
            "schema_id": "fixture_v1",
            "schema_version": "1.0",
            "content_sha256": digest,
            "size_bytes": len(payload),
            "storage_scope": "SOURCE_READ_ONLY",
            "relative_path": "input.json",
            "origin": self.identity,
            "provenance": {"parent_artifact_ids": [], "operation_id": operation},
        }
        return self.make_envelope(
            "JOB_REQUEST",
            {
                "job_id": derive_imported_id("job", "seminartext", "fixture", digest),
                "operation_id": operation,
                "idempotency_key": content_sha256({"fixture": digest}),
                "capability": self.capability.id,
                "timeout_ms": 2000,
                "inputs": [artifact],
            },
            "job",
        )

    def test_handshake_declares_pinned_worker_capability(self):
        response = self.adapter.handshake(self.handshake)
        validate_message(response)
        self.assertEqual(response["payload"]["worker"], self.identity)
        self.assertEqual(response["payload"]["capabilities"][0]["id"], "fixture.validate")

    def test_unknown_handshake_capability_fails_closed(self):
        request = copy.deepcopy(self.handshake)
        request["payload"]["requested_capabilities"] = ["unknown"]
        with self.assertRaises(CompatibilityError):
            self.adapter.handshake(request)

    def test_successful_request_writes_only_hashed_report(self):
        events = self.adapter.invoke(self.job)
        self.assertEqual([item["type"] for item in events], ["PROGRESS", "PROGRESS", "RESULT"])
        artifact = events[-1]["payload"]["outputs"][0]
        report_path = self.output / artifact["relative_path"]
        self.assertTrue(report_path.is_file())
        self.assertEqual(hashlib.sha256(report_path.read_bytes()).hexdigest(), artifact["content_sha256"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["source_before"], report["source_after"])
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")

    def test_hash_mismatch_blocks_before_execution(self):
        request = copy.deepcopy(self.job)
        request["payload"]["inputs"][0]["content_sha256"] = "f" * 64
        with self.assertRaises(AdapterPreconditionError):
            self.adapter.invoke(request)

    def test_dirty_source_blocks_before_execution(self):
        (self.source / "untracked.txt").write_text("dirty", encoding="utf-8")
        with self.assertRaises(AdapterPreconditionError):
            self.adapter.invoke(self.job)

    def test_output_inside_source_is_rejected(self):
        adapter = LocalComponentAdapter(
            identity=self.identity,
            source_root=self.source,
            output_root=self.source / "output",
            capabilities=(self.capability,),
            clock=lambda: NOW,
        )
        with self.assertRaises(AdapterPreconditionError):
            adapter.verify_source()

    def test_cancellation_is_acknowledged(self):
        slow = CapabilitySpec(
            id=self.capability.id,
            version="1.0",
            input_schema_ids=("fixture_v1",),
            output_schema_ids=("adapter_probe_report_v1",),
            supports_resume=False,
            command=(sys.executable, "-c", "import time; time.sleep(5)"),
            success_stdout_marker="never",
        )
        events = self.make_adapter(slow).invoke(self.job, cancel_requested=lambda: True)
        self.assertEqual(events[-1]["type"], "CANCEL_ACK")
        self.assertEqual(events[-1]["payload"]["status"], "CANCELLED")

    def test_timeout_is_unknown_outcome_and_not_retryable(self):
        slow = CapabilitySpec(
            id=self.capability.id,
            version="1.0",
            input_schema_ids=("fixture_v1",),
            output_schema_ids=("adapter_probe_report_v1",),
            supports_resume=False,
            command=(sys.executable, "-c", "import time; time.sleep(5)"),
            success_stdout_marker="never",
        )
        request = copy.deepcopy(self.job)
        request["payload"]["timeout_ms"] = 1
        events = self.make_adapter(slow).invoke(request)
        self.assertEqual(events[-1]["type"], "ERROR")
        self.assertEqual(events[-1]["payload"]["classification"], "UNKNOWN_OUTCOME")
        self.assertFalse(events[-1]["payload"]["safe_to_retry"])

    def test_failed_command_returns_structured_error_without_raw_output(self):
        failing = CapabilitySpec(
            id=self.capability.id,
            version="1.0",
            input_schema_ids=("fixture_v1",),
            output_schema_ids=("adapter_probe_report_v1",),
            supports_resume=False,
            command=(sys.executable, "-c", "import sys; print('private'); sys.exit(3)"),
            success_stdout_marker="never",
        )
        events = self.make_adapter(failing).invoke(self.job)
        error = events[-1]
        self.assertEqual(error["type"], "ERROR")
        self.assertEqual(error["payload"]["classification"], "NON_RETRYABLE")
        self.assertNotIn("private", json.dumps(error))


if __name__ == "__main__":
    unittest.main()
