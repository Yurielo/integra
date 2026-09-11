import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from integra_core.onedrive import (
    build_onedrive_package, preview_onedrive_publication, publish_onedrive_package,
    recover_onedrive_publication, validate_onedrive_package,
)
from integra_core.project_lease import LeaseStore
from integra_core.publishing import COMPLETE, CURRENT, MANIFEST, PublishingError, _target_lock
from tests.test_publishing import PROJECT, fixtures as obsidian_fixtures


def package(created_at="2026-09-11T11:00:00Z"):
    *_, source_manifest, files = obsidian_fixtures()
    manifest, payloads = build_onedrive_package(source_manifest, files, created_at=created_at)
    return manifest, payloads


def authorization(root: Path, manifest: dict):
    root.mkdir(parents=True, exist_ok=True)
    store = LeaseStore(root / "leases")
    lease = store.acquire({
        "schema_version": "1.0", "lease_id": "urn:integra:lease:66666666-6666-6666-6666-666666666666",
        "project_id": PROJECT, "mutable_entity": {"namespace": "artifact", "entity_id": manifest["package_id"]},
        "writer": {"component_id": "integra.onedrive_publisher", "host_id": "test-host", "process_id": 43, "process_start_token": "test-process"},
        "operation_id": "urn:integra:operation:77777777-7777-7777-7777-777777777777",
        "acquired_at": "2026-09-11T11:00:00Z", "heartbeat_at": "2026-09-11T11:00:00Z",
        "expires_at": "2026-09-11T11:05:00Z",
        "artifact_precondition": {"revision_id": manifest["package_id"], "content_sha256": manifest["version_sha256"]},
        "readers": ["integra.ui"], "generation": 1, "state": "ACTIVE",
    })
    return {"lease": lease, "lease_store": store,
            "clock": lambda: datetime(2026, 9, 11, 11, 1, tzinfo=timezone.utc)}


