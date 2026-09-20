import copy
import json
import unittest
from pathlib import Path

from integra_core.protocol import (
    CompatibilityError,
    IdempotencyDecision,
    IdempotencyLedger,
    ProgressTracker,
    ProtocolViolation,
    negotiate_protocol,
    resume_binding,
    validate_artifact_reference,
    validate_message,
    validate_resume_binding,
    validate_resume_token,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "worker_protocol_v1"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class WorkerProtocolFixtureTests(unittest.TestCase):
    def test_success_fixture_validates_and_reaches_terminal_state(self):
        fixture = load_fixture("success")
        tracker = ProgressTracker()
        for message in fixture["messages"]:
            validate_message(message)
            if message["type"] in {"PROGRESS", "RESULT"}:
                tracker.apply(message)
        self.assertTrue(tracker.terminal)
        self.assertEqual(tracker.fraction, 0.5)

    def test_cancellation_fixture_is_acknowledged_and_terminal(self):
        fixture = load_fixture("cancellation")
        tracker = ProgressTracker()
        for message in fixture["messages"]:
            validate_message(message)
            tracker.apply(message)
        self.assertTrue(tracker.terminal)

    def test_retry_fixture_is_explicitly_safe(self):
        message = load_fixture("retry")["messages"][0]
        validate_message(message)
        self.assertEqual(message["payload"]["classification"], "RETRYABLE")
        self.assertTrue(message["payload"]["safe_to_retry"])

    def test_incompatibility_fixture_fails_closed(self):
        fixture = load_fixture("incompatibility")
        with self.assertRaises(CompatibilityError):
            negotiate_protocol(fixture["controller_versions"], fixture["worker_versions"])

    def test_provenance_fixture_keeps_two_parents(self):
        artifact = load_fixture("provenance")["artifact"]
        validate_artifact_reference(artifact)
        self.assertEqual(len(artifact["provenance"]["parent_artifact_ids"]), 2)


class WorkerProtocolSafetyTests(unittest.TestCase):
    def setUp(self):
        self.success = load_fixture("success")
        self.job = copy.deepcopy(self.success["messages"][2])
        self.progress = copy.deepcopy(self.success["messages"][3])

    def test_negotiation_selects_highest_exact_version(self):
        self.assertEqual(negotiate_protocol(["1.0", "1.1"], ["1.0", "1.1"]), "1.1")

    def test_malformed_protocol_version_fails_closed(self):
        with self.assertRaises(CompatibilityError):
            negotiate_protocol(["1.0"], ["v1", "1.0"])

    def test_idempotency_replays_same_request(self):
        ledger = IdempotencyLedger()
        key = self.job["payload"]["idempotency_key"]
        payload = self.job["payload"]
        self.assertEqual(ledger.register(key, payload), IdempotencyDecision.NEW)
        self.assertEqual(ledger.register(key, copy.deepcopy(payload)), IdempotencyDecision.REPLAY)

    def test_idempotency_rejects_same_key_for_changed_request(self):
        ledger = IdempotencyLedger()
        key = self.job["payload"]["idempotency_key"]
        ledger.register(key, self.job["payload"])
        changed = copy.deepcopy(self.job["payload"])
        changed["timeout_ms"] += 1
        with self.assertRaises(ProtocolViolation):
            ledger.register(key, changed)

    def test_progress_must_be_monotonic(self):
        tracker = ProgressTracker()
        tracker.apply(self.progress)
        regressing = copy.deepcopy(self.progress)
        regressing["message_id"] = "urn:integra:message:90000000-0000-0000-0000-000000000001"
        regressing["payload"]["sequence"] = 2
        regressing["payload"]["fraction"] = 0.4
        with self.assertRaises(ProtocolViolation):
            tracker.apply(regressing)

    def test_post_terminal_event_is_rejected(self):
        tracker = ProgressTracker()
        tracker.apply(self.success["messages"][-1])
        with self.assertRaises(ProtocolViolation):
            tracker.apply(self.progress)

    def test_event_from_different_job_is_rejected(self):
        tracker = ProgressTracker()
        tracker.apply(self.progress)
        other = copy.deepcopy(self.progress)
        other["message_id"] = "urn:integra:message:90000000-0000-0000-0000-000000000004"
        other["payload"]["job_id"] = "urn:integra:job:90000000-0000-0000-0000-000000000005"
        other["payload"]["sequence"] = 2
        with self.assertRaises(ProtocolViolation):
            tracker.apply(other)

    def test_path_traversal_is_rejected(self):
        artifact = copy.deepcopy(self.job["payload"]["inputs"][0])
        artifact["relative_path"] = "../source.json"
        with self.assertRaises(ProtocolViolation):
            validate_artifact_reference(artifact)

    def test_non_normalized_path_is_rejected(self):
        artifact = copy.deepcopy(self.job["payload"]["inputs"][0])
        artifact["relative_path"] = "source//input.json"
        with self.assertRaises(ProtocolViolation):
            validate_artifact_reference(artifact)

    def test_mutable_job_requires_project_lease(self):
        self.job["payload"]["mutable_entity"] = (
            "urn:integra:artifact:90000000-0000-0000-0000-000000000002"
        )
        with self.assertRaises(ProtocolViolation):
            validate_message(self.job)

    def test_valid_project_lease_allows_mutable_job_contract(self):
        self.job["payload"]["mutable_entity"] = (
            "urn:integra:artifact:90000000-0000-0000-0000-000000000002"
        )
        self.job["payload"]["write_lease"] = {
            "lease_id": "urn:integra:lease:90000000-0000-0000-0000-000000000003",
            "generation": 2,
            "artifact_precondition_sha256": "d" * 64,
        }
        validate_message(self.job)

    def test_unknown_outcome_cannot_be_marked_retryable(self):
        message = copy.deepcopy(load_fixture("retry")["messages"][0])
        message["payload"]["classification"] = "UNKNOWN_OUTCOME"
        with self.assertRaises(ProtocolViolation):
            validate_message(message)

    def test_resume_binding_is_deterministic_and_input_sensitive(self):
        job_id = self.job["payload"]["job_id"]
        commit = "970bde598ddd649599295139986933e0e06cb9c0"
        first = resume_binding(job_id, "canonical_evidence.validate", commit, ["b" * 64])
        second = resume_binding(job_id, "canonical_evidence.validate", commit, ["b" * 64])
        changed = resume_binding(job_id, "canonical_evidence.validate", commit, ["c" * 64])
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

    def test_resume_token_expiry_must_follow_issue_time(self):
        with self.assertRaises(ProtocolViolation):
            validate_resume_token(
                {
                    "token": "opaque-token",
                    "binding_sha256": "e" * 64,
                    "issued_at": "2026-09-10T14:00:00Z",
                    "expires_at": "2026-09-10T13:59:59Z",
                }
            )

    def test_resume_token_must_match_current_job_facts(self):
        job_id = self.job["payload"]["job_id"]
        commit = "970bde598ddd649599295139986933e0e06cb9c0"
        token = {
            "token": "opaque-token",
            "binding_sha256": resume_binding(
                job_id, "canonical_evidence.validate", commit, ["b" * 64]
            ),
            "issued_at": "2026-09-10T14:00:00Z",
            "expires_at": "2026-09-10T15:00:00Z",
        }
        validate_resume_binding(
            token, job_id, "canonical_evidence.validate", commit, ["b" * 64]
        )
        with self.assertRaises(ProtocolViolation):
            validate_resume_binding(
                token, job_id, "canonical_evidence.validate", commit, ["c" * 64]
            )


if __name__ == "__main__":
    unittest.main()
