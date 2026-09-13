"""Boundary checks and optional real pinned VideoText media acceptance probes."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from integra_core import videotext_media_runtime as media


def real_media_fixture(path):
    """Synthetic media only; does not perform recognition or access user files."""
    try:
        media.preflight()
    except (ValueError, OSError) as error:
        raise unittest.SkipTest(str(error)) from error
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise unittest.SkipTest("FFmpeg is unavailable")
    if Path(path).suffix == ".wav":
        subprocess.run([ffmpeg,"-nostdin","-v","error","-f","lavfi","-i","sine=frequency=440:sample_rate=48000",
                        "-t","2","-c:a","pcm_s16le",str(path)],check=True,capture_output=True,timeout=30)
        return ffmpeg
    subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True, capture_output=True, timeout=30)
    return ffmpeg


class MediaBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"not-real-media")
        self.output = self.root / "output.mp4"

    def verified_worker(self):
        worker = self.root / "worker"
        worker.write_bytes(b"identity-only-test-fixture")
        worker.chmod(0o700)
        (self.root / "runtime.json").write_text(json.dumps({
            "component": "videotext", "commit_sha": media.COMMIT,
            "media_adapters_sha256": media.MEDIA_SHA256,
            "audio_adapter_sha256": media.AUDIO_SHA256,
            "srt_service_sha256": media.SERVICE_SHA256,
            "worker_sha256": media.digest(worker),
        }))
        environment = patch.dict(os.environ, {"INTEGRA_VIDEOTEXT_MEDIA_WORKER": str(worker)})
        environment.start()
        self.addCleanup(environment.stop)
        return worker

    def tool_availability(self, worker, available):
        original_is_file = Path.is_file
        files = patch.object(Path, "is_file", lambda path:
            str(path) in available or (path.parent == self.root and original_is_file(path)))
        access = patch.object(media.os, "access", side_effect=lambda path, mode:
            Path(path) == worker or str(path) in available)
        for replacement in (files, access):
            replacement.start()
            self.addCleanup(replacement.stop)

    def test_verified_worker_without_either_media_dependency_fails_closed(self):
        worker = self.verified_worker()
        available = set()
        self.tool_availability(worker, available)
        for missing in ("ffmpeg", "ffprobe"):
            with self.subTest(missing=missing):
                available.clear()
                available.update(f"/opt/homebrew/bin/{name}" for name in ("ffmpeg", "ffprobe") if name != missing)
                with self.assertRaisesRegex(ValueError, f"dependency is unavailable: {missing}"):
                    media.preflight()

    def test_tool_resolution_matches_pinned_toolrunner_priority(self):
        worker = self.verified_worker()
        expected = (
            "/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin",
            "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin",
        )
        self.assertEqual(media.MEDIA_TOOL_SEARCH_PATHS, expected)
        available = {f"{prefix}/{name}" for prefix in expected for name in ("ffmpeg", "ffprobe")}
        self.tool_availability(worker, available)
        for prefix in expected:
            with self.subTest(first_available=prefix):
                self.assertEqual(media.preflight()["tools"], {
                    name: f"{prefix}/{name}" for name in ("ffmpeg", "ffprobe")
                })
                available.difference_update(f"{prefix}/{name}" for name in ("ffmpeg", "ffprobe"))

    def test_path_and_integra_override_do_not_claim_component_dependencies(self):
        worker = self.verified_worker()
        custom = self.root / "ffmpeg"
        custom.write_bytes(b"outside-component-search-path")
        custom.chmod(0o700)
        self.tool_availability(worker, {str(custom)})
        with patch.dict(os.environ, {"PATH": str(self.root), "INTEGRA_FFMPEG": str(custom)}):
            with self.assertRaisesRegex(ValueError, "dependency is unavailable: ffmpeg"):
                media.preflight()

    def test_missing_component_dependency_disables_media_capabilities(self):
        from integra_core import capabilities
        worker = self.verified_worker()
        self.tool_availability(worker, {"/opt/homebrew/bin/ffmpeg"})
        source = {"source_type": "LOCAL_VIDEO", "kind": "MEDIA", "properties": {}}
        with ExitStack() as stack:
            # Isolate unrelated adapters while retaining the real component
            # preflight under test (verified worker, missing ffprobe).
            for name in ("preflight", "ffmpeg_preflight", "seminartext_preflight",
                         "word_timeline_preflight", "videotext_preflight"):
                stack.enter_context(patch.object(capabilities, name, return_value={"state": "READY"}))
            registry = {item["id"]: item for item in capabilities.capability_registry([source])}
        for name in ("burn_subtitles", "audio_analysis", "speed_video"):
            self.assertFalse(registry[name]["runtime_available"])
            self.assertIn("ffprobe", registry[name]["ui_state"])
        self.assertTrue(registry["transcript"]["runtime_available"])

    def test_existing_output_and_source_preserved(self):
        self.output.write_bytes(b"user-data")
        with self.assertRaises(FileExistsError):
            media.cut(self.source, self.output, 0, 1)
        with self.assertRaises(FileExistsError):
            media.cut(self.source, self.source, 0, 1)
        self.assertEqual(self.output.read_bytes(), b"user-data")

    def test_invalid_parameters_and_symlinks_fail_before_runtime(self):
        cases = [("clip", {"start_seconds": float("nan"), "end_seconds": 2}),
                 ("clip", {"start_seconds": 3, "end_seconds": 2}),
                 ("clip", {"start_seconds": True, "end_seconds": 2}),
                 ("speed", {"speed_factor": 3}), ("invented", {}),
                 ("audio_analysis", {"speed_factor": 1})]
        for operation, options in cases:
            with self.subTest(operation=operation, options=options), self.assertRaises(ValueError):
                media.process(self.source, self.output, operation, **options)
        link = self.root / "link"; link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            media.cut(link, self.output, 0, 1)
        self.assertFalse(self.output.exists())

    def test_unavailable_or_unverified_runtime_fails_closed(self):
        worker = self.root / "worker"; worker.write_bytes(b"not-executable"); worker.chmod(0o700)
        with patch.dict(os.environ, {"INTEGRA_VIDEOTEXT_MEDIA_WORKER": str(worker)}):
            with self.assertRaises(ValueError): media.preflight()
            (self.root / "runtime.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "identity mismatch"): media.preflight()

    def test_timeout_terminates_process_group(self):
        # Real harmless subprocess exercises process cleanup, not a fake media backend.
        with self.assertRaises(TimeoutError):
            media._execute([sys.executable, "-c", "import time; time.sleep(30)"], self.root, 0.05, None)

    def test_cancellation_terminates_process(self):
        checks = [False, True]
        with self.assertRaises(media.MediaCancelled):
            media._execute([sys.executable, "-c", "import time; time.sleep(30)"], self.root, 10,
                           lambda: checks.pop(0) if checks else True)


class RealVideoTextMediaTests(unittest.TestCase):
    def setUp(self):
        try:
            self.runtime = media.preflight()
        except ValueError as error:
            self.skipTest(str(error))
        self.ffmpeg = shutil.which("ffmpeg")
        if not self.ffmpeg: self.skipTest("FFmpeg is unavailable")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "input.mp4"
        subprocess.run([self.ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=25",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", str(self.source)], check=True, capture_output=True, timeout=30)

    def test_real_clip_speed_and_audio_analysis_preserve_input(self):
        before = media.digest(self.source)
        clipped = media.cut(self.source, self.root / "clip.mp4", 0.2, 1.2, timeout=30)
        self.assertAlmostEqual(clipped["duration_seconds"], 1, delta=0.25)
        fast = media.adjust_speed(self.source, self.root / "fast.mp4", 2, timeout=30)
        self.assertAlmostEqual(fast["duration_seconds"], 1, delta=0.25)
        analysis = media.analyze_audio(self.source, self.root / "analysis.json", timeout=30)
        self.assertEqual(analysis["operation"], "audio_analysis")
        self.assertIn("integratedLoudnessLUFS", json.loads((self.root / "analysis.json").read_text()))
        self.assertEqual(before, media.digest(self.source))

    def test_real_subtitle_burn_and_invalid_input(self):
        srt = self.root / "captions.srt"
        srt.write_text("1\n00:00:00,100 --> 00:00:01,500\nIntegra test\n")
        result = media.burn(self.source, srt, self.root / "burned.mp4", timeout=30)
        self.assertIn("codec_type=video", result["validation"])
        srt.write_text("invalid subtitles")
        with self.assertRaises(ValueError):
            media.burn(self.source, srt, self.root / "invalid.mp4", timeout=30)
        self.assertFalse((self.root / "invalid.mp4").exists())

    def test_real_rejected_range_never_publishes(self):
        with self.assertRaises(ValueError):
            media.cut(self.source, self.root / "invalid.mp4", 1, 20, timeout=30)
        self.assertFalse((self.root / "invalid.mp4").exists())