class OneDrivePublicationTests(unittest.TestCase):
    def test_package_is_deterministic_and_exactly_bound_to_obsidian(self):
        first, files = package(); second, second_files = package()
        self.assertEqual(first, second); self.assertEqual(files, second_files)
        *_, obsidian_manifest, _ = obsidian_fixtures()
        self.assertEqual(first["source_package"], {
            "package_id": obsidian_manifest["package_id"],
            "version_sha256": obsidian_manifest["version_sha256"],
        })
        changed = copy.deepcopy(first); changed["source_artifacts_modified"] = True
        with self.assertRaises(PublishingError):
            validate_onedrive_package(changed, files)

    def test_preview_is_read_only_for_available_and_unavailable_targets(self):
        manifest, files = package()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); workspace = base / "workspace"; workspace.mkdir()
            missing = base / "missing-sync"
            result = preview_onedrive_publication(missing, workspace, manifest, files)
            self.assertEqual(result["state"], "DRY_RUN_UNAVAILABLE")
            self.assertEqual(list(workspace.iterdir()), [])
            sync = base / "sync"; sync.mkdir()
            self.assertEqual(preview_onedrive_publication(sync, workspace, manifest, files)["state"], "DRY_RUN_AVAILABLE")
            self.assertEqual(list(sync.iterdir()), [])

    def test_unavailable_target_queues_outside_sync_then_publishes(self):
        manifest, files = package()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); workspace = base / "workspace"; workspace.mkdir(); sync = base / "sync"
            auth = authorization(base / "auth", manifest)
            result = publish_onedrive_package(sync, workspace, manifest, files, **auth)
            self.assertEqual(result["state"], "QUEUED_TARGET_UNAVAILABLE")
            self.assertFalse(result["cloud_verified"])
            queue = workspace / "onedrive-queue" / (manifest["version_sha256"] + ".json")
            stage = workspace / "onedrive-staging/course" / (manifest["version_sha256"] + ".stage")
            self.assertTrue(queue.is_file()); self.assertTrue((stage / COMPLETE).is_file())
            self.assertFalse(sync.exists())
            sync.mkdir()
            result = publish_onedrive_package(sync, workspace, manifest, files, **auth)
            self.assertEqual(result["state"], "LOCALLY_PUBLISHED")
            self.assertFalse(result["cloud_verified"]); self.assertFalse(queue.exists())

    def test_complete_is_last_and_partial_recovery_is_verified(self):
        manifest, files = package()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); workspace = base / "workspace"; workspace.mkdir(); sync = base / "sync"; sync.mkdir()
            auth = authorization(base / "auth", manifest)
            with self.assertRaisesRegex(PublishingError, "verification"):
                publish_onedrive_package(sync, workspace, manifest, files, interrupt_after="VERIFIED", **auth)
            version = sync / "Integra/course/versions" / manifest["version_sha256"]
            self.assertTrue((version / MANIFEST).is_file()); self.assertFalse((version / COMPLETE).exists())
            result = recover_onedrive_publication(sync, workspace, manifest, files, **auth)
            self.assertEqual(result["state"], "LOCALLY_PUBLISHED")
            self.assertTrue((version / COMPLETE).is_file())
            self.assertFalse(json.loads((sync / "Integra/course" / CURRENT).read_bytes())["cloud_verified"])
            self.assertEqual(publish_onedrive_package(sync, workspace, manifest, files, **auth)["state"], "UNCHANGED")

    def test_recovery_rejects_tampered_partial_without_overwrite(self):
        manifest, files = package()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); workspace = base / "workspace"; workspace.mkdir(); sync = base / "sync"; sync.mkdir()
            auth = authorization(base / "auth", manifest)
            with self.assertRaises(PublishingError):
                publish_onedrive_package(sync, workspace, manifest, files, interrupt_after="FILES", **auth)
            version = sync / "Integra/course/versions" / manifest["version_sha256"]
            changed = version / "00_START_HERE.md"; changed.write_bytes(b"user or conflict bytes")
            with self.assertRaisesRegex(PublishingError, "differs"):
                recover_onedrive_publication(sync, workspace, manifest, files, **auth)
            self.assertEqual(changed.read_bytes(), b"user or conflict bytes")

    def test_placeholder_and_conflict_copy_fail_closed(self):
        manifest, files = package()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); workspace = base / "workspace"; workspace.mkdir(); sync = base / "sync"; sync.mkdir()
            auth = authorization(base / "auth", manifest)
            detector = lambda path: path.name == "00_START_HERE.md"
            with self.assertRaisesRegex(PublishingError, "physical verification"):
                publish_onedrive_package(sync, workspace, manifest, files,
                                         placeholder_detector=detector, **auth)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); workspace = base / "workspace"; workspace.mkdir(); sync = base / "sync"; sync.mkdir()
            auth = authorization(base / "auth", manifest)
            managed = sync / "Integra/course"; managed.mkdir(parents=True)
            conflict = managed / "topic conflicted copy.md"; conflict.write_text("remote")
            with self.assertRaisesRegex(PublishingError, "collision"):
                publish_onedrive_package(sync, workspace, manifest, files, **auth)
            self.assertEqual(conflict.read_text(), "remote")

    def test_shared_lock_blocks_onedrive_for_overlapping_obsidian_target(self):
        manifest, files = package()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); workspace = base / "workspace"; workspace.mkdir(); sync = base / "sync"; sync.mkdir()
            auth = authorization(base / "auth", manifest)
            target = sync / "Integra/course"; target.mkdir(parents=True)
            with _target_lock(target / ".export.lock"):
                with self.assertRaisesRegex(PublishingError, "locked"):
                    publish_onedrive_package(sync, workspace, manifest, files, **auth)

    def test_complete_without_current_is_repaired_only_after_verification(self):
        manifest, files = package()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); workspace = base / "workspace"; workspace.mkdir(); sync = base / "sync"; sync.mkdir()
            auth = authorization(base / "auth", manifest)
            with self.assertRaisesRegex(PublishingError, "completion"):
                publish_onedrive_package(sync, workspace, manifest, files, interrupt_after="COMPLETE", **auth)
            current = sync / "Integra/course" / CURRENT
            self.assertFalse(current.exists())
            self.assertEqual(recover_onedrive_publication(sync, workspace, manifest, files, **auth)["state"], "LOCALLY_PUBLISHED")
            current.unlink()
            version = sync / "Integra/course/versions" / manifest["version_sha256"]
            changed = version / "00_START_HERE.md"; changed.write_bytes(b"tampered")
            with self.assertRaises(PublishingError):
                recover_onedrive_publication(sync, workspace, manifest, files, **auth)
            self.assertFalse(current.exists())

    def test_symlink_roots_workspace_overlap_and_expired_lease_fail(self):
        manifest, files = package()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); workspace = base / "workspace"; workspace.mkdir(); actual = base / "actual"; actual.mkdir()
            sync = base / "sync"; sync.symlink_to(actual); auth = authorization(base / "auth", manifest)
            with self.assertRaisesRegex(PublishingError, "symlink"):
                publish_onedrive_package(sync, workspace, manifest, files, **auth)
            with self.assertRaisesRegex(PublishingError, "outside"):
                preview_onedrive_publication(actual, actual, manifest, files)
            with self.assertRaisesRegex(PublishingError, "lease"):
                publish_onedrive_package(base / "missing", workspace, manifest, files,
                    lease=auth["lease"], lease_store=auth["lease_store"],
                    clock=lambda: datetime(2026, 9, 11, 11, 6, tzinfo=timezone.utc))
            self.assertEqual(list(workspace.iterdir()), [])

    def test_workspace_symlink_and_corrupt_current_version_fail_closed(self):
        manifest, files = package()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); workspace = base / "workspace"; workspace.mkdir(); sync = base / "sync"; sync.mkdir()
            auth = authorization(base / "auth", manifest)
            outside = base / "outside"; outside.mkdir()
            (workspace / "onedrive-staging").symlink_to(outside)
            with self.assertRaisesRegex(PublishingError, "workspace contains a symlink"):
                publish_onedrive_package(sync, workspace, manifest, files, **auth)
            self.assertEqual(list(outside.iterdir()), [])
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); workspace = base / "workspace"; workspace.mkdir(); sync = base / "sync"; sync.mkdir()
            auth = authorization(base / "auth", manifest)
            publish_onedrive_package(sync, workspace, manifest, files, **auth)
            version = sync / "Integra/course/versions" / manifest["version_sha256"]
            changed = version / "00_START_HERE.md"; changed.write_bytes(b"remote-corruption")
            preview = preview_onedrive_publication(sync, workspace, manifest, files)
            self.assertTrue(preview["collisions"])
            with self.assertRaisesRegex(PublishingError, "collision"):
                publish_onedrive_package(sync, workspace, manifest, files, **auth)
            self.assertEqual(changed.read_bytes(), b"remote-corruption")


if __name__ == "__main__":
    unittest.main()
