import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from integra_core.playlist import (
    PlaylistError,
    build_playlist_plan,
    diff_playlist_refresh,
    discover_playlist,
    process_playlist,
    validate_checkpoint,
    validate_discovery,
    validate_plan,
    validate_refresh,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "playlist_v1"


class PlaylistTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.artifact_root = Path(self._temporary.name)
        self.persisted: list[dict] = []

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def load(self, name: str) -> dict:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def result(self, item: dict) -> dict:
        payload = f"processed:{item['video_id']}".encode()
        relative_path = f"{item['video_id']}.bin"
        (self.artifact_root / relative_path).write_bytes(payload)
        return {"relative_path": relative_path}

    def test_offline_discovery_is_deterministic_and_traceable(self) -> None:
        raw = self.load("snapshot_initial.json")
        first = discover_playlist(raw)
        second = discover_playlist(copy.deepcopy(raw))
        self.assertEqual(first, second)
        self.assertFalse(first["network_access_performed"])
        self.assertEqual(len({item["video_source_id"] for item in first["items"]}), 3)
        self.assertEqual(first["items"][0]["title"], "Fixture lesson A")
        validate_discovery(first)

    def test_reorder_does_not_change_video_source_identity(self) -> None:
        first = discover_playlist(self.load("snapshot_initial.json"))
        second = discover_playlist(self.load("snapshot_refreshed.json"))
        old = {item["video_id"]: item["video_source_id"] for item in first["items"]}
        new = {item["video_id"]: item["video_source_id"] for item in second["items"]}
        self.assertEqual(old["video-a"], new["video-a"])
        self.assertEqual(old["video-b"], new["video-b"])
        self.assertEqual(first["collection_id"], second["collection_id"])

    def test_subset_plan_is_ordered_sequential_and_has_exact_storage(self) -> None:
        discovery = discover_playlist(self.load("snapshot_initial.json"))
        plan = build_playlist_plan(discovery, ["video-b", "video-a"])
        validate_plan(plan)
        self.assertEqual(plan["selected_video_ids"], ["video-b", "video-a"])
        self.assertEqual(plan["execution"]["max_parallel_items"], 1)
        estimate = plan["storage_estimate"]
        self.assertEqual(
            estimate["required_disk_bytes"],
            sum(value for key, value in estimate.items() if key != "required_disk_bytes"),
        )

    def test_unknown_or_duplicate_selection_fails_closed(self) -> None:
        discovery = discover_playlist(self.load("snapshot_initial.json"))
        for selection in (["unknown"], ["video-a", "video-a"], []):
            with self.subTest(selection=selection), self.assertRaises(PlaylistError):
                build_playlist_plan(discovery, selection)

    def test_pause_resume_never_reprocesses_completed_video(self) -> None:
        discovery = discover_playlist(self.load("snapshot_initial.json"))
        plan = build_playlist_plan(discovery)
        calls: list[str] = []

        def processor(item: dict) -> dict:
            calls.append(item["video_id"])
            return self.result(item)

        paused = process_playlist(
            plan,
            processor,
            artifact_root=self.artifact_root,
            checkpoint_writer=self.persisted.append,
            max_new_items=1,
        )
        self.assertEqual(paused["status"], "PAUSED")
        self.assertEqual(calls, ["video-a"])
        complete = process_playlist(
            plan,
            processor,
            paused,
            artifact_root=self.artifact_root,
            checkpoint_writer=self.persisted.append,
        )
        self.assertEqual(complete["status"], "COMPLETE")
        self.assertEqual(calls, ["video-a", "video-b"])
        replay = process_playlist(
            plan,
            processor,
            complete,
            artifact_root=self.artifact_root,
            checkpoint_writer=self.persisted.append,
        )
        self.assertEqual(replay, complete)
        self.assertEqual(calls, ["video-a", "video-b"])
        self.assertEqual(complete["inaccessible"][0]["video_id"], "video-c")

    def test_per_video_provenance_binds_snapshot_position(self) -> None:
        discovery = discover_playlist(self.load("snapshot_initial.json"))
        plan = build_playlist_plan(discovery, ["video-b"])
        checkpoint = process_playlist(
            plan,
            self.result,
            artifact_root=self.artifact_root,
            checkpoint_writer=self.persisted.append,
        )
        record = checkpoint["completed"][0]
        self.assertEqual(record["snapshot_id"], discovery["snapshot_id"])
        self.assertEqual(record["snapshot_position"], 1)
        self.assertEqual(record["provenance_status"], "EXACT")

    def test_changed_checkpoint_or_plan_fails_closed(self) -> None:
        discovery = discover_playlist(self.load("snapshot_initial.json"))
        plan = build_playlist_plan(discovery)
        checkpoint = process_playlist(
            plan,
            self.result,
            artifact_root=self.artifact_root,
            checkpoint_writer=self.persisted.append,
            max_new_items=1,
        )
        changed = copy.deepcopy(checkpoint)
        changed["completed"][0]["snapshot_position"] = 99
        with self.assertRaises(PlaylistError):
            validate_checkpoint(plan, changed, self.artifact_root)
        changed_plan = copy.deepcopy(plan)
        changed_plan["execution"]["max_parallel_items"] = 2
        with self.assertRaises(PlaylistError):
            validate_plan(changed_plan)
        changed_plan = copy.deepcopy(plan)
        changed_plan["items"][0]["title"] = "Unbound replacement"
        with self.assertRaises(PlaylistError):
            validate_plan(changed_plan)

    def test_item_checkpoint_is_durable_before_later_processor_crash(self) -> None:
        discovery = discover_playlist(self.load("snapshot_initial.json"))
        plan = build_playlist_plan(discovery)
        persisted: list[dict] = []
        calls: list[str] = []

        def crashing_processor(item: dict) -> dict:
            calls.append(item["video_id"])
            if item["video_id"] == "video-b":
                raise RuntimeError("synthetic crash")
            return self.result(item)

        with self.assertRaises(RuntimeError):
            process_playlist(
                plan,
                crashing_processor,
                artifact_root=self.artifact_root,
                checkpoint_writer=persisted.append,
            )
        self.assertEqual(calls, ["video-a", "video-b"])
        self.assertEqual(len(persisted), 1)
        self.assertEqual(
            [item["video_id"] for item in persisted[0]["completed"]], ["video-a"]
        )

        def resumed_processor(item: dict) -> dict:
            calls.append(item["video_id"])
            return self.result(item)

        complete = process_playlist(
            plan,
            resumed_processor,
            persisted[0],
            artifact_root=self.artifact_root,
            checkpoint_writer=persisted.append,
        )
        self.assertEqual(complete["status"], "COMPLETE")
        self.assertEqual(calls, ["video-a", "video-b", "video-b"])

    def test_missing_or_changed_artifact_never_becomes_verified_completion(self) -> None:
        discovery = discover_playlist(self.load("snapshot_initial.json"))
        plan = build_playlist_plan(discovery, ["video-a"])
        with self.assertRaises(PlaylistError):
            process_playlist(
                plan,
                lambda _item: {"relative_path": "missing.bin"},
                artifact_root=self.artifact_root,
                checkpoint_writer=self.persisted.append,
            )
        checkpoint = process_playlist(
            plan,
            self.result,
            artifact_root=self.artifact_root,
            checkpoint_writer=self.persisted.append,
        )
        (self.artifact_root / checkpoint["completed"][0]["relative_path"]).write_bytes(
            b"changed"
        )
        with self.assertRaises(PlaylistError):
            process_playlist(
                plan,
                self.result,
                checkpoint,
                artifact_root=self.artifact_root,
                checkpoint_writer=self.persisted.append,
            )

    def test_unsafe_artifact_paths_symlinks_and_hardlinks_fail_closed(self) -> None:
        discovery = discover_playlist(self.load("snapshot_initial.json"))
        plan = build_playlist_plan(discovery, ["video-a"])
        for relative_path in ("../escape.bin", "/absolute.bin", "a//b.bin"):
            with self.subTest(relative_path=relative_path), self.assertRaises(
                PlaylistError
            ):
                process_playlist(
                    plan,
                    lambda _item, path=relative_path: {"relative_path": path},
                    artifact_root=self.artifact_root,
                    checkpoint_writer=self.persisted.append,
                )
        (self.artifact_root / "target.bin").write_bytes(b"target")
        os.symlink("target.bin", self.artifact_root / "link.bin")
        with self.assertRaises(PlaylistError):
            process_playlist(
                plan,
                lambda _item: {"relative_path": "link.bin"},
                artifact_root=self.artifact_root,
                checkpoint_writer=self.persisted.append,
            )
        os.link(self.artifact_root / "target.bin", self.artifact_root / "hard.bin")
        with self.assertRaises(PlaylistError):
            process_playlist(
                plan,
                lambda _item: {"relative_path": "target.bin"},
                artifact_root=self.artifact_root,
                checkpoint_writer=self.persisted.append,
            )

    def test_symlinked_artifact_root_and_reused_path_fail_closed(self) -> None:
        discovery = discover_playlist(self.load("snapshot_initial.json"))
        plan = build_playlist_plan(discovery, ["video-a"])
        external = self.artifact_root / "external"
        external.mkdir()
        (external / "shared.bin").write_bytes(b"shared")
        symlink_root = self.artifact_root / "root-link"
        os.symlink(external, symlink_root)
        with self.assertRaises(PlaylistError):
            process_playlist(
                plan,
                lambda _item: {"relative_path": "shared.bin"},
                artifact_root=symlink_root,
                checkpoint_writer=self.persisted.append,
            )

        two_item_plan = build_playlist_plan(discovery, ["video-a", "video-b"])
        with self.assertRaises(PlaylistError):
            process_playlist(
                two_item_plan,
                lambda _item: {"relative_path": "external/shared.bin"},
                artifact_root=self.artifact_root,
                checkpoint_writer=self.persisted.append,
            )

    def test_refresh_reports_add_remove_reorder_and_access_change(self) -> None:
        old = discover_playlist(self.load("snapshot_initial.json"))
        new = discover_playlist(self.load("snapshot_refreshed.json"))
        plan = build_playlist_plan(old, ["video-a"])
        checkpoint = process_playlist(
            plan,
            self.result,
            artifact_root=self.artifact_root,
            checkpoint_writer=self.persisted.append,
        )
        diff = diff_playlist_refresh(
            old, new, checkpoint, artifact_root=self.artifact_root
        )
        self.assertEqual(diff["added_video_ids"], ["video-d"])
        self.assertEqual(diff["removed_video_ids"], ["video-c"])
        self.assertEqual(diff["reordered_video_ids"], ["video-a", "video-b"])
        self.assertEqual(diff["became_inaccessible_video_ids"], ["video-a"])
        self.assertEqual(diff["retained_completed_evidence"], checkpoint["completed"])
        validate_refresh(old, new, diff, artifact_root=self.artifact_root)
        forged = copy.deepcopy(diff)
        forged["added_video_ids"] = ["forged"]
        with self.assertRaises(PlaylistError):
            validate_refresh(old, new, forged, artifact_root=self.artifact_root)

    def test_removed_remote_item_keeps_local_completed_evidence(self) -> None:
        old = discover_playlist(self.load("snapshot_initial.json"))
        new = discover_playlist(self.load("snapshot_refreshed.json"))
        plan = build_playlist_plan(old, ["video-a"])
        checkpoint = process_playlist(
            plan,
            self.result,
            artifact_root=self.artifact_root,
            checkpoint_writer=self.persisted.append,
        )
        diff = diff_playlist_refresh(
            old, new, checkpoint, artifact_root=self.artifact_root
        )
        self.assertEqual(
            diff["retained_completed_evidence"][0]["video_id"], "video-a"
        )

    def test_refresh_rejects_tampered_retained_evidence(self) -> None:
        old = discover_playlist(self.load("snapshot_initial.json"))
        new = discover_playlist(self.load("snapshot_refreshed.json"))
        plan = build_playlist_plan(old, ["video-a"])
        checkpoint = process_playlist(
            plan,
            self.result,
            artifact_root=self.artifact_root,
            checkpoint_writer=self.persisted.append,
        )
        checkpoint["completed"][0]["content_sha256"] = "0" * 64
        checkpoint["checkpoint_sha256"] = hashlib.sha256(
            json.dumps(
                {key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        with self.assertRaises(PlaylistError):
            diff_playlist_refresh(
                old, new, checkpoint, artifact_root=self.artifact_root
            )

    def test_checkpoint_collection_types_fail_closed(self) -> None:
        discovery = discover_playlist(self.load("snapshot_initial.json"))
        plan = build_playlist_plan(discovery)
        checkpoint = process_playlist(
            plan,
            self.result,
            artifact_root=self.artifact_root,
            checkpoint_writer=self.persisted.append,
            max_new_items=1,
        )
        checkpoint["completed"] = "not-a-list"
        with self.assertRaises(PlaylistError):
            validate_checkpoint(plan, checkpoint, self.artifact_root)

    def test_boolean_numeric_values_and_invalid_timestamp_fail_closed(self) -> None:
        raw = self.load("snapshot_initial.json")
        raw["items"][0]["duration_seconds"] = True
        with self.assertRaises(PlaylistError):
            discover_playlist(raw)
        raw = self.load("snapshot_initial.json")
        raw["fetched_at"] = "not-a-timestampZ"
        with self.assertRaises(PlaylistError):
            discover_playlist(raw)
        discovery = discover_playlist(self.load("snapshot_initial.json"))
        plan = build_playlist_plan(discovery, ["video-a"])
        with self.assertRaises(PlaylistError):
            process_playlist(
                plan,
                self.result,
                artifact_root=self.artifact_root,
                checkpoint_writer=self.persisted.append,
                max_new_items=True,
            )

    def test_refresh_rejects_tampered_retained_size_and_provenance(self) -> None:
        old = discover_playlist(self.load("snapshot_initial.json"))
        new = discover_playlist(self.load("snapshot_refreshed.json"))
        plan = build_playlist_plan(old, ["video-a"])
        checkpoint = process_playlist(
            plan,
            self.result,
            artifact_root=self.artifact_root,
            checkpoint_writer=self.persisted.append,
        )
        for field, value in (("size_bytes", -1), ("provenance_status", "ASSUMED")):
            changed = copy.deepcopy(checkpoint)
            changed["completed"][0][field] = value
            changed["checkpoint_sha256"] = hashlib.sha256(
                json.dumps(
                    {key: item for key, item in changed.items() if key != "checkpoint_sha256"},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            with self.subTest(field=field), self.assertRaises(PlaylistError):
                diff_playlist_refresh(
                    old, new, changed, artifact_root=self.artifact_root
                )

    def test_duplicate_remote_item_and_noncontiguous_order_fail(self) -> None:
        raw = self.load("snapshot_initial.json")
        raw["items"][1]["video_id"] = raw["items"][0]["video_id"]
        with self.assertRaises(PlaylistError):
            discover_playlist(raw)
        raw = self.load("snapshot_initial.json")
        raw["items"][1]["position"] = 7
        with self.assertRaises(PlaylistError):
            discover_playlist(raw)


if __name__ == "__main__":
    unittest.main()
