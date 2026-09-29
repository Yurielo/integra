import os
from pathlib import Path
import tempfile
import unittest

from integra_core.folder_discovery import (
    FolderDiscoveryError,
    discover_folder_sources,
    discover_zoom_folder_sources,
)


class FolderDiscoveryTests(unittest.TestCase):
    def test_discovers_only_top_level_supported_files_in_deterministic_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "zeta.wav").write_bytes(b"zeta")
            (root / "Alpha.mp3").write_bytes(b"alpha")
            (root / "notes.md").write_text("notes", encoding="utf-8")
            (root / "unsupported.bin").write_bytes(b"ignored")
            (root / ".DS_Store").write_bytes(b"hidden")
            nested = root / "nested"; nested.mkdir(); (nested / "inside.wav").write_bytes(b"inside")
            result = discover_folder_sources(str(root))
        self.assertFalse(result["recursive"])
        self.assertEqual([item["display_name"] for item in result["sources"]], ["Alpha.mp3", "notes.md", "zeta.wav"])
        self.assertEqual([item["folder_discovery"]["ordinal"] for item in result["sources"]], [1, 2, 3])
        self.assertEqual({item["reason"] for item in result["ignored"]}, {"HIDDEN", "NOT_REGULAR_FILE", "UNSUPPORTED"})

    def test_deduplicates_equal_content_and_preserves_first_displayed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.wav").write_bytes(b"same")
            (root / "b.wav").write_bytes(b"same")
            result = discover_folder_sources(str(root))
        self.assertEqual([item["display_name"] for item in result["sources"]], ["a.wav"])
        self.assertEqual(result["ignored"], [{"name": "b.wav", "reason": "DUPLICATE_CONTENT"}])

    def test_rejects_symlink_and_non_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); file = root / "file.wav"; file.write_bytes(b"audio")
            with self.assertRaisesRegex(FolderDiscoveryError, "accessible local folder"):
                discover_folder_sources(str(file))
            link = root / "folder-link"; os.symlink(root, link)
            with self.assertRaisesRegex(FolderDiscoveryError, "accessible local folder"):
                discover_folder_sources(str(link))

    def test_zoom_selects_audio_only_then_audio_then_video_per_recording_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Zoom Meeting"; root.mkdir()
            (root / "zoom_0.mp4").write_bytes(b"video" * 4)
            (root / "audio_only.m4a").write_bytes(b"audio")
            second = root / "part-02"; second.mkdir()
            (second / "small.wav").write_bytes(b"a")
            (second / "large.mp3").write_bytes(b"b" * 8)
            third = root / "part-03"; third.mkdir()
            (third / "zoom_1.mp4").write_bytes(b"v" * 5)
            (third / "zoom_2.mp4").write_bytes(b"v" * 7)
            fourth = root / "part-04"; fourth.mkdir()
            (fourth / "zoom_3.avi").write_bytes(b"v" * 9)
            (fourth / "zoom_4.opus").write_bytes(b"a" * 11)
            (fourth / "not_s07.aiff").write_bytes(b"x" * 30)
            (root / "recording.conf").write_text("config", encoding="utf-8")
            ignored = root / "participants"; ignored.mkdir(); (ignored / "person.mp3").write_bytes(b"x" * 20)
            result = discover_zoom_folder_sources(str(root))
        self.assertTrue(result["recursive"])
        self.assertEqual(result["recognition"], "ZOOM_RECORDING_FOLDER_S07")
        self.assertEqual([item["display_name"] for item in result["sources"]], [
            "audio_only.m4a", "large.mp3", "zoom_2.mp4", "zoom_4.opus",
        ])
        self.assertEqual([item["zoom_discovery"]["ordinal"] for item in result["sources"]], [1, 2, 3, 4])
        self.assertTrue(all(item["zoom_discovery"]["recursive"] for item in result["sources"]))
        self.assertIn({"name": "recording.conf", "reason": "UNSUPPORTED"}, result["ignored"])
        self.assertIn({"name": "zoom_0.mp4", "reason": "SECONDARY_REPRESENTATION"}, result["ignored"])
        self.assertNotIn("person.mp3", [item["name"] for item in result["ignored"]])

    def test_zoom_rejects_empty_and_retains_distinct_recording_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(FolderDiscoveryError, "accessible local folder"):
                discover_zoom_folder_sources(str(root / "missing"))
            first = root / "a"; second = root / "b"; first.mkdir(); second.mkdir()
            (first / "audio_only.m4a").write_bytes(b"same")
            (second / "audio_only.m4a").write_bytes(b"same")
            result = discover_zoom_folder_sources(str(root))
        self.assertEqual([item["display_name"] for item in result["sources"]], [
            "audio_only.m4a", "audio_only.m4a",
        ])
        self.assertEqual(
            [item["zoom_discovery"]["recording_directory"] for item in result["sources"]],
            ["a", "b"],
        )


if __name__ == "__main__":
    unittest.main()
