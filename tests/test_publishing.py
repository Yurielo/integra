import copy
import fcntl
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from integra_core.protocol import content_sha256
from integra_core.project_lease import LeaseStore
from integra_core.publishing import (
    COMPLETE, CURRENT, MANIFEST, PublishingError, _record_hash, _target_lock,
    build_obsidian_package, preview_obsidian_export, publish_obsidian_export,
    recover_obsidian_export, validate_source_export,
)


H = "1" * 64
PROJECT = "urn:integra:project:11111111-1111-1111-1111-111111111111"
AT = "2026-09-11T10:01:00Z"


def fixtures():
    files = {"00_START_HERE.md": b"# Start\n", "Topics/topic.md": b"# Topic\n"}
    source = {
        "schema_version": 1, "artifact_type": "seminartext.managed_generated_export",
        "kind": "obsidian_derived_view", "ownership_classes": ["MANAGED_GENERATED", "USER_OWNED"],
        "files": {name: hashlib.sha256(value).hexdigest() for name, value in files.items()},
        "canonical_evidence_artifact_id": "artifact:evidence",
        "canonical_evidence_sha256": "2" * 64,
        "canonical_knowledge_artifact_id": "artifact:knowledge",
        "canonical_knowledge_sha256": "3" * 64,
        "coverage": {"full_seminar_coverage": True}, "resolver_states": {"source:one": "AVAILABLE"},
    }
    knowledge = {
        "view_id": "urn:integra:artifact:22222222-2222-2222-2222-222222222222",
        "source_binding": {"canonical_evidence_id": "artifact:evidence", "canonical_evidence_sha256": "2" * 64,
                           "canonical_knowledge_id": "artifact:knowledge", "canonical_knowledge_sha256": "3" * 64},
        "record_sha256": "",
    }
    knowledge["record_sha256"] = _record_hash(knowledge)
    navigation = {
        "navigation_id": "urn:integra:artifact:33333333-3333-3333-3333-333333333333",
        "project_id": PROJECT,
        "sources": {"knowledge": {"record_id": knowledge["view_id"], "record_sha256": knowledge["record_sha256"]}},
        "targets": [{"target_id": "evidence:one", "target_sha256": H, "available": True,
                     "actions": ["SEEK_MEDIA"], "locators": [{"type": "TIME_INTERVAL", "start_seconds": 1, "end_seconds": 2}], "unavailable_reason": None}],
        "record_sha256": "",
    }
    navigation["record_sha256"] = _record_hash(navigation)
    manifest, packaged = build_obsidian_package(
        project_id=PROJECT, project_slug="course", source_files=files,
        source_manifest=source, knowledge_view=knowledge, navigation=navigation,
        created_at="2026-09-11T10:00:00Z",
    )
    return files, source, knowledge, navigation, manifest, packaged


def authorization(root: Path, manifest: dict):
    store = LeaseStore(root / "leases")
    lease = store.acquire({
        "schema_version": "1.0", "lease_id": "urn:integra:lease:44444444-4444-4444-4444-444444444444",
        "project_id": PROJECT, "mutable_entity": {"namespace": "artifact", "entity_id": manifest["package_id"]},
        "writer": {"component_id": "integra.obsidian_exporter", "host_id": "test-host", "process_id": 42, "process_start_token": "test-process"},
        "operation_id": "urn:integra:operation:55555555-5555-5555-5555-555555555555",
        "acquired_at": "2026-09-11T10:00:00Z", "heartbeat_at": "2026-09-11T10:00:00Z",
        "expires_at": "2026-09-11T10:05:00Z",
        "artifact_precondition": {"revision_id": manifest["package_id"], "content_sha256": manifest["version_sha256"]},
        "readers": ["integra.ui"], "generation": 1, "state": "ACTIVE",
    })
    return {"lease": lease, "lease_store": store, "operation_at": AT}


