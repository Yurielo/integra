import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integra_core.documents import extract_document
from integra_core.identity import derive_imported_id
from integra_core.playlist import discover_playlist
from integra_core.protocol import content_sha256
from integra_core.projects_sources import (
    RegistryError,
    dumps_registry,
    loads_registry,
    new_registry,
    register_document,
    register_local_media,
    register_project,
    register_youtube_playlist,
    register_youtube_video,
    update_project,
    validate_registry,
)


ROOT = Path(__file__).resolve().parents[1]
PLAYLIST_FIXTURE = ROOT / "tests" / "fixtures" / "playlist_v1" / "snapshot_initial.json"
T0 = "2026-09-11T00:00:00Z"
T1 = "2026-09-11T00:01:00Z"
T2 = "2026-09-11T00:02:00Z"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
    "0000000a49444154789c636000000002000148afa4710000000049454e44ae426082"
)
WAV = b"RIFF\x08\x00\x00\x00WAVEfmt "


class ProjectSourceRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        registry = new_registry("local-user", T0)
        self.registry, self.project_id = register_project(
            registry, project_key="seminar-2026", kind="SEMINAR",
            title="Seminar 2026", occurred_at=T0,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_project_kinds_identity_history_and_lifecycle(self) -> None:
        registry = new_registry("types", T0)
        ids = []
        for index, kind in enumerate(("SEMINAR", "COURSE", "SERIES", "EVENT")):
            registry, project_id = register_project(
                registry, project_key=f"project-{index}", kind=kind,
                title=kind.title(), occurred_at=T0,
            )
            ids.append(project_id)
        self.assertEqual(len(set(ids)), 4)
        changed = update_project(
            registry, ids[0], occurred_at=T1, title="Renamed", lifecycle="ARCHIVED"
        )
        project = next(item for item in changed["projects"] if item["project_id"] == ids[0])
        self.assertEqual(project["revision"], 3)
        self.assertEqual(
            [event["event_type"] for event in project["history"]],
            ["CREATED", "RENAMED", "LIFECYCLE_CHANGED"],
        )
        validate_registry(changed)

    def test_reopening_project_is_idempotent(self) -> None:
        reopened, project_id = register_project(
            loads_registry(dumps_registry(self.registry)),
            project_key="seminar-2026", kind="SEMINAR", title="Ignored display rename",
            occurred_at=T1,
        )
        self.assertEqual(project_id, self.project_id)
        self.assertEqual(reopened, self.registry)
        self.assertEqual(len(reopened["projects"]), 1)

    def test_local_audio_and_video_use_bytes_not_path_for_identity(self) -> None:
        first = self.root / "lesson.wav"
        second = self.root / "renamed.wav"
        first.write_bytes(WAV)
        second.write_bytes(first.read_bytes())
        registry, source_id = register_local_media(
            self.registry, self.project_id, first, captured_at=T1
        )
        refreshed, moved_id = register_local_media(
            registry, self.project_id, second, captured_at=T2
        )
        self.assertEqual(source_id, moved_id)
        self.assertEqual(len(refreshed["sources"]), 1)
        self.assertEqual(len(refreshed["sources"][0]["revisions"]), 2)
        self.assertEqual(refreshed["sources"][0]["source_type"], "LOCAL_AUDIO")
        self.assertEqual(first.read_bytes(), WAV)
        video = self.root / "clip.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isom")
        with_video, _ = register_local_media(
            refreshed, self.project_id, video, captured_at=T2
        )
        self.assertEqual(
            {source["source_type"] for source in with_video["sources"]},
            {"LOCAL_AUDIO", "LOCAL_VIDEO"},
        )

    def test_unavailable_or_unsupported_local_source_fails_visibly(self) -> None:
        with self.assertRaisesRegex(RegistryError, "available regular"):
            register_local_media(
                self.registry, self.project_id, self.root / "missing.mp4", captured_at=T1
            )
        unsupported = self.root / "source.exe"
        unsupported.write_bytes(b"payload")
        with self.assertRaisesRegex(RegistryError, "unsupported"):
            register_local_media(
                self.registry, self.project_id, unsupported, captured_at=T1
            )

    def test_individual_youtube_video_is_independent_and_resumable(self) -> None:
        registry, source_id = register_youtube_video(
            self.registry, self.project_id, video_id="video-a", title="Lesson A",
            availability="AVAILABLE", captured_at=T1,
        )
        reopened = loads_registry(dumps_registry(registry))
        refreshed, same_id = register_youtube_video(
            reopened, self.project_id, video_id="video-a", title="Lesson A renamed",
            availability="AVAILABLE", captured_at=T2,
        )
        self.assertEqual(source_id, same_id)
        self.assertEqual(len(refreshed["sources"]), 1)
        self.assertEqual(len(refreshed["sources"][0]["revisions"]), 2)
        self.assertEqual(refreshed["sources"][0]["display_name"], "Lesson A renamed")

    def test_inaccessible_youtube_video_is_explicit_not_fabricated(self) -> None:
        registry, _ = register_youtube_video(
            self.registry, self.project_id, video_id="private", title="Unavailable",
            availability="INACCESSIBLE", captured_at=T1,
        )
        source = registry["sources"][0]
        self.assertEqual(source["lifecycle"], "UNAVAILABLE")
        self.assertEqual(source["revisions"][0]["availability"], "INACCESSIBLE")
        self.assertEqual(
            source["revisions"][0]["provenance"]["canonical_url"],
            "https://www.youtube.com/watch?v=private",
        )

    def test_playlist_reuses_individual_video_source_contract(self) -> None:
        raw = json.loads(PLAYLIST_FIXTURE.read_text(encoding="utf-8"))
        discovery = discover_playlist(raw)
        registry, standalone_id = register_youtube_video(
            self.registry, self.project_id, video_id="video-a", title="Fixture lesson A",
            availability="AVAILABLE", captured_at=T1,
        )
        registry, playlist_id, video_ids = register_youtube_playlist(
            registry, self.project_id, discovery, captured_at=T2
        )
        self.assertEqual(playlist_id, discovery["collection_id"])
        self.assertEqual(standalone_id, discovery["items"][0]["video_source_id"])
        self.assertIn(standalone_id, video_ids)
        self.assertEqual(len(registry["sources"]), 4)

    def test_unchanged_playlist_refresh_is_idempotent(self) -> None:
        discovery = discover_playlist(
            json.loads(PLAYLIST_FIXTURE.read_text(encoding="utf-8"))
        )
        first, _, _ = register_youtube_playlist(
            self.registry, self.project_id, discovery, captured_at=T1
        )
        second, _, _ = register_youtube_playlist(
            loads_registry(dumps_registry(first)), self.project_id,
            discovery, captured_at=T1,
        )
        self.assertEqual(first, second)

    def test_one_video_can_retain_two_same_time_playlist_memberships(self) -> None:
        first_raw = json.loads(PLAYLIST_FIXTURE.read_text(encoding="utf-8"))
        second_raw = copy.deepcopy(first_raw)
        second_raw["playlist_native_id"] = "PL-SECOND-FIXTURE"
        first = discover_playlist(first_raw)
        second = discover_playlist(second_raw)
        registry, _, _ = register_youtube_playlist(
            self.registry, self.project_id, first, captured_at=T1
        )
        registry, _, _ = register_youtube_playlist(
            registry, self.project_id, second, captured_at=T1
        )
        video = next(
            source for source in registry["sources"]
            if source["source_id"] == first["items"][0]["video_source_id"]
        )
        self.assertEqual(len(video["memberships"]), 2)
        self.assertEqual(
            {item["collection_id"] for item in video["memberships"]},
            {first["collection_id"], second["collection_id"]},
        )
        self.assertTrue(
            all(
                {"snapshot_id", "position", "duration_seconds"}.issubset(item)
                for item in video["memberships"]
            )
        )

    def test_playlist_membership_removal_breaks_reciprocal_index(self) -> None:
        discovery = discover_playlist(
            json.loads(PLAYLIST_FIXTURE.read_text(encoding="utf-8"))
        )
        registry, _, _ = register_youtube_playlist(
            self.registry, self.project_id, discovery, captured_at=T1
        )
        tampered = copy.deepcopy(registry)
        video = next(source for source in tampered["sources"] if source["memberships"])
        video["memberships"].clear()
        tampered["record_sha256"] = ""
        tampered["record_sha256"] = content_sha256(tampered)
        with self.assertRaisesRegex(RegistryError, "membership index"):
            validate_registry(tampered)

    def test_same_content_with_conflicting_media_type_fails_closed(self) -> None:
        wav = self.root / "source.m4a"
        mp3 = self.root / "source.mp4"
        wav.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isom")
        mp3.write_bytes(wav.read_bytes())
        registry, _ = register_local_media(
            self.registry, self.project_id, wav, captured_at=T1
        )
        with self.assertRaisesRegex(RegistryError, "identity conflict"):
            register_local_media(registry, self.project_id, mp3, captured_at=T2)

    def test_document_pipeline_record_is_reused_without_reextracting(self) -> None:
        source_path = self.root / "notes.md"
        source_path.write_text("# Notes\n\nExact supporting material.", encoding="utf-8")
        document = extract_document(source_path, captured_at=T1)
        registry, source_id = register_document(
            self.registry, self.project_id, document, captured_at=T1
        )
        self.assertEqual(source_id, document["source"]["source_id"])
        self.assertEqual(registry["sources"][0]["source_type"], "MARKDOWN")
        self.assertEqual(
            registry["sources"][0]["revisions"][0]["provenance"]["document_id"],
            document["document_id"],
        )

    def test_renamed_document_keeps_source_identity_and_revision_lineage(self) -> None:
        first = self.root / "first.md"
        second = self.root / "second.md"
        first.write_text("same material", encoding="utf-8")
        second.write_bytes(first.read_bytes())
        registry, first_id = register_document(
            self.registry, self.project_id,
            extract_document(first, captured_at=T1), captured_at=T1,
        )
        registry, second_id = register_document(
            registry, self.project_id,
            extract_document(second, captured_at=T2), captured_at=T2,
        )
        self.assertEqual(first_id, second_id)
        self.assertEqual(len(registry["sources"]), 1)
        self.assertEqual(len(registry["sources"][0]["revisions"]), 2)
        self.assertEqual(registry["sources"][0]["display_name"], "second.md")

    def test_image_and_scan_roles_are_explicit(self) -> None:
        image_path = self.root / "support.png"
        image_path.write_bytes(PNG)
        document = extract_document(image_path, captured_at=T1)
        image_registry, _ = register_document(
            self.registry, self.project_id, document,
            captured_at=T1, image_role="IMAGE",
        )
        self.assertEqual(image_registry["sources"][0]["source_type"], "IMAGE")
        scan_registry, _ = register_document(
            self.registry, self.project_id, document,
            captured_at=T1, image_role="SCAN",
        )
        self.assertEqual(scan_registry["sources"][0]["source_type"], "SCAN")
        notes = self.root / "notes.txt"
        notes.write_text("text", encoding="utf-8")
        with self.assertRaisesRegex(RegistryError, "applies only"):
            register_document(
                self.registry, self.project_id,
                extract_document(notes, captured_at=T1), captured_at=T1,
                image_role="IMAGE",
            )

    def test_same_source_can_be_attached_to_two_projects_without_duplication(self) -> None:
        registry, second_project = register_project(
            self.registry, project_key="course-2026", kind="COURSE",
            title="Course", occurred_at=T1,
        )
        registry, first_id = register_youtube_video(
            registry, self.project_id, video_id="shared", title="Shared",
            availability="AVAILABLE", captured_at=T1,
        )
        registry, second_id = register_youtube_video(
            registry, second_project, video_id="shared", title="Shared",
            availability="AVAILABLE", captured_at=T2,
        )
        self.assertEqual(first_id, second_id)
        self.assertEqual(len(registry["sources"]), 1)
        self.assertEqual(len(registry["sources"][0]["project_ids"]), 2)

    def test_hash_and_identity_tampering_fail_closed(self) -> None:
        registry, _ = register_youtube_video(
            self.registry, self.project_id, video_id="video-a", title="Lesson",
            availability="AVAILABLE", captured_at=T1,
        )
        for mutation in ("record_hash", "source_identity", "relationship"):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(registry)
                if mutation == "record_hash":
                    changed["record_sha256"] = "0" * 64
                elif mutation == "source_identity":
                    changed["sources"][0]["identity_sha256"] = "0" * 64
                    changed["record_sha256"] = ""
                    changed["record_sha256"] = content_sha256(changed)
                else:
                    changed["projects"][0]["source_ids"] = []
                    changed["record_sha256"] = ""
                    changed["record_sha256"] = content_sha256(changed)
                with self.assertRaises(RegistryError):
                    validate_registry(changed)

    def test_bad_timestamp_unknown_project_and_invalid_availability_fail(self) -> None:
        with self.assertRaises(RegistryError):
            new_registry("local", "2026-09-11")
        with self.assertRaisesRegex(RegistryError, "not registered"):
            register_youtube_video(
                self.registry, "urn:integra:project:00000000-0000-0000-0000-000000000000",
                video_id="v", title="V", availability="AVAILABLE", captured_at=T1,
            )
        with self.assertRaisesRegex(RegistryError, "availability"):
            register_youtube_video(
                self.registry, self.project_id, video_id="v", title="V",
                availability="UNKNOWN", captured_at=T1,
            )

    def test_source_refresh_changes_lifecycle_without_duplicate_identity(self) -> None:
        registry, source_id = register_youtube_video(
            self.registry, self.project_id, video_id="v", title="V",
            availability="AVAILABLE", captured_at=T1,
        )
        registry, refreshed_id = register_youtube_video(
            registry, self.project_id, video_id="v", title="V unavailable",
            availability="INACCESSIBLE", captured_at=T2,
        )
        self.assertEqual(source_id, refreshed_id)
        self.assertEqual(len(registry["sources"]), 1)
        self.assertEqual(registry["sources"][0]["lifecycle"], "UNAVAILABLE")
        self.assertEqual(len(registry["sources"][0]["revisions"]), 2)

    def test_symlink_media_is_not_followed(self) -> None:
        target = self.root / "target.wav"
        link = self.root / "link.wav"
        target.write_bytes(WAV)
        link.symlink_to(target)
        with self.assertRaisesRegex(RegistryError, "non-symlink"):
            register_local_media(self.registry, self.project_id, link, captured_at=T1)

    def test_ancestor_swap_during_hashing_fails_closed(self) -> None:
        safe = self.root / "safe"
        held = self.root / "held"
        outside = self.root / "outside"
        safe.mkdir()
        outside.mkdir()
        source = safe / "clip.wav"
        source.write_bytes(WAV)
        (outside / "clip.wav").write_bytes(b"RIFF\x08\x00\x00\x00WAVEevil")
        original_read = __import__("os").read
        swapped = False

        def swapping_read(descriptor: int, size: int) -> bytes:
            nonlocal swapped
            payload = original_read(descriptor, size)
            if payload and not swapped:
                safe.rename(held)
                safe.symlink_to(outside, target_is_directory=True)
                swapped = True
            return payload

        with patch("integra_core.projects_sources.os.read", side_effect=swapping_read):
            with self.assertRaisesRegex(RegistryError, "changed during fingerprinting"):
                register_local_media(
                    self.registry, self.project_id, source, captured_at=T1
                )

    def test_project_history_rewrite_fails_even_with_resealed_record(self) -> None:
        changed = update_project(
            self.registry, self.project_id, occurred_at=T1, title="Renamed"
        )
        tampered = copy.deepcopy(changed)
        event = tampered["projects"][0]["history"][1]
        event["details"]["from"] = "Fabricated"
        identity = content_sha256(
            {
                "project_id": self.project_id, "ordinal": 2,
                "event_type": event["event_type"], "occurred_at": event["occurred_at"],
                "details": event["details"],
            }
        )
        event["event_id"] = derive_imported_id(
            "artifact", "integra.project_history", f"{self.project_id}:2", identity
        )
        tampered["record_sha256"] = ""
        tampered["record_sha256"] = content_sha256(tampered)
        with self.assertRaisesRegex(RegistryError, "rename history"):
            validate_registry(tampered)

    def test_source_revision_deletion_breaks_hash_chain(self) -> None:
        registry, _ = register_youtube_video(
            self.registry, self.project_id, video_id="chain", title="First",
            availability="AVAILABLE", captured_at=T1,
        )
        registry, _ = register_youtube_video(
            registry, self.project_id, video_id="chain", title="Second",
            availability="AVAILABLE", captured_at=T2,
        )
        tampered = copy.deepcopy(registry)
        source = tampered["sources"][0]
        source["revisions"].pop(0)
        source["current_revision_id"] = source["revisions"][-1]["revision_id"]
        tampered["record_sha256"] = ""
        tampered["record_sha256"] = content_sha256(tampered)
        with self.assertRaises(RegistryError):
            validate_registry(tampered)

    def test_invalid_media_container_signatures_fail_visibly(self) -> None:
        for suffix in (".mp4", ".wav", ".mp3", ".flac", ".aac", ".mkv"):
            with self.subTest(suffix=suffix):
                source = self.root / f"fake{suffix}"
                source.write_bytes(b"plain text is not media")
                with self.assertRaisesRegex(RegistryError, "signature"):
                    register_local_media(
                        self.registry, self.project_id, source, captured_at=T1
                    )


if __name__ == "__main__":
    unittest.main()
