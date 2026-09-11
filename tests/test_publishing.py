import copy
import fcntl
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone

from integra_core.protocol import content_sha256
from integra_core.project_lease import LeaseStore
from integra_core.publishing import (
    COMPLETE, CURRENT, MANIFEST, PublishingError, _record_hash, _target_lock,
    build_obsidian_package, preview_obsidian_export, publish_obsidian_export,
    recover_obsidian_export, validate_source_export,
    validate_package,
)
from tests.test_cross_navigation import CrossNavigationTests


H = "1" * 64
AUTHORITY_CASE = CrossNavigationTests()
AUTHORITY_CASE.setUp()
PROJECT = AUTHORITY_CASE.index["project_id"]
AT = "2026-09-11T10:01:00Z"


def fixtures():
    files = {"00_START_HERE.md": b"# Start\n", "Topics/topic.md": b"# Topic\n"}
    knowledge = copy.deepcopy(AUTHORITY_CASE.view)
    navigation = copy.deepcopy(AUTHORITY_CASE.index)
    authority = copy.deepcopy(AUTHORITY_CASE.authority)
    source_binding = knowledge["source_binding"]
    source = {
        "schema_version": 1, "artifact_type": "seminartext.managed_generated_export",
        "kind": "obsidian_derived_view", "ownership_classes": ["MANAGED_GENERATED", "USER_OWNED"],
        "files": {name: hashlib.sha256(value).hexdigest() for name, value in files.items()},
        "canonical_evidence_artifact_id": source_binding["canonical_evidence_id"],
        "canonical_evidence_sha256": source_binding["canonical_evidence_sha256"],
        "canonical_knowledge_artifact_id": source_binding["canonical_knowledge_id"],
        "canonical_knowledge_sha256": source_binding["canonical_knowledge_sha256"],
        "coverage": {"full_seminar_coverage": True},
        "resolver_states": {item["target_id"]: "AVAILABLE" for item in navigation["targets"] if item["available"]},
    }
    manifest, packaged = build_obsidian_package(
        project_id=PROJECT, project_slug="course", source_files=files,
        source_manifest=source, knowledge_view=knowledge, navigation=navigation,
        evidence_payload=AUTHORITY_CASE.evidence_payload,
        source_evidence_payload=AUTHORITY_CASE.source_payload,
        knowledge_payload=AUTHORITY_CASE.knowledge_payload,
        navigation_authority=authority,
        created_at="2026-09-11T10:00:00Z",
    )
    return files, source, knowledge, navigation, authority, manifest, packaged


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
    return {"lease": lease, "lease_store": store,
            "clock": lambda: datetime(2026, 9, 11, 10, 1, tzinfo=timezone.utc)}


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
        for field in ("coverage", "resolver_states"):
            empty = copy.deepcopy(source); empty[field] = {}
            with self.assertRaisesRegex(PublishingError, "coverage or resolver"):
                validate_source_export(files, empty)

    def test_full_authority_rebuild_rejects_fabricated_action_or_locator(self):
        files, source, knowledge, navigation, authority, *_ = fixtures()
        for field, value in (("actions", ["OPEN_ENTITY"]), ("locators", [])):
            forged = copy.deepcopy(navigation)
            forged["targets"][0][field] = value
            forged["targets"][0]["target_sha256"] = _record_hash(forged["targets"][0], "target_sha256")
            forged["record_sha256"] = _record_hash(forged)
            with self.assertRaisesRegex(PublishingError, "authoritative source validation"):
                build_obsidian_package(project_id=PROJECT, project_slug="course", source_files=files,
                    source_manifest=source, knowledge_view=knowledge, navigation=forged,
                    evidence_payload=AUTHORITY_CASE.evidence_payload,
                    source_evidence_payload=AUTHORITY_CASE.source_payload,
                    knowledge_payload=AUTHORITY_CASE.knowledge_payload,
                    navigation_authority=authority, created_at="2026-09-11T10:00:00Z")

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
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); vault = base / "vault"; vault.mkdir(); auth = authorization(base, manifest)
            publish_obsidian_export(vault, manifest, files, **auth)
            current = vault / "Integra/course" / CURRENT
            pointer = json.loads(current.read_bytes()); pointer["package_id"] = "fabricated"
            current.write_text(json.dumps(pointer))
            with self.assertRaisesRegex(PublishingError, "collision"):
                publish_obsidian_export(vault, manifest, files, **auth)

    def test_symlink_vault_and_dangling_current_are_rejected(self):
        *_, manifest, files = fixtures()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); actual = base / "actual"; actual.mkdir()
            linked = base / "linked"; linked.symlink_to(actual)
            with self.assertRaisesRegex(PublishingError, "vault must not be a symlink"):
                preview_obsidian_export(linked, manifest, files)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); vault = base / "vault"; vault.mkdir(); auth = authorization(base, manifest)
            publish_obsidian_export(vault, manifest, files, **auth)
            current = vault / "Integra/course" / CURRENT
            current.unlink(); current.symlink_to("missing")
            with self.assertRaisesRegex(PublishingError, "collision"):
                publish_obsidian_export(vault, manifest, files, **auth)

    def test_runtime_manifest_authority_and_derived_identity_are_exact(self):
        *_, manifest, files = fixtures()
        mutations = [
            ("source_artifacts_modified", True),
            ("semantic_authority", "AUTHORITATIVE"),
            ("package_id", "urn:integra:artifact:99999999-9999-9999-9999-999999999999"),
        ]
        for field, value in mutations:
            changed = copy.deepcopy(manifest); changed[field] = value
            with self.assertRaises(PublishingError):
                validate_package(changed, files)
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

    def test_recovery_rejects_tampered_or_unknown_staging_without_erasing(self):
        *_, manifest, files = fixtures()
        for mutation in ("manifest", "unknown-directory", "lock-symlink"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); vault = root / "vault"; vault.mkdir(); auth = authorization(root, manifest)
                with self.assertRaises(PublishingError):
                    publish_obsidian_export(vault, manifest, files, interrupt_after="VERIFIED", **auth)
                staging = vault / "Integra/course/.staging" / (manifest["version_sha256"] + ".partial")
                if mutation == "manifest":
                    (staging / MANIFEST).write_text("{}")
                else:
                    if mutation == "unknown-directory":
                        (staging / "unknown").mkdir()
                    else:
                        lock = vault / "Integra/course/.export.lock"
                        lock.unlink(); lock.symlink_to(root / "missing-lock")
                with self.assertRaises(PublishingError):
                    recover_obsidian_export(vault, manifest, files, **auth)
                self.assertTrue(staging.exists())

    def test_immutable_version_rejects_unknown_directory(self):
        *_, manifest, files = fixtures()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); vault = root / "vault"; vault.mkdir(); auth = authorization(root, manifest)
            publish_obsidian_export(vault, manifest, files, **auth)
            version = vault / "Integra/course/versions" / manifest["version_sha256"]
            (version / "unknown").mkdir()
            with self.assertRaisesRegex(PublishingError, "collision"):
                publish_obsidian_export(vault, manifest, files, **auth)

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
                    lease_store=auth["lease_store"], clock=auth["clock"])
            with self.assertRaisesRegex(PublishingError, "lease"):
                publish_obsidian_export(vault, manifest, files, lease=auth["lease"],
                    lease_store=auth["lease_store"],
                    clock=lambda: datetime(2026, 9, 11, 10, 6, tzinfo=timezone.utc))
            self.assertEqual(list(vault.iterdir()), [])

    def test_resigned_binding_tampering_fails(self):
        files, source, knowledge, navigation, authority, *_ = fixtures()
        navigation["sources"]["knowledge"]["record_sha256"] = H
        navigation["record_sha256"] = _record_hash(navigation)
        with self.assertRaisesRegex(PublishingError, "authoritative source validation"):
            build_obsidian_package(project_id=PROJECT, project_slug="course", source_files=files,
                source_manifest=source, knowledge_view=knowledge, navigation=navigation,
                evidence_payload=AUTHORITY_CASE.evidence_payload,
                source_evidence_payload=AUTHORITY_CASE.source_payload,
                knowledge_payload=AUTHORITY_CASE.knowledge_payload,
                navigation_authority=authority,
                created_at="2026-09-11T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