class PublishingTests(unittest.TestCase):
    def test_package_is_deterministic_and_bound_to_navigation(self):
        *_, first, files = fixtures()
        *_, second, second_files = fixtures()
        self.assertEqual(first, second)
        self.assertEqual(files, second_files)
        metadata = json.loads(files["_meta/integra_navigation.json"])
        self.assertEqual(metadata["navigation_sha256"], first["navigation"]["record_sha256"])

    def test_source_export_hash_and_unsafe_path_fail(self):
        files, source, *_ = fixtures()
        broken = dict(files); broken["00_START_HERE.md"] = b"changed"
        with self.assertRaisesRegex(PublishingError, "hash differs"):
            validate_source_export(broken, source)
        unsafe = copy.deepcopy(source); unsafe["files"]["../outside"] = H
        with self.assertRaises(PublishingError):
            validate_source_export({**files, "../outside": b"x"}, unsafe)

    def test_preview_writes_nothing_and_publish_replays(self):
        *_, manifest, files = fixtures()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); vault = root / "vault"; vault.mkdir(); auth = authorization(root, manifest)
            before = list(vault.iterdir())
            self.assertEqual(preview_obsidian_export(vault, manifest, files)["state"], "DRY_RUN")
            self.assertEqual(list(vault.iterdir()), before)
            first = publish_obsidian_export(vault, manifest, files, **auth)
            self.assertEqual(first["state"], "EXPORTED")
            version = vault / "Integra/course/versions" / manifest["version_sha256"]
            self.assertTrue((version / COMPLETE).is_file())
            self.assertTrue((version / MANIFEST).is_file())
            self.assertTrue((vault / "Integra/course" / CURRENT).is_file())
            self.assertEqual(publish_obsidian_export(vault, manifest, files, **auth)["state"], "UNCHANGED")

    def test_user_content_and_changed_managed_version_are_protected(self):
        *_, manifest, files = fixtures()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); vault = root / "vault"; vault.mkdir(); auth = authorization(root, manifest)
            user = vault / "personal.md"; user.write_text("mine")
            publish_obsidian_export(vault, manifest, files, **auth)
            self.assertEqual(user.read_text(), "mine")
            version = vault / "Integra/course/versions" / manifest["version_sha256"]
            (version / "Topics/topic.md").write_text("edited")
            with self.assertRaisesRegex(PublishingError, "collision"):
                publish_obsidian_export(vault, manifest, files, **auth)
            self.assertEqual(user.read_text(), "mine")

    def test_unknown_managed_root_content_and_symlink_fail(self):
        *_, manifest, files = fixtures()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); vault = base / "vault"; vault.mkdir(); auth = authorization(base, manifest)
            managed = vault / "Integra/course"; managed.mkdir(parents=True)
            (managed / "notes.md").write_text("mine")
            with self.assertRaisesRegex(PublishingError, "collision"):
                publish_obsidian_export(vault, manifest, files, **auth)
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            base = Path(directory); vault = base / "vault"; vault.mkdir(); auth = authorization(base, manifest)
            (vault / "Integra").mkdir(); (vault / "Integra/course").symlink_to(outside)
            with self.assertRaisesRegex(PublishingError, "symlink"):
                publish_obsidian_export(vault, manifest, files, **auth)

    def test_interruption_is_recovered_without_promotion(self):
        *_, manifest, files = fixtures()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); vault = root / "vault"; vault.mkdir(); auth = authorization(root, manifest)
            with self.assertRaisesRegex(PublishingError, "injected"):
                publish_obsidian_export(vault, manifest, files, interrupt_after="VERIFIED", **auth)
            self.assertFalse((vault / "Integra/course" / CURRENT).exists())
            result = recover_obsidian_export(vault, manifest, files, **auth)
            self.assertEqual(result["state"], "EXPORTED")

    def test_target_lock_is_nonblocking_and_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "target.lock"
            with _target_lock(path):
                with self.assertRaisesRegex(PublishingError, "locked"):
                    with _target_lock(path):
                        pass

    def test_wrong_or_expired_project_lease_blocks_before_write(self):
        *_, manifest, files = fixtures()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); vault = root / "vault"; vault.mkdir(); auth = authorization(root, manifest)
            wrong = copy.deepcopy(auth["lease"])
            wrong["writer"]["component_id"] = "integra.onedrive_publisher"
            with self.assertRaisesRegex(PublishingError, "lease"):
                publish_obsidian_export(vault, manifest, files, lease=wrong,
                    lease_store=auth["lease_store"], operation_at=AT)
            with self.assertRaisesRegex(PublishingError, "lease"):
                publish_obsidian_export(vault, manifest, files, lease=auth["lease"],
                    lease_store=auth["lease_store"], operation_at="2026-09-11T10:06:00Z")
            self.assertEqual(list(vault.iterdir()), [])

    def test_resigned_binding_tampering_fails(self):
        files, source, knowledge, navigation, *_ = fixtures()
        navigation["sources"]["knowledge"]["record_sha256"] = H
        navigation["record_sha256"] = _record_hash(navigation)
        with self.assertRaisesRegex(PublishingError, "does not bind"):
            build_obsidian_package(project_id=PROJECT, project_slug="course", source_files=files,
                source_manifest=source, knowledge_view=knowledge, navigation=navigation,
                created_at="2026-09-11T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
