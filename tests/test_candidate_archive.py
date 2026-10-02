"""Local archive fixtures only: no app build, launch, promotion, or live runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integra_core.candidate_identity import candidate_id, canonical_bytes, tree_sha256
from scripts import candidate_archive as archive
from scripts import candidate_protection_gate


class CandidateArchiveTests(unittest.TestCase):
    def setUp(self):
        # Production rejects OS temporary roots; isolate tiny fixtures under HOME.
        self.temporary = tempfile.TemporaryDirectory(prefix=".integra-archive-test-", dir=Path.home())
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / "source" / "Integra.app"
        self.manifest = self.app / archive.EMBEDDED
        self.manifest.parent.mkdir(parents=True)
        self.executable = self.app / "Contents/MacOS/Integra"
        self.executable.parent.mkdir()
        self.executable.write_bytes(b"fixture executable\x00\n")
        self.executable.chmod(0o755)
        (self.app / "Contents/Resources/empty").mkdir()
        cache = self.app / "Contents/Resources/__pycache__"
        cache.mkdir(); (cache / "fixture.pyc").write_bytes(b"retained despite bundle hash exclusion")
        self.identity = {"source": {"commit_sha": "a" * 40},
                         "execution": {"gui_python": {"path": "/unavailable/external/python", "sha256": "b" * 64}}}
        self._manifest()
        self.destination = self.root / "durable"

    def _manifest(self, *, timestamp="fixture"):
        value = {"schema_version": "1.0", "candidate_id": candidate_id(self.identity),
                 "identity_sha256": candidate_id(self.identity).removeprefix("candidate-v1-"),
                 "identity": self.identity,
                 "bundle": {"digest_algorithm": "sha256-tree-excluding-candidate-manifest",
                            "digest": tree_sha256(self.app, exclude={archive.EMBEDDED})},
                 "build": {"timestamp": timestamp}}
        self.manifest.write_bytes(canonical_bytes(value) + b"\n")
        return value

    def _create(self, **kwargs):
        return archive.create_archive(self.app, self.destination, **kwargs)

    def _package(self):
        return Path(self._create()["archive_path"])

    def _expected_path(self):
        value = json.loads(self.manifest.read_text())
        return self.destination / value["candidate_id"] / value["bundle"]["digest"]

    def test_copy_preserves_exact_bytes_modes_and_separate_inodes(self):
        receipt = self._create()
        package = Path(receipt["archive_path"])
        self.assertEqual(package, self._expected_path())
        self.assertEqual(receipt["verification"], "ARCHIVAL_BYTE_INTEGRITY")
        self.assertEqual(receipt["runtime_validation"], "NOT_PERFORMED")
        for source in self.app.rglob("*"):
            target = package / archive.APP / source.relative_to(self.app)
            self.assertEqual(source.stat().st_mode & 0o7777, target.stat().st_mode & 0o7777)
            if source.is_file():
                self.assertEqual(source.read_bytes(), target.read_bytes())
                self.assertNotEqual(source.stat().st_ino, target.stat().st_ino)
                self.assertEqual(target.stat().st_nlink, 1)
        self.assertEqual(receipt["app_size_bytes"], sum(p.stat().st_size for p in self.app.rglob("*") if p.is_file()))
        self.assertTrue((package / archive.COMPLETE).is_file())
        self.assertEqual(archive.verify_archive(package, {key: receipt[key] for key in archive.IDENTITY_KEYS}), receipt)

    def test_verification_is_offline_after_original_source_disappears(self):
        package = self._package()
        shutil.rmtree(self.app)
        with patch("integra_core.candidate_identity.validate_bundle", side_effect=AssertionError("live validation")):
            self.assertEqual(archive.verify_archive(package)["status"], "COMPLETE")

    def test_external_manifest_and_evidence_are_exact_retained_bytes(self):
        retained = self.root / "manifest.json"; shutil.copy2(self.manifest, retained)
        evidence = self.root / "probe.json"; evidence.write_bytes(b'{"result":"fixture only"}\n')
        receipt = self._create(manifest=retained, evidence=[evidence])
        package = Path(receipt["archive_path"])
        self.assertEqual((package / archive.MANIFEST_NAME).read_bytes(), retained.read_bytes())
        self.assertEqual((package / "evidence/0000-probe.json").read_bytes(), evidence.read_bytes())
        self.assertEqual(self._create(manifest=retained, evidence=[evidence]), receipt)
        evidence.write_bytes(b"changed evidence")
        with self.assertRaisesRegex(ValueError, "existing archive differs"):
            self._create(manifest=retained, evidence=[evidence])
        self.assertEqual(archive.verify_archive(package), receipt)

    def test_external_manifest_mismatch_fails_before_copy(self):
        other = self.root / "wrong-manifest.json"; other.write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "exactly match"):
            self._create(manifest=other)
        self.assertFalse(self.destination.exists())

    def test_managed_archive_requires_canonical_lifecycle_gate_before_copy(self):
        with patch.object(archive, 'MANAGED_BASE', self.root), \
                patch.object(candidate_protection_gate, 'require_archive_publication',
                             side_effect=ValueError('authority pending')) as gate:
            with self.assertRaisesRegex(ValueError, 'authority pending'):
                self._create()
            gate.assert_called_once()
        self.assertFalse(self._expected_path().exists())

    def test_idempotent_existing_fully_reverifies(self):
        receipt = self._create()
        with patch.object(archive, "_publish", side_effect=AssertionError("must not republish")):
            self.assertEqual(self._create(), receipt)
        package = Path(receipt["archive_path"])
        executable = package / archive.APP / "Contents/MacOS/Integra"
        executable.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            self._create()
        self.assertEqual(executable.stat().st_mode & 0o777, 0o644)

    def test_candidate_id_collision_is_partitioned_by_bundle_digest(self):
        first = self._create()
        self.executable.write_bytes(b"different build bytes")
        self._manifest()
        second = self._create()
        self.assertEqual(first["candidate_id"], second["candidate_id"])
        self.assertNotEqual(first["bundle_digest"], second["bundle_digest"])
        self.assertNotEqual(first["archive_path"], second["archive_path"])
        self.assertEqual(archive.verify_archive(Path(first["archive_path"])), first)
        self.assertEqual(archive.verify_archive(Path(second["archive_path"])), second)

    def test_same_candidate_bundle_but_different_manifest_is_not_overwritten(self):
        first = self._create()
        self._manifest(timestamp="different metadata")
        with self.assertRaisesRegex(ValueError, "manifest_digest differs"):
            self._create()
        self.assertEqual(archive.verify_archive(Path(first["archive_path"])), first)

    def test_existing_partial_destination_is_preserved(self):
        destination = self._expected_path(); destination.mkdir(parents=True)
        sentinel = destination / "user-file"; sentinel.write_text("preserve")
        with self.assertRaises(ValueError):
            self._create()
        self.assertEqual(sentinel.read_text(), "preserve")
        self.assertEqual(list(destination.iterdir()), [sentinel])

    def test_interrupted_copy_leaves_no_complete_or_published_package(self):
        original = shutil.copy2
        count = 0

        def interrupt(source, destination, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("simulated interruption")
            return original(source, destination, **kwargs)

        with patch.object(archive.shutil, "copy2", side_effect=interrupt):
            with self.assertRaisesRegex(ValueError, "simulated interruption"):
                self._create()
        self.assertFalse(self._expected_path().exists())
        self.assertTrue(list(self.destination.glob("*/.incomplete-*")))
        self.assertEqual(list(self.destination.rglob(archive.COMPLETE)), [])

    def test_publish_failure_keeps_only_incomplete_attempt(self):
        with patch.object(archive, "_publish", side_effect=OSError("publish interrupted")):
            with self.assertRaisesRegex(ValueError, "publish interrupted"):
                self._create()
        self.assertFalse(self._expected_path().exists())
        self.assertEqual(list(self.destination.rglob(archive.COMPLETE)), [])

    def test_atomic_publish_never_replaces_concurrently_created_empty_directory(self):
        original = archive._publish

        def collide(stage, destination):
            destination.mkdir()
            original(stage, destination)

        with patch.object(archive, "_publish", side_effect=collide):
            with self.assertRaises(ValueError):
                self._create()
        self.assertTrue(self._expected_path().is_dir())
        self.assertEqual(list(self._expected_path().iterdir()), [])
        self.assertEqual(list(self.destination.rglob(archive.COMPLETE)), [])

    def test_tampering_missing_app_or_metadata_only_cannot_qualify(self):
        package = self._package()
        target = package / archive.APP / "Contents/MacOS/Integra"
        target.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "bundle bytes differ"):
            archive.verify_archive(package)
        shutil.rmtree(package / archive.APP)
        with self.assertRaises(ValueError):
            archive.verify_archive(package)

    def test_python_cache_extra_files_and_permissions_are_bound(self):
        package = self._package()
        cache = package / archive.APP / "Contents/Resources/__pycache__/fixture.pyc"
        before = cache.read_bytes(); cache.write_bytes(b"different cache")
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            archive.verify_archive(package)
        cache.write_bytes(before)
        extra = package / "unlisted"; extra.write_text("extra")
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            archive.verify_archive(package)
        extra.unlink()
        (package / archive.APP / "Contents/Resources/empty").chmod(0o700)
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            archive.verify_archive(package)

    def test_retained_manifest_inventory_and_complete_tamper_fail(self):
        package = self._package()
        for name in (archive.MANIFEST_NAME, archive.INVENTORY, archive.COMPLETE):
            with self.subTest(name=name):
                target = package / name; original = target.read_bytes()
                target.write_bytes(b"{}")
                with self.assertRaises(ValueError):
                    archive.verify_archive(package)
                target.write_bytes(original)
        self.assertEqual(archive.verify_archive(package)["status"], "COMPLETE")

    def test_expected_identity_is_enforced_and_unknown_fields_fail(self):
        package = self._package()
        for key in archive.IDENTITY_KEYS:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "differs from expected"):
                archive.verify_archive(package, {key: "wrong"})
        with self.assertRaisesRegex(ValueError, "unsupported expected"):
            archive.verify_archive(package, {"unknown": "value"})

    def test_symlink_and_special_file_in_source_are_rejected(self):
        bad = self.app / "Contents/Resources/bad"
        bad.symlink_to(self.executable)
        with self.assertRaisesRegex(ValueError, "regular files"):
            self._create()
        bad.unlink(); os.mkfifo(bad)
        with self.assertRaisesRegex(ValueError, "regular files"):
            self._create()
        self.assertFalse(self.destination.exists())

    def test_archive_symlinks_and_hardlinks_are_rejected(self):
        package = self._package()
        target = package / archive.MANIFEST_NAME
        target.unlink(); target.symlink_to(self.manifest)
        with self.assertRaisesRegex(ValueError, "regular files"):
            archive.verify_archive(package)
        target.unlink(); os.link(self.manifest, target)
        with self.assertRaisesRegex(ValueError, "hardlinked"):
            archive.verify_archive(package)

    def test_symlink_ancestors_traversal_and_overlapping_paths_fail(self):
        link = self.root / "link"; link.symlink_to(self.root, target_is_directory=True)
        for destination in (link / "archive", self.root / "unused/../archive", self.app / "archive", self.root):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                archive.create_archive(self.app, destination)
        with self.assertRaisesRegex(ValueError, "symlink"):
            archive.create_archive(link / "source/Integra.app", self.destination)
        with self.assertRaisesRegex(ValueError, "symlink"):
            archive.verify_archive(link / "archive")

    def test_temporary_root_destinations_are_rejected(self):
        for root in (Path("/tmp"), Path("/private/tmp"), Path(tempfile.gettempdir())):
            with self.subTest(root=root), self.assertRaises(ValueError):
                archive.create_archive(self.app, root / "candidate-archive-test")
        with patch.dict(os.environ, {"TMPDIR": str(self.root)}):
            with self.assertRaisesRegex(ValueError, "temporary root"):
                self._create()

    @unittest.skipUnless(sys.platform == "darwin", "macOS case-alias regression")
    def test_case_aliased_temporary_root_fails_before_copy_without_source_mutation(self):
        alias = Path("/private/TMP")
        if not alias.exists() or not alias.samefile("/private/tmp"):
            self.skipTest("temporary volume is case-sensitive")
        before = archive._inventory(self.app)
        destination = alias / self.root.name / "archive"
        with patch.object(archive.shutil, "copytree", side_effect=AssertionError("copy must not start")):
            with self.assertRaisesRegex(ValueError, "temporary root"):
                archive.create_archive(self.app, destination)
        with self.assertRaisesRegex(ValueError, "temporary root"):
            archive.verify_archive(destination)
        self.assertFalse(destination.exists())
        self.assertEqual(archive._inventory(self.app), before)

    @unittest.skipUnless(sys.platform == "darwin", "macOS case-alias regression")
    def test_case_aliased_source_overlap_fails_before_copy_without_source_mutation(self):
        alias = self.root / "SOURCE/Integra.app"
        if not alias.exists() or not alias.samefile(self.app):
            self.skipTest("fixture volume is case-sensitive")
        before = archive._inventory(self.app)
        pairs = ((alias, self.app / "future/archive"),
                 (self.app, alias / "future/archive"),
                 (self.app, alias), (alias, self.app.parent))
        with patch.object(archive.shutil, "copytree", side_effect=AssertionError("copy must not start")):
            for source, destination in pairs:
                with self.subTest(source=source, destination=destination):
                    with self.assertRaisesRegex(ValueError, "must not overlap"):
                        archive.create_archive(source, destination)
        self.assertFalse((self.app / "future").exists())
        self.assertEqual(archive._inventory(self.app), before)

    def test_containment_distinguishes_missing_root_children_and_siblings(self):
        future = self.root / "future/archive"
        self.assertTrue(archive.path_is_within(future, future))
        self.assertTrue(archive.path_is_within(future / "nested/output.json", future))
        self.assertFalse(archive.path_is_within(self.root / "future/archive-other", future))
        self.assertFalse(archive.path_is_within(self.root / "other/archive", future))
        self.assertFalse(archive.path_is_within(self.root, future))
        self.assertFalse((self.root / "future").exists())

    @unittest.skipUnless(sys.platform == "darwin", "macOS case-alias regression")
    def test_missing_root_containment_uses_existing_ancestor_identity(self):
        alias = self.root / "SOURCE"
        if not alias.exists() or not alias.samefile(self.app.parent):
            self.skipTest("fixture volume is case-sensitive")
        future = self.app.parent / "future/archive"
        self.assertTrue(archive.path_is_within(alias / "future/archive/output.json", future))
        self.assertTrue(archive.path_is_within(future / "output.json", alias / "future/archive"))
        self.assertFalse(archive.path_is_within(alias / "future/archive-other/output.json", future))
        self.assertFalse(archive.path_is_within(alias / "other/archive/output.json", future))
        self.assertFalse(future.exists())

    def test_disk_preflight_includes_reserve_and_performs_no_copy(self):
        with patch.object(archive.shutil, "disk_usage", return_value=SimpleNamespace(free=archive.RESERVE_BYTES)):
            with patch.object(archive.shutil, "copytree", side_effect=AssertionError("copy must not start")):
                with self.assertRaisesRegex(ValueError, "insufficient disk space"):
                    self._create()
        self.assertFalse(self.destination.exists())
        with self.assertRaisesRegex(ValueError, "disk reserve"):
            self._create(reserve_bytes=0)

    def test_invalid_source_and_source_changed_during_copy_fail(self):
        original = self.executable.read_bytes(); self.executable.write_bytes(b"invalid before copy")
        with self.assertRaisesRegex(ValueError, "bundle bytes differ"):
            self._create()
        self.assertFalse(self.destination.exists())
        self.executable.write_bytes(original)
        original_copy = shutil.copytree

        def mutate(source, destination, *args, **kwargs):
            result = original_copy(source, destination, *args, **kwargs)
            if Path(source) == self.app:
                self.executable.chmod(0o644)
            return result

        with patch.object(archive.shutil, "copytree", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "source files/permissions changed"):
                self._create()
        self.assertEqual(list(self.destination.rglob(archive.COMPLETE)), [])

    def test_cli_create_verify_and_expected_mismatch(self):
        script = Path(archive.__file__)
        result = subprocess.run([sys.executable, "-B", str(script), "create", "--app", str(self.app),
                                 "--archive-root", str(self.destination)], capture_output=True, text=True, check=True)
        receipt = json.loads(result.stdout)
        result = subprocess.run([sys.executable, "-B", str(script), "verify", receipt["archive_path"],
                                 "--candidate-id", receipt["candidate_id"], "--bundle-digest", receipt["bundle_digest"],
                                 "--manifest-digest", receipt["manifest_digest"]], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), receipt)
        result = subprocess.run([sys.executable, "-B", str(script), "verify", receipt["archive_path"],
                                 "--bundle-digest", "wrong"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("differs from expected", result.stderr)


if __name__ == "__main__":
    unittest.main()
