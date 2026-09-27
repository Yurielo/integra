"""Real pinned CLI integration with deterministic test-only media executables."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from integra_core import seminartext_asr_runtime as asr
from tests.asr_tools import media_environment, TRANSCRIPT, require_subtitle_runtime


class SeminarTextASRTests(unittest.TestCase):
    def test_active_cli_pin_is_the_final_seminartext_artifact(self):
        self.assertEqual(asr.ENTRYPOINT_SHA256, "30d8c1bd6f5ca717391b168cba71228a030009feaec4eb443bb1e76dab230a6c")

    def test_source_speech_language_is_limited_to_the_pinned_runtime_contract(self):
        self.assertEqual(asr._source_speech_language("ru"), "ru")
        with self.assertRaisesRegex(asr.ASRError, "Source-speech language"):
            asr._source_speech_language("en")

    def test_native_failed_run_surfaces_quality_report_in_both_views(self):
        swift=(Path(__file__).resolve().parents[1]/"macos/IntegraApp.swift").read_text()
        self.assertIn('if state == "FAILED" { renderFailedASRReports(run) }',swift)
        outputs=swift.split('private func renderOutputs()',1)[1]
        self.assertIn('else if run["state"] as? String == "FAILED"',outputs)
        self.assertIn('renderFailedASRReports(run)',outputs)
        helper=swift.split('private func renderFailedASRReports',1)[1].split('@objc',1)[0]
        self.assertIn('outputs["transcript_quality_report"]',helper)
        self.assertIn('#selector(openOutput(_:))',helper)

    def test_rejects_unverifiable_component(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"INTEGRA_SEMINARTEXT_CHECKOUT": directory}):
            with self.assertRaisesRegex(asr.ASRError, "cannot be verified"):
                asr.preflight(Path("ffmpeg"), Path("whisper"), Path("model"))

    def test_rejects_modified_entrypoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "seminartext").write_text("not the pinned program")
            with patch.dict(os.environ, {}, clear=True), patch.object(asr, "BUNDLED_RUNTIME_ROOT", root):
                with self.assertRaisesRegex(asr.ASRError, "pinned bytes"):
                    asr._runtime()

    def test_verified_runtime_is_accepted_but_modified_bytes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); entrypoint = root / "seminartext"; version = root / "SEMINARTEXT_VERSION"
            entrypoint.write_bytes(b"verified packaged SeminarText CLI"); version.write_bytes(b"verified version metadata")
            with patch.dict(os.environ, {}, clear=True), patch.object(asr, "BUNDLED_RUNTIME_ROOT", root), \
                 patch.object(asr, "ENTRYPOINT_SHA256", asr._sha(entrypoint)), patch.object(asr, "VERSION_SHA256", asr._sha(version)):
                self.assertEqual(asr._runtime(), root.resolve())
                entrypoint.write_bytes(entrypoint.read_bytes() + b"\nmodified")
                with self.assertRaisesRegex(asr.ASRError, "pinned bytes"):
                    asr._runtime()

    def test_srt_normalization_rejects_malformed_source_without_editing_it(self):
        require_subtitle_runtime()
        cases=['', 'missing timing\ntext\n',
               '00:00:02,000 --> 00:00:01,000\ntext\n',
               '00:00:00,000 --> 00:00:01,000\n']
        for value in cases:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                source=Path(directory)/'original.srt'; source.write_text(value)
                target=Path(directory)/'numbered.srt'
                with self.assertRaises(asr.ASRError): asr._number_srt(source,target)
                self.assertEqual(source.read_text(),value)
                self.assertFalse(target.exists())

    def test_srt_normalization_never_overwrites_existing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'original.srt'
            source.write_text('00:00:00,000 --> 00:00:01,000\nSource words.\n')
            target=Path(directory)/'numbered.srt'; target.write_text('User-owned result')
            with self.assertRaises(FileExistsError): asr._number_srt(source,target)
            self.assertEqual(target.read_text(),'User-owned result')

    def fixture(self, root):
        env = media_environment(root)
        source = root / "source.wav"; source.write_bytes(b"test audio")
        work = root / "work"; work.mkdir()
        args = {"ffmpeg": Path(env["INTEGRA_FFMPEG"]),
                "whisper": Path(env["INTEGRA_WHISPER_CLI"]),
                "model": Path(env["INTEGRA_WHISPER_MODEL"])}
        return source, work, args

    def scripted_whisper(self, root, whisper, *, recover):
        calls = root / "calls.jsonl"
        whisper.write_text(f"#!{sys.executable}\n" + f"""import json, sys
