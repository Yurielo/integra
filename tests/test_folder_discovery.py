import os
from pathlib import Path
import tempfile
import unittest

from integra_core.folder_discovery import FolderDiscoveryError, discover_folder_sources


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


if __name__ == "__main__":
    unittest.main()
