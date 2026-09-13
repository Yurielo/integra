import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

from integra_core.transcript_output import resolve_transcript_text

ROOT = Path(__file__).resolve().parents[1]


class TranscriptOutputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = "source-test"
        self.path = self.root / "transcript.json"
        self.original = json.dumps({"schema_version": "1.0", "source_id": self.source,
            "segments": [{"text": "Первый абзац."}, {"text": "Второй абзац."}]}, ensure_ascii=False).encode()
        self.path.write_bytes(self.original)

    def resolve(self):
        return Path(resolve_transcript_text(self.root, self.source, str(self.path)))

    def test_real_text_is_deterministic_and_original_remains_unchanged(self):
        text = self.resolve()
        self.assertEqual(text.suffix, ".txt")
        self.assertEqual(text.read_text(), "Первый абзац.\nВторой абзац.\n")
        self.assertEqual(self.resolve(), text)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_existing_txt_is_not_rewritten(self):
        text = self.root / "existing.txt"
        text.write_text("Текст без завершающего переноса")
        self.assertEqual(resolve_transcript_text(self.root, self.source, str(text)), str(text))
        self.assertEqual(text.read_text(), "Текст без завершающего переноса")

    def test_edited_projection_is_preserved(self):
        text = self.resolve()
        text.write_text("User edit")
        with self.assertRaisesRegex(ValueError, "no file was overwritten"):
            self.resolve()
        self.assertEqual(text.read_text(), "User edit")

    def test_wrong_source_and_invalid_segments_fail_without_projection(self):
        with self.assertRaisesRegex(ValueError, "identity differs"):
            resolve_transcript_text(self.root, "other", str(self.path))
        record = json.loads(self.original)
        record["segments"] = [{"text": 123}]
        self.path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "segments"):
            self.resolve()
        self.assertFalse((self.root / "transcript-text").exists())

    def test_outside_paths_and_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "outside.txt"
            external.write_text("outside")
            with self.assertRaises(ValueError):
                resolve_transcript_text(self.root, self.source, str(external))
        alias = self.root / "alias.json"
        alias.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            resolve_transcript_text(self.root, self.source, str(alias))
        directory = self.root / "transcript-text"
        directory.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self.resolve()

    def test_bridge_resolves_completed_legacy_result(self):
        project_id = "urn:integra:project:" + str(uuid.uuid4())
        run_id = "urn:integra:run:" + str(uuid.uuid4())
        project = self.root / "projects" / project_id.split(":")[-1]
        (project / "runs").mkdir(parents=True)
        transcript = project / "transcript.json"
        transcript.write_bytes(self.original)
        (project / "project.json").write_text(json.dumps({"project_id": project_id, "name": "Synthetic legacy result", "status": "READY"}))
        (project / "runs" / (run_id.split(":")[-1] + ".json")).write_text(json.dumps({"run_id": run_id,
            "source_results": [{"source_id": self.source, "state": "COMPLETED", "outputs": {"transcript": str(transcript)}}]}))
        bridge = os.environ.get("INTEGRA_TEST_BRIDGE", str(ROOT / "macos/Resources/bridge.py"))
        process = subprocess.run([os.environ.get("INTEGRA_TEST_PYTHON", "python3"), bridge, "transcript-text"],
            input=json.dumps({"project_id": project_id, "run_id": run_id, "source_id": self.source}),
            text=True, capture_output=True, check=True, env={**os.environ, "INTEGRA_APP_DATA_ROOT": str(self.root)})
        result = json.loads(process.stdout)["result"]
        self.assertEqual(result["format"], "txt")
        self.assertEqual(Path(result["path"]).read_text(), "Первый абзац.\nВторой абзац.\n")
        self.assertEqual(transcript.read_bytes(), self.original)

    def test_ui_calls_resolver_instead_of_opening_legacy_path(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        self.assertIn('#selector(openTranscript(_:))', source)
        self.assertIn('bridge.json("transcript-text"', source)


if __name__ == "__main__":
    unittest.main()
