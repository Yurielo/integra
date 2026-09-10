import tempfile
import unittest
from pathlib import Path

from integra_core.project_lease import (
    LeaseConflict,
    LeaseStore,
    RecoveryDecision,
    RecoveryObservation,
    recovery_decision,
)


PROJECT = "urn:integra:project:11111111-1111-1111-1111-111111111111"
ENTITY = "urn:integra:artifact:22222222-2222-2222-2222-222222222222"
WRITER = {
    "component_id": "integra.test",
    "host_id": "host-1",
    "process_id": 42,
    "process_start_token": "process-start-1",
}


def lease_payload(lease_id="urn:integra:lease:33333333-3333-3333-3333-333333333333"):
    return {
        "schema_version": "1.0",
        "lease_id": lease_id,
        "project_id": PROJECT,
        "mutable_entity": {"namespace": "artifact", "entity_id": ENTITY},
        "writer": WRITER,
        "operation_id": "urn:integra:operation:44444444-4444-4444-4444-444444444444",
        "acquired_at": "2026-09-10T10:00:00Z",
        "heartbeat_at": "2026-09-10T10:00:00Z",
        "expires_at": "2026-09-10T10:05:00Z",
        "artifact_precondition": {"revision_id": "revision-1", "content_sha256": "a" * 64},
        "readers": ["integra.ui"],
        "generation": 1,
        "state": "ACTIVE",
    }


class ProjectLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = LeaseStore(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_single_writer_conflict(self):
        acquired = self.store.acquire(lease_payload())
        self.assertEqual(acquired["generation"], 1)
        with self.assertRaises(LeaseConflict):
            self.store.acquire(lease_payload("urn:integra:lease:55555555-5555-5555-5555-555555555555"))

    def test_wrong_writer_cannot_heartbeat(self):
        acquired = self.store.acquire(lease_payload())
        wrong_writer = dict(WRITER, process_id=43)
        with self.assertRaises(LeaseConflict):
            self.store.heartbeat(
                PROJECT, ENTITY, acquired["lease_id"], wrong_writer, 1,
                "2026-09-10T10:01:00Z", "2026-09-10T10:06:00Z"
            )

    def test_expired_lease_cannot_be_revived_by_late_heartbeat(self):
        acquired = self.store.acquire(lease_payload())
        with self.assertRaises(LeaseConflict):
            self.store.heartbeat(
                PROJECT, ENTITY, acquired["lease_id"], WRITER, 1,
                "2026-09-10T10:05:00Z", "2026-09-10T10:10:00Z"
            )

    def test_release_then_reacquire_increments_generation(self):
        acquired = self.store.acquire(lease_payload())
        released = self.store.release(PROJECT, ENTITY, acquired["lease_id"], WRITER, 1, "2026-09-10T10:02:00Z")
        self.assertEqual(released["release_reason"], "WRITER_RELEASE")
        replacement = lease_payload("urn:integra:lease:55555555-5555-5555-5555-555555555555")
        replacement["acquired_at"] = "2026-09-10T10:03:00Z"
        replacement["heartbeat_at"] = "2026-09-10T10:03:00Z"
        replacement["expires_at"] = "2026-09-10T10:08:00Z"
        self.assertEqual(self.store.acquire(replacement)["generation"], 2)

    def test_expiry_alone_never_recovers(self):
        lease = self.store.acquire(lease_payload())
        decision = recovery_decision(
            lease,
            "2026-09-10T10:06:00Z",
            RecoveryObservation("UNKNOWN", "UNCHANGED"),
        )
        self.assertEqual(decision, RecoveryDecision.DENY_UNVERIFIED_PROCESS)

    def test_successful_heartbeat_updates_active_lease(self):
        acquired = self.store.acquire(lease_payload())
        updated = self.store.heartbeat(
            PROJECT, ENTITY, acquired["lease_id"], WRITER, 1,
            "2026-09-10T10:04:00Z", "2026-09-10T10:09:00Z"
        )
        self.assertEqual(updated["heartbeat_at"], "2026-09-10T10:04:00Z")
        self.assertEqual(updated["state"], "ACTIVE")

    def test_mismatched_entity_namespace_is_rejected(self):
        payload = lease_payload()
        payload["mutable_entity"]["namespace"] = "topic"
        with self.assertRaises(LeaseConflict):
            self.store.acquire(payload)

    def test_live_process_or_changed_artifact_denies_recovery(self):
        lease = self.store.acquire(lease_payload())
        now = "2026-09-10T10:06:00Z"
        self.assertEqual(
            recovery_decision(lease, now, RecoveryObservation("ALIVE", "UNCHANGED")),
            RecoveryDecision.DENY_PROCESS_ALIVE,
        )
        self.assertEqual(
            recovery_decision(lease, now, RecoveryObservation("NOT_RUNNING", "CHANGED")),
            RecoveryDecision.DENY_ARTIFACT_CHANGED,
        )

    def test_verified_stale_recovery_retains_record(self):
        self.store.acquire(lease_payload())
        decision, recovered = self.store.recover_stale(
            PROJECT,
            ENTITY,
            "2026-09-10T10:06:00Z",
            RecoveryObservation("NOT_RUNNING", "UNCHANGED"),
        )
        self.assertEqual(decision, RecoveryDecision.ALLOW_RECOVERY)
        self.assertEqual(recovered["state"], "RELEASED")
        self.assertEqual(recovered["release_reason"], "VERIFIED_STALE_RECOVERY")
        self.assertIsNotNone(self.store.read(PROJECT, ENTITY))


if __name__ == "__main__":
    unittest.main()
