"""Real pinned Swift SRTService acceptance and fail-closed adapter checks."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from integra_core import videotext_subtitles as subtitles
from tests.asr_tools import require_subtitle_runtime


class SubtitleBoundaryTests(unittest.TestCase):
    def test_missing_runtime_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"INTEGRA_VIDEOTEXT_SUBTITLE_WORKER": str(Path(directory)/'missing')}):
                with self.assertRaisesRegex(ValueError, 'unavailable'):
                    subtitles.preflight()

    def test_existing_destination_is_preserved_even_without_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source.srt'; source.write_text('source')
            target = root/'target.srt'; target.write_text('user-owned')
            with self.assertRaises(FileExistsError):
                subtitles.normalize(source, target)
            self.assertEqual(target.read_text(), 'user-owned')
            with self.assertRaises(FileExistsError):
                subtitles.normalize(source, source)
            self.assertEqual(source.read_text(), 'source')

    def test_symlink_boundaries_and_unknown_options_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source.srt'; source.write_text('source')
            link = root/'link.srt'; link.symlink_to(source)
            with self.assertRaises(ValueError):
                subtitles.normalize(link, root/'new.srt')
            with self.assertRaises(FileExistsError):
                subtitles.normalize(source, link)
            with self.assertRaises(ValueError):
                subtitles.process(source, root/'new.srt', 'invented')
            with self.assertRaises(ValueError):
                subtitles.process(source, root/'new.srt', imaginary_option=True)
            self.assertFalse((root/'new.srt').exists())


class RealVideoTextSubtitleTests(unittest.TestCase):
    def setUp(self):
        self.runtime = require_subtitle_runtime()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root/'original.srt'
        self.target = self.root/'result.srt'

    def test_unnumbered_unicode_multiline_and_chunk_offsets_use_real_service(self):
        original = ('00:00:00,125 --> 00:00:02,750\r\nПривет, Integra.\r\nSecond line 🎬\r\n\r\n'
                    '00:05:00,000 --> 00:05:01,250\r\nСледующий фрагмент.\r\n\r\n').encode()
        self.source.write_bytes(original)
        result = subtitles.normalize(self.source, self.target)
        self.assertEqual(self.target.read_text(),
            '1\n00:00:00,125 --> 00:00:02,750\nПривет, Integra.\nSecond line 🎬\n\n'
            '2\n00:05:00,000 --> 00:05:01,250\nСледующий фрагмент.\n')
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(result['cue_count'], 2)
        self.assertEqual(result['runtime']['srt_service_sha256'], subtitles.SERVICE_SHA256)
        self.assertEqual(result['source_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(result['output_sha256'], hashlib.sha256(self.target.read_bytes()).hexdigest())

    def test_numbered_input_is_renumbered_without_changing_text(self):
        self.source.write_text('3\n00:00:01,000 --> 00:00:02,000\nПервый\n\n'
                               '7\n00:00:03,000 --> 00:00:04,000\nВторой\n')
        subtitles.normalize(self.source, self.target)
        self.assertEqual(self.target.read_text(), '1\n00:00:01,000 --> 00:00:02,000\nПервый\n\n'
                                                '2\n00:00:03,000 --> 00:00:04,000\nВторой\n')

    def test_clip_rebases_and_speed_preserves_text(self):
        original = '1\n00:00:01,000 --> 00:00:03,000\nOne\n\n2\n00:00:04,000 --> 00:00:06,000\nДва\n'
        self.source.write_text(original)
        subtitles.process(self.source, self.target, 'clip', start_seconds=2, end_seconds=5)
        self.assertEqual(self.target.read_text(),
                         '1\n00:00:00,000 --> 00:00:01,000\nOne\n\n2\n00:00:02,000 --> 00:00:03,000\nДва\n')
        fast = self.root/'fast.srt'
        subtitles.process(self.source, fast, 'speed', speed_factor=2)
        self.assertEqual(fast.read_text(),
                         '1\n00:00:00,500 --> 00:00:01,500\nOne\n\n2\n00:00:02,000 --> 00:00:03,000\nДва\n')
        self.assertEqual(self.source.read_text(), original)

    def test_invalid_content_never_becomes_success_or_changes_source(self):
        cases = ['', 'missing timing\ntext\n', '1\n00:00:02,000 --> 00:00:01,000\nBad\n',
                 '1\n00:00:00,000 --> 00:00:00,000\nZero\n',
                 '1\n00:00:00,000 --> 00:00:01,000\n\n',
                 '1\n00:00:00,000 --> 00:00:02,000\nOne\n\n2\n00:00:01,000 --> 00:00:03,000\nOverlap\n',
                 '2\n00:00:00,000 --> 00:00:01,000\nOne\n\n1\n00:00:02,000 --> 00:00:03,000\nBad ID\n']
        for content in cases:
            with self.subTest(content=content):
                self.source.write_text(content)
                with self.assertRaises(ValueError):
                    subtitles.normalize(self.source, self.target)
                self.assertEqual(self.source.read_text(), content)
                self.assertFalse(self.target.exists())

    def test_invalid_operation_parameters_and_media_bounds(self):
        self.source.write_text('1\n00:00:01,000 --> 00:00:03,000\nWords\n')
        for operation, options in [
            ('speed', {'speed_factor': 0}), ('speed', {'speed_factor': 3}),
            ('clip', {'start_seconds': 3, 'end_seconds': 2}),
            ('clip', {'start_seconds': 10, 'end_seconds': 11}),
            ('normalize', {'media_duration': 1}),
        ]:
            with self.subTest(operation=operation, options=options):
                with self.assertRaises(ValueError):
                    subtitles.process(self.source, self.target, operation, **options)
                self.assertFalse(self.target.exists())

    def test_extreme_hour_cannot_wrap_in_original_formatter(self):
        original = '1\n4294967296:00:00,000 --> 4294967296:00:01,000\nWords\n'
        self.source.write_text(original)
        with self.assertRaises(ValueError):
            subtitles.normalize(self.source, self.target)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.source.read_text(), original)

    def test_translation_route_rejects_zero_duration_before_provider(self):
        original = ('1\n00:00:00,000 --> 00:00:00,000\nZero\n\n'
                    '2\n00:00:01,000 --> 00:00:02,000\nValid\n')
        self.source.write_text(original)
        completed = subprocess.run([
            self.runtime['worker'], '--srt', str(self.source),
            '--output', str(self.target), '--target', 'ru',
        ], capture_output=True, text=True, timeout=5)
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.source.read_text(), original)
        # The native route must reject skipped cues before it can call Ollama.
        worker_source = (Path(__file__).resolve().parents[1]/
                         'workers/videotext_translation_worker.swift').read_text()
        translation_route = worker_source.split('let sourceURL', 1)[1].split('let translated', 1)[0]
        self.assertLess(translation_route.index('parsed.skippedZeroDurationCount == 0'),
                        translation_route.index('TranslationAdapter().translate'))

    def test_actual_runtime_manifest_and_binary_drift_rejected(self):
        worker = self.root/'translation-worker'
        shutil.copy2(self.runtime['worker'], worker)
        manifest = self.root/'runtime.json'
        original = json.loads((Path(self.runtime['worker']).parent/'runtime.json').read_text())
        with patch.dict(os.environ, {'INTEGRA_VIDEOTEXT_SUBTITLE_WORKER': str(worker)}):
            manifest.write_text(json.dumps(original))
            self.assertEqual(subtitles.preflight()['state'], 'READY')
            for field in ['commit_sha', 'srt_service_sha256', 'worker_sha256']:
                manifest.write_text(json.dumps({**original, field: '0'*64}))
                with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    subtitles.preflight()
            manifest.write_text(json.dumps(original))
            with worker.open('ab') as stream:
                stream.write(b'drift')
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                subtitles.preflight()


if __name__ == '__main__':
    unittest.main()
