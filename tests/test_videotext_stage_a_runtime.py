"""Stage A contract tests use a deterministic fake worker, never user media."""
from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import textwrap
import unittest

from integra_core import videotext_stage_a_runtime as stage_a


class StageARuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stage_root = self.root / "owned"; self.stage_root.mkdir()
        self.source = self.root / "source.wav"; self.source.write_bytes(b"not real media")
        self.model = self.root / "model.bin"; self.model.write_bytes(b"model")
        self.tools = {}
        for name in ("ffmpeg", "ffprobe", "whisper-cli"):
            tool = self.root / name; tool.write_text("#!/bin/sh\nexit 0\n"); tool.chmod(stat.S_IRWXU)
            self.tools[name] = tool
        self.worker_dir = self.root / "runtime"; self.worker_dir.mkdir()
        self.worker = self.worker_dir / stage_a.WORKER_NAME
        self._write_worker()
        runtime = {**stage_a.EXPECTED, "schema_version": "1.0", "worker_sha256": stage_a._sha(self.worker)}
        (self.worker_dir / "runtime.json").write_text(json.dumps(runtime))

    def _write_worker(self, *, malformed=False, escape=False, sleep=False):
        body = """
        #!/usr/bin/env python3
        import json, os, pathlib, sys, time
        request = json.loads(pathlib.Path(sys.argv[2]).read_text())
        project = pathlib.Path(request['project_path'])
        texts = project / 'Texts'; support = project / 'Support files'
        texts.mkdir(parents=True); support.mkdir(parents=True)
        (texts/'full.srt').write_text(%r)
        (texts/'transcript.txt').write_text('hello')
        (support/'whisper.json').write_text('{}')
        (support/'manifest.json').write_text('{}')
        quality = support/'Quality'/'transcription_quality.json'; quality.parent.mkdir(); quality.write_text('{}')
        review = support/'Review'/'review_tasks.json'; review.parent.mkdir(); review.write_text('{}')
        pathlib.Path(os.environ['HOME']).joinpath('environment.json').write_text(json.dumps({'path': os.environ['PATH'], 'seminartext': [k for k in os.environ if 'SEMINARTEXT' in k]}))
        %s
        result = {'schema_version':'1.0','component':'videotext','capability':'stage_a_transcript','project_path':str(project),'srt_path':str(texts/'full.srt'),'transcript_path':str(texts/'transcript.txt'),'whisper_json_path':str(support/'whisper.json'),'manifest_path':str(support/'manifest.json'),'quality_path':str(quality),'review_tasks_path':str(review),'review_checkpoint':'SOURCE_TRANSCRIPT','semantic_authority':'MACHINE_UNVERIFIED'}
        print('INTEGRA_VIDEOTEXT_STAGE_A_RESULT ' + json.dumps(result))
        """ % ("1\n00:00:00,000 --> 00:00:01,000\nHello\n" if not malformed else "bad", "time.sleep(5)" if sleep else "")
        if escape:
            body = body.replace("'srt_path':str(texts/'full.srt')", "'srt_path':'/tmp/escape.srt'")
        self.worker.write_text(textwrap.dedent(body).lstrip())
        self.worker.chmod(stat.S_IRWXU)

    def _run(self, **options):
        timeout_seconds = options.pop('timeout_seconds', 1)
        return stage_a.run(source=self.source, stage_root=self.stage_root, worker=self.worker,
                           ffmpeg=self.tools['ffmpeg'], ffprobe=self.tools['ffprobe'],
                           whisper=self.tools['whisper-cli'], model=self.model, timeout_seconds=timeout_seconds, **options)

    def test_cold_then_hash_bound_warm_reuse_and_clean_environment(self):
        cold = self._run()
        self.assertEqual((cold['state'], cold['cache_state'], cold['cue_count']), ('REVIEW_REQUIRED', 'COLD', 1))
        environment = json.loads(next((self.stage_root/'runs').glob('*/environment.json')).read_text())
        self.assertEqual(environment['seminartext'], [])
        self.assertTrue(environment['path'].startswith(str((self.stage_root/'runs').resolve())))
        warm = self._run()
        self.assertEqual((warm['state'], warm['cache_state']), ('REUSED', 'WARM'))

    def test_malformed_srt_never_becomes_cache(self):
        self._write_worker(malformed=True)
        runtime = json.loads((self.worker_dir/'runtime.json').read_text()); runtime['worker_sha256'] = stage_a._sha(self.worker)
        (self.worker_dir/'runtime.json').write_text(json.dumps(runtime))
        with self.assertRaisesRegex(stage_a.StageAError, 'SRT'):
            self._run()
        self.assertFalse(any((self.stage_root/'.videotext-stage-a-cache').glob('*.json')) if (self.stage_root/'.videotext-stage-a-cache').exists() else False)

    def test_result_path_escape_is_rejected(self):
        self._write_worker(escape=True)
        runtime = json.loads((self.worker_dir/'runtime.json').read_text()); runtime['worker_sha256'] = stage_a._sha(self.worker)
        (self.worker_dir/'runtime.json').write_text(json.dumps(runtime))
        with self.assertRaisesRegex(stage_a.StageAError, 'escapes'):
            self._run()

    def test_timeout_cleans_owned_process(self):
        self._write_worker(sleep=True)
        runtime = json.loads((self.worker_dir/'runtime.json').read_text()); runtime['worker_sha256'] = stage_a._sha(self.worker)
        (self.worker_dir/'runtime.json').write_text(json.dumps(runtime))
        with self.assertRaisesRegex(stage_a.StageAError, 'timed out'):
            self._run(timeout_seconds=0.05)

    def test_cancellation_cleans_owned_process(self):
        self._write_worker(sleep=True)
        runtime = json.loads((self.worker_dir/'runtime.json').read_text()); runtime['worker_sha256'] = stage_a._sha(self.worker)
        (self.worker_dir/'runtime.json').write_text(json.dumps(runtime))
        with self.assertRaisesRegex(stage_a.StageACancelled, 'cancelled'):
            self._run(cancelled=lambda: True)

    def test_runtime_identity_drift_fails_before_execution(self):
        runtime = json.loads((self.worker_dir/'runtime.json').read_text()); runtime['commit_sha'] = '0' * 40
        (self.worker_dir/'runtime.json').write_text(json.dumps(runtime))
        with self.assertRaisesRegex(stage_a.StageAError, 'identity mismatch'):
            self._run()


if __name__ == '__main__':
    unittest.main()
