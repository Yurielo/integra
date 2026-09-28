import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from integra_core.seminartext_runtime import ENTRYPOINT_SHA256, PINNED_COMMIT, generate_topics, preflight


class SeminarTextRuntimeTests(unittest.TestCase):
    def test_preflight_requires_bundled_or_explicit_runtime_configuration(self):
        with patch.dict(os.environ, {}, clear=True), patch("integra_core.seminartext_runtime.BUNDLED_RUNTIME_ROOT", Path("/missing")):
            with self.assertRaisesRegex(ValueError, "not configured"):
                preflight()

    def test_preflight_rejects_unpinned_checkout_before_model_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            with patch.dict(os.environ, {"INTEGRA_SEMINARTEXT_CHECKOUT": str(checkout), "INTEGRA_SEMINARTEXT_TOPIC_MODEL": "model"}, clear=True):
                with self.assertRaisesRegex(ValueError, "cannot be verified"):
                    preflight()

    def test_preflight_reports_verified_pinned_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); checkout = root / "checkout"; entrypoint = checkout / "seminartext_modules" / "seminartext_topics.py"
            entrypoint.parent.mkdir(parents=True); entrypoint.write_text("# pinned")
            git = root / "git"; git.write_text(f"#!/bin/sh\necho {PINNED_COMMIT}\n"); git.chmod(git.stat().st_mode | stat.S_IXUSR)
            ollama = root / "ollama"; ollama.write_text("#!/bin/sh\nprintf 'NAME ID SIZE MODIFIED\\ngemma3:4b id size now\\n'\n"); ollama.chmod(ollama.stat().st_mode | stat.S_IXUSR)
            environment = {"INTEGRA_SEMINARTEXT_CHECKOUT": str(checkout), "INTEGRA_SEMINARTEXT_TOPIC_MODEL": "gemma3:4b", "PATH": str(root)}
            with patch.dict(os.environ, environment, clear=True), \
                 patch("integra_core.seminartext_runtime._entrypoint_is_exact", return_value=True):
                result = preflight()
        self.assertEqual(result["commit_sha"], PINNED_COMMIT)
        self.assertEqual(result["model"], "gemma3:4b")

    def test_preflight_accepts_exact_bundled_personal_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); entrypoint = root / "seminartext_modules" / "seminartext_topics.py"
            entrypoint.parent.mkdir(parents=True); entrypoint.write_text("# bundled")
            ollama = root / "ollama"; ollama.write_text("#!/bin/sh\nprintf 'NAME ID SIZE MODIFIED\\ngemma3:4b id size now\\n'"); ollama.chmod(ollama.stat().st_mode | stat.S_IXUSR)
            with patch.dict(os.environ, {"PATH":str(root)}, clear=True), \
                 patch("integra_core.seminartext_runtime.BUNDLED_RUNTIME_ROOT", root), \
                 patch("integra_core.seminartext_runtime._entrypoint_is_exact", return_value=True):
                result = preflight()
        self.assertEqual(result["origin"], "BUNDLED_PERSONAL_RUNTIME")
        self.assertEqual(result["commit_sha"], PINNED_COMMIT)

    def test_generate_topics_accepts_only_review_required_drafts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); subtitles = root / "input.srt"; output = root / "topics.json"
            subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nРусский текст\n", encoding="utf-8")

            def fake_worker(command, **_kwargs):
                destination = Path(command[command.index("--output") + 1])
                destination.write_text(json.dumps({"component":"seminartext", "detail":"auto", "topics":[{"semantic_status":"REVIEW_REQUIRED"}]}), encoding="utf-8")
                return __import__("subprocess").CompletedProcess(command, 0, "", "")

            with patch("integra_core.seminartext_runtime.preflight", return_value={"commit_sha": PINNED_COMMIT, "checkout":"/pinned", "model":"gemma3:4b"}), \
                 patch("integra_core.seminartext_runtime.subprocess.run", side_effect=fake_worker):
                result = generate_topics(subtitles, output)
                persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["runtime"], {"commit_sha": PINNED_COMMIT, "model":"gemma3:4b"})
            self.assertEqual(result["topic_detail"], {"requested":"auto", "executed":"auto"})
            self.assertEqual(persisted["topics"][0]["semantic_status"], "REVIEW_REQUIRED")

    def test_generate_topics_passes_the_requested_detail_and_rejects_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); subtitles = root / "input.srt"; output = root / "topics.json"
            subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nРусский текст\n", encoding="utf-8")

            def fake_worker(command, **_kwargs):
                self.assertEqual(command[command.index("--detail") + 1], "high")
                destination = Path(command[command.index("--output") + 1])
                destination.write_text(json.dumps({"component":"seminartext", "detail":"low", "topics":[{"semantic_status":"REVIEW_REQUIRED"}]}), encoding="utf-8")
                return __import__("subprocess").CompletedProcess(command, 0, "", "")

            with patch("integra_core.seminartext_runtime.preflight", return_value={"commit_sha": PINNED_COMMIT, "checkout":"/pinned", "model":"gemma3:4b"}), \
                 patch("integra_core.seminartext_runtime.subprocess.run", side_effect=fake_worker):
                with self.assertRaisesRegex(ValueError, "detail provenance"):
                    generate_topics(subtitles, output, detail="high")

    def test_generate_topics_rejects_semantically_accepted_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); subtitles = root / "input.srt"; output = root / "topics.json"
            subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nРусский текст\n", encoding="utf-8")

            def fake_worker(command, **_kwargs):
                destination = Path(command[command.index("--output") + 1])
                destination.write_text(json.dumps({"component":"seminartext", "topics":[{"semantic_status":"ACCEPTED"}]}), encoding="utf-8")
                return __import__("subprocess").CompletedProcess(command, 0, "", "")

            with patch("integra_core.seminartext_runtime.preflight", return_value={"commit_sha": PINNED_COMMIT, "checkout":"/pinned", "model":"gemma3:4b"}), \
                 patch("integra_core.seminartext_runtime.subprocess.run", side_effect=fake_worker):
                with self.assertRaisesRegex(ValueError, "semantic status"):
                    generate_topics(subtitles, output)


if __name__ == "__main__": unittest.main()