from pathlib import Path
args = sys.argv[1:]
with Path({str(calls)!r}).open('a') as stream: stream.write(json.dumps(args) + '\\n')
prefix = args[args.index('-of') + 1]
text = {TRANSCRIPT!r} if {recover!r} and '--prompt' not in args else 'Неполное восстановление. ' * 30
Path(prefix + '.txt').write_text(text + '\\n', encoding='utf-8')
Path(prefix + '.srt').write_text('1\\n00:00:00,000 --> 00:00:01,250\\n' + text + '\\n', encoding='utf-8')
""")
        return calls

    def test_original_cli_retries_repetition_without_prompt_and_preserves_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source, work, args = self.fixture(root)
            calls = self.scripted_whisper(root, args["whisper"], recover=True)
            original = source.read_bytes()
            result = asr.transcribe(source, work, **args)
            attempts = [json.loads(line) for line in calls.read_text().splitlines()]
            self.assertEqual(len(attempts), 2)
            self.assertIn('--prompt', attempts[0]); self.assertNotIn('--prompt', attempts[1])
            self.assertIn('--vad', attempts[0])
            self.assertEqual(attempts[1][attempts[1].index('-vt') + 1], '0.68')
            self.assertEqual(Path(result['raw_txt']).read_text().strip(), TRANSCRIPT)
            self.assertNotEqual(result['raw_txt'], result['cleaned_txt'])
            self.assertEqual(Path(result['source_srt']).read_text(),
                             '00:00:00,000 --> 00:00:01,250\n' + TRANSCRIPT + '\n\n')
            self.assertEqual(Path(result['srt']).read_text(),
                             '1\n00:00:00,000 --> 00:00:01,250\n' + TRANSCRIPT + '\n')
            self.assertNotEqual(result['srt'],result['source_srt'])
            self.assertEqual(source.read_bytes(), original)
            provenance = json.loads(Path(result['record']).read_text())
            self.assertEqual(provenance['suspicious_chunks'], 0)
            self.assertEqual(provenance['artifact_sha256']['raw_txt'], hashlib.sha256(Path(result['raw_txt']).read_bytes()).hexdigest())

    def test_careful_mode_uses_project_cli_and_persists_executed_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source, work, args = self.fixture(root)
            calls = self.scripted_whisper(root, args["whisper"], recover=True)
            result = asr.transcribe(source, work, **args, recognition_mode="careful")
            attempts = [json.loads(line) for line in calls.read_text().splitlines()]
            self.assertEqual(len(attempts), 2)
            self.assertEqual(attempts[0][attempts[0].index("-bo") + 1], "8")
            self.assertEqual(attempts[0][attempts[0].index("-bs") + 1], "8")
            self.assertEqual(attempts[0][attempts[0].index("-vt") + 1], "0.45")
            self.assertEqual(attempts[0][attempts[0].index("-vsd") + 1], "700")
            self.assertEqual(attempts[1][attempts[1].index("-bo") + 1], "3")
            self.assertEqual(attempts[1][attempts[1].index("-bs") + 1], "3")
            self.assertEqual(attempts[1][attempts[1].index("-vt") + 1], "0.68")
            self.assertEqual(attempts[1][attempts[1].index("-vsd") + 1], "350")
            self.assertEqual(json.loads(Path(result["record"]).read_text())["mode"], "careful")

    def test_normal_mode_uses_default_quality_profile_and_persists_executed_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source, work, args = self.fixture(root)
            calls = self.scripted_whisper(root, args["whisper"], recover=True)
            result = asr.transcribe(source, work, **args)
            attempts = [json.loads(line) for line in calls.read_text().splitlines()]
            self.assertEqual(len(attempts), 2)
            self.assertEqual(attempts[0][attempts[0].index("-bo") + 1], "5")
            self.assertEqual(attempts[0][attempts[0].index("-bs") + 1], "5")
            self.assertEqual(attempts[0][attempts[0].index("-vt") + 1], "0.55")
            self.assertEqual(attempts[0][attempts[0].index("-vsd") + 1], "550")
            self.assertEqual(attempts[1][attempts[1].index("-bo") + 1], "3")
            self.assertEqual(attempts[1][attempts[1].index("-bs") + 1], "3")
            self.assertEqual(json.loads(Path(result["record"]).read_text())["mode"], "normal")

    def test_persistent_repetition_is_quality_error_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source, work, args = self.fixture(root)
            calls = self.scripted_whisper(root, args['whisper'], recover=False)
            with self.assertRaises(asr.ASRQualityError) as caught:
                asr.transcribe(source, work, **args)
            self.assertEqual(len(calls.read_text().splitlines()), 2)
            artifacts = caught.exception.artifacts
            self.assertTrue(Path(artifacts['raw_txt']).is_file())
            self.assertTrue(Path(artifacts['review_txt']).is_file())
            self.assertEqual(artifacts['provenance']['suspicious_chunks'], 1)

    def test_numbered_subtitles_preserve_chunk_offsets_and_original_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source,work,args=self.fixture(root)
            args['ffmpeg'].write_text(f"#!{sys.executable}\n" + """import sys, shutil
args=sys.argv[1:]
source=args[args.index('-i')+1]
target=args[-1]
for index in range(2 if '%04d' in target else 1):
    shutil.copyfile(source,target.replace('%04d',f'{index:04d}'))
""")
            result=asr.transcribe(source,work,**args)
            original=Path(result['source_srt']).read_bytes()
            expected=('00:00:00,000 --> 00:00:01,250\n'+TRANSCRIPT+'\n\n'
                      '00:05:00,000 --> 00:05:01,250\n'+TRANSCRIPT+'\n\n')
            self.assertEqual(original,expected.encode())
            numbered=Path(result['srt']).read_text()
            self.assertEqual(numbered,'1\n'+expected.split('\n\n')[0]+'\n\n2\n'+expected.split('\n\n')[1]+'\n')
            self.assertEqual(Path(result['source_srt']).read_bytes(),original)

    def test_cancellation_terminates_owned_cli_without_success_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source, work, args = self.fixture(root)
            args['whisper'].write_text('#!/bin/sh\nsleep 30\n')
            started = time.monotonic()
            with self.assertRaises(asr.ASRCancelled):
                asr.transcribe(source, work, **args, cancelled=lambda: time.monotonic() - started > 1)
            self.assertLess(time.monotonic() - started, 8)
            self.assertFalse((work / 'seminartext-asr/provenance.json').exists())

    def test_vad_integrity_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source, work, args = self.fixture(root)
            vad = root / 'vad.bin'; vad.write_bytes(b'wrong model')
            with self.assertRaisesRegex(asr.ASRError, 'VAD model differs'):
                asr.transcribe(source, work, **args, vad_model=vad)
            self.assertFalse((work / 'seminartext-asr').exists())
