import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from integra_core.migration import (
    MigrationError,
    build_dry_run,
    discover_source_project,
    execute_copy_on_write,
    validate_discovery,
    validate_migration,
    validate_plan,
    validate_report,
    migration_operation_identity,
)
from integra_core.operations import JobStore, ResourceReservationStore
from integra_core.migration_fixtures import (
    EXPECTED_RESULTS,
    run_governed_migration_action,
    run_migration_fixtures,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "migration_v1"


class MigrationTests(unittest.TestCase):
    def test_governed_fixture_inventory_passes(self) -> None:
        results = run_migration_fixtures(ROOT)
        self.assertEqual(set(results), EXPECTED_RESULTS)
        self.assertEqual(set(results.values()), {"PASS"})

    def test_discovers_seminartext_read_only(self) -> None:
        source = FIXTURES / "seminartext_project"
        before = self.snapshot(source)
        discovery = discover_source_project(source, "seminartext")
        validate_discovery(discovery)
        self.assertEqual(discovery["source_format"], "SEMINARTEXT_PROJECT")
        self.assertEqual(discovery["source_schema_version"], "1")
        self.assertTrue(discovery["read_only"])
        self.assertEqual(before, self.snapshot(source))

    def test_discovers_videotext_schema_v7_read_only(self) -> None:
        source = FIXTURES / "videotext_project"
        before = self.snapshot(source)
        discovery = discover_source_project(source, "videotext")
        self.assertEqual(discovery["source_format"], "VIDEOTEXT_PROJECT")
        self.assertEqual(discovery["source_schema_version"], "7")
        self.assertEqual(discovery["source_references"][0]["scope"], "IN_PROJECT")
        self.assertEqual(before, self.snapshot(source))

    def test_dry_run_writes_nothing(self) -> None:
        source = FIXTURES / "seminartext_project"
        discovery = discover_source_project(source, "seminartext")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            parent_before = list(Path(temporary).iterdir())
            plan = build_dry_run(discovery, target)
            validate_plan(plan)
            self.assertEqual(plan["status"], "READY")
            self.assertEqual(plan["source_write_operations"], 0)
            self.assertEqual(parent_before, list(Path(temporary).iterdir()))
            self.assertFalse(target.exists())

    def test_copy_validation_and_rollback_preserve_source(self) -> None:
        source = FIXTURES / "videotext_project"
        before = self.snapshot(source)
        discovery = discover_source_project(source, "videotext")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            plan = build_dry_run(discovery, target)
            control = Path(temporary) / "control"
            report = run_governed_migration_action(
                control, action="copy", discovery=discovery, plan=plan
            )
            validate_report(report)
            integrity = validate_migration(discovery, plan, report)
            self.assertEqual(integrity["status"], "PASS")
            self.assertFalse(report["activation_performed"])
            rollback = run_governed_migration_action(
                control,
                action="rollback",
                discovery=discovery,
                plan=plan,
                report=report,
            )
            self.assertEqual(rollback["status"], "ROLLED_BACK")
            self.assertFalse(target.exists())
        self.assertEqual(before, self.snapshot(source))

    def test_governed_action_finishes_job_and_releases_resources(self) -> None:
        discovery = discover_source_project(
            FIXTURES / "seminartext_project", "seminartext"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = build_dry_run(discovery, root / "target")
            control = root / "control"
            run_governed_migration_action(
                control, action="copy", discovery=discovery, plan=plan
            )
            identity = migration_operation_identity(plan, "copy")
            job = JobStore(control / "jobs").read(identity["job_id"])
            reservations = ResourceReservationStore(
                control / "reservations", "migration-fixture-host"
            ).find_by_job(identity["job_id"])
            self.assertEqual(job["state"], "SUCCEEDED")
            self.assertEqual(job["terminal"]["outcome"], "SUCCEEDED")
            self.assertEqual(len(reservations), 1)
            self.assertEqual(reservations[0]["state"], "RELEASED")

    def test_ids_are_independent_of_root_path(self) -> None:
        source = FIXTURES / "seminartext_project"
        first = discover_source_project(source, "seminartext")
        with tempfile.TemporaryDirectory() as temporary:
            moved = Path(temporary) / "different-display-name"
            shutil.copytree(source, moved)
            second = discover_source_project(moved, "seminartext")
        self.assertEqual(first["project_id"], second["project_id"])
        self.assertEqual(first["source_revision_sha256"], second["source_revision_sha256"])
        self.assertEqual(first["layout_sha256"], second["layout_sha256"])
        self.assertEqual(first["files"], second["files"])
        with tempfile.TemporaryDirectory() as temporary:
            first_plan = build_dry_run(first, Path(temporary) / "target-a")
            second_plan = build_dry_run(first, Path(temporary) / "target-b")
        self.assertEqual(first_plan["plan_id"], second_plan["plan_id"])
        self.assertEqual(first_plan["job_id"], second_plan["job_id"])
        self.assertEqual(first_plan["plan_sha256"], second_plan["plan_sha256"])
        self.assertNotEqual(
            first_plan["target_locator_sha256"], second_plan["target_locator_sha256"]
        )

    def test_target_collision_never_overwrites(self) -> None:
        discovery = discover_source_project(FIXTURES / "videotext_project", "videotext")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            target.mkdir()
            sentinel = target / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")
            plan = build_dry_run(discovery, target)
            self.assertEqual(plan["status"], "BLOCKED")
            with self.assertRaisesRegex(MigrationError, "blocked"):
                execute_copy_on_write(discovery, plan)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_ready_copy_requires_governed_operations_context(self) -> None:
        discovery = discover_source_project(FIXTURES / "seminartext_project", "seminartext")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            plan = build_dry_run(discovery, target)
            with self.assertRaisesRegex(MigrationError, "governed Operations context"):
                execute_copy_on_write(discovery, plan)
            self.assertFalse(target.exists())

    def test_wrong_or_expired_project_lease_blocks_copy(self) -> None:
        discovery = discover_source_project(FIXTURES / "seminartext_project", "seminartext")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            plan = build_dry_run(discovery, target)
            with self.assertRaisesRegex(MigrationError, "expired"):
                run_governed_migration_action(
                    Path(temporary) / "control",
                    action="copy",
                    discovery=discovery,
                    plan=plan,
                    execution_now="2026-09-11T00:11:00Z",
                )
            self.assertFalse(target.exists())

    def test_derived_identifiers_cannot_be_substituted(self) -> None:
        discovery = discover_source_project(FIXTURES / "seminartext_project", "seminartext")
        changed = copy.deepcopy(discovery)
        changed["project_id"] = "urn:integra:project:11111111-1111-4111-8111-111111111111"
        with self.assertRaisesRegex(MigrationError, "project ID"):
            validate_discovery(changed)
        with tempfile.TemporaryDirectory() as temporary:
            plan = build_dry_run(discovery, Path(temporary) / "target")
            changed_plan = copy.deepcopy(plan)
            changed_plan["plan_id"] = "urn:integra:operation:22222222-2222-4222-8222-222222222222"
            with self.assertRaisesRegex(MigrationError, "plan ID"):
                validate_plan(changed_plan)

    def test_target_cannot_be_substituted_after_operations_authorization(self) -> None:
        discovery = discover_source_project(FIXTURES / "seminartext_project", "seminartext")
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            plan = build_dry_run(discovery, parent / "authorized-target")
            changed = build_dry_run(discovery, parent / "substituted-target")
            with self.assertRaises(MigrationError):
                run_governed_migration_action(
                    parent / "control",
                    action="copy",
                    discovery=discovery,
                    plan=changed,
                    authorization_plan=plan,
                )
            self.assertFalse((parent / "substituted-target").exists())

    def test_source_change_after_plan_blocks_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            shutil.copytree(FIXTURES / "seminartext_project", source)
            discovery = discover_source_project(source, "seminartext")
            target = Path(temporary) / "target"
            plan = build_dry_run(discovery, target)
            (source / "transcript_video_001.txt").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(MigrationError, "changed after discovery"):
                run_governed_migration_action(
                    Path(temporary) / "control",
                    action="copy",
                    discovery=discovery,
                    plan=plan,
                )
            self.assertFalse(target.exists())

    def test_symlink_source_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            shutil.copytree(FIXTURES / "seminartext_project", source)
            (source / "link").symlink_to(source / "seminar.yaml")
            with self.assertRaisesRegex(MigrationError, "unsafe file"):
                discover_source_project(source, "seminartext")

    def test_unexpected_target_file_blocks_rollback(self) -> None:
        source = FIXTURES / "seminartext_project"
        discovery = discover_source_project(source, "seminartext")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            plan = build_dry_run(discovery, target)
            control = Path(temporary) / "control"
            report = run_governed_migration_action(
                control, action="copy", discovery=discovery, plan=plan
            )
            (target / "user-file.txt").write_text("do not delete", encoding="utf-8")
            with self.assertRaisesRegex(MigrationError, "unexpected"):
                run_governed_migration_action(
                    control,
                    action="rollback",
                    discovery=discovery,
                    plan=plan,
                    report=report,
                )
            self.assertTrue(target.exists())
            self.assertEqual((target / "user-file.txt").read_text(encoding="utf-8"), "do not delete")

    def test_unexpected_empty_directory_blocks_rollback(self) -> None:
        source = FIXTURES / "seminartext_project"
        discovery = discover_source_project(source, "seminartext")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            plan = build_dry_run(discovery, target)
            control = Path(temporary) / "control"
            report = run_governed_migration_action(
                control, action="copy", discovery=discovery, plan=plan
            )
            unexpected = target / "user-empty-directory"
            unexpected.mkdir()
            with self.assertRaisesRegex(MigrationError, "unexpected directories"):
                run_governed_migration_action(
                    control,
                    action="rollback",
                    discovery=discovery,
                    plan=plan,
                    report=report,
                )
            self.assertTrue(target.exists())
            self.assertTrue(unexpected.is_dir())

    def test_tampered_target_fails_integrity(self) -> None:
        source = FIXTURES / "videotext_project"
        discovery = discover_source_project(source, "videotext")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            plan = build_dry_run(discovery, target)
            report = run_governed_migration_action(
                Path(temporary) / "control",
                action="copy",
                discovery=discovery,
                plan=plan,
            )
            copied = target / plan["mappings"][0]["destination_relative_path"]
            copied.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(MigrationError, "size differs|hash differs"):
                validate_migration(discovery, plan, report)

    def test_tampered_project_manifest_fails_integrity(self) -> None:
        source = FIXTURES / "videotext_project"
        discovery = discover_source_project(source, "videotext")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            plan = build_dry_run(discovery, target)
            report = run_governed_migration_action(
                Path(temporary) / "control",
                action="copy",
                discovery=discovery,
                plan=plan,
            )
            manifest_path = target / ".integra" / "project.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_component"] = "seminartext"
            manifest["unexpected"] = "must fail closed"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(MigrationError, "manifest differs"):
                validate_migration(discovery, plan, report)

    def test_external_videotext_source_is_not_accessed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "project"
            shutil.copytree(FIXTURES / "videotext_project", source)
            manifest_path = source / "Support files" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["sourceMediaPath"] = "/private/not-authorized/source.mp4"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            discovery = discover_source_project(source, "videotext")
            reference = discovery["source_references"][0]
            self.assertEqual(reference["scope"], "EXTERNAL_REFERENCE")
            self.assertFalse(reference["accessed"])
            self.assertNotIn("/private/not-authorized/source.mp4", json.dumps(discovery))

    def test_noncanonical_seminartext_source_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            shutil.copytree(FIXTURES / "seminartext_project", source)
            registry_path = source / "sources.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["videos"][0]["file"] = "../outside.mp4"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(MigrationError, "escapes"):
                discover_source_project(source, "seminartext")

    def test_partial_recovery_refuses_unknown_bytes(self) -> None:
        source = FIXTURES / "seminartext_project"
        discovery = discover_source_project(source, "seminartext")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "partial"
            plan = build_dry_run(discovery, target)
            target.mkdir()
            (target / ".integra-migration-in-progress.json").write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "plan_id": plan["plan_id"],
                    "plan_sha256": plan["plan_sha256"],
                    "project_id": plan["project_id"],
                    "target_locator_sha256": plan["target_locator_sha256"],
                    "state": "IN_PROGRESS",
                }),
                encoding="utf-8",
            )
            (target / "unknown.txt").write_text("unknown", encoding="utf-8")
            with self.assertRaisesRegex(MigrationError, "unexpected"):
                run_governed_migration_action(
                    Path(temporary) / "control", action="recover", plan=plan
                )
            self.assertTrue(target.exists())

    def test_partial_recovery_accepts_empty_planned_source_directory(self) -> None:
        discovery = discover_source_project(
            FIXTURES / "seminartext_project", "seminartext"
        )
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "partial"
            plan = build_dry_run(discovery, target)
            target.mkdir()
            (target / ".integra-migration-in-progress.json").write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "plan_id": plan["plan_id"],
                    "plan_sha256": plan["plan_sha256"],
                    "project_id": plan["project_id"],
                    "target_locator_sha256": plan["target_locator_sha256"],
                    "state": "IN_PROGRESS",
                }),
                encoding="utf-8",
            )
            (target / "source").mkdir()
            recovered = run_governed_migration_action(
                Path(temporary) / "control", action="recover", plan=plan
            )
            self.assertEqual(recovered["status"], "RECOVERED_PARTIAL")
            self.assertFalse(target.exists())

    def test_partial_recovery_accepts_exact_project_manifest_phase(self) -> None:
        discovery = discover_source_project(
            FIXTURES / "videotext_project", "videotext"
        )
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "partial"
            plan = build_dry_run(discovery, target)
            control = Path(temporary) / "control"
            run_governed_migration_action(
                control, action="copy", discovery=discovery, plan=plan
            )
            (target / ".integra" / "migration_report.json").unlink()
            (target / ".integra-migration-in-progress.json").write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "plan_id": plan["plan_id"],
                    "plan_sha256": plan["plan_sha256"],
                    "project_id": plan["project_id"],
                    "target_locator_sha256": plan["target_locator_sha256"],
                    "state": "IN_PROGRESS",
                }),
                encoding="utf-8",
            )
            recovered = run_governed_migration_action(
                control, action="recover", plan=plan
            )
            self.assertEqual(recovered["status"], "RECOVERED_PARTIAL")
            self.assertFalse(target.exists())

    def test_partial_recovery_accepts_exact_report_before_marker_removal(self) -> None:
        discovery = discover_source_project(
            FIXTURES / "seminartext_project", "seminartext"
        )
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "partial"
            plan = build_dry_run(discovery, target)
            control = Path(temporary) / "control"
            run_governed_migration_action(
                control, action="copy", discovery=discovery, plan=plan
            )
            (target / ".integra-migration-in-progress.json").write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "plan_id": plan["plan_id"],
                    "plan_sha256": plan["plan_sha256"],
                    "project_id": plan["project_id"],
                    "target_locator_sha256": plan["target_locator_sha256"],
                    "state": "IN_PROGRESS",
                }),
                encoding="utf-8",
            )
            recovered = run_governed_migration_action(
                control, action="recover", plan=plan
            )
            self.assertEqual(recovered["status"], "RECOVERED_PARTIAL")
            self.assertFalse(target.exists())

    @staticmethod
    def snapshot(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file() and not path.is_symlink()
        }


if __name__ == "__main__":
    unittest.main()
