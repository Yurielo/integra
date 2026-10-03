import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integra_core import translategemma_runtime as runtime


class TranslateGemmaRuntimeTests(unittest.TestCase):
    def test_exact_daemon_tag_and_full_digest_required_without_fallback(self):
        for name, digest, accepted in (
            (runtime.MODEL, runtime.MODEL_DIGEST, True),
            ('translategemma:4b', runtime.MODEL_DIGEST, False),
            (runtime.MODEL, runtime.MODEL_DIGEST[:12], False),
            ('qwen3:8b', runtime.MODEL_DIGEST, False),
            (runtime.MODEL, '0' * 64, False),
        ):
            payload = json.dumps({'models': [{'name': name, 'digest': digest}]}).encode()
            with self.subTest(name=name, digest=digest), patch.object(runtime, 'urlopen', return_value=io.BytesIO(payload)):
                if accepted:
                    self.assertEqual(runtime._model_digest(), runtime.MODEL_DIGEST)
                else:
                    with self.assertRaises(ValueError):
                        runtime._model_digest()

    def test_preflight_binds_full_model_weights_and_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'ollama'
            executable.write_bytes(b'public test executable')
            with patch.object(runtime, 'resolve_ollama', return_value=executable), \
                    patch.object(runtime, '_model_digest', return_value=runtime.MODEL_DIGEST), \
                    patch.object(runtime, '_verify_model_bytes') as verify, \
                    patch.object(runtime.subprocess, 'check_output', return_value='ollama version 1\n'):
                record = runtime.preflight()
                verify.assert_called_once_with(hash_layers=True)
        self.assertEqual(record['model_id'], runtime.MODEL_DIGEST)
        self.assertEqual(record['weights_sha256'], runtime.WEIGHTS_DIGEST)
        self.assertEqual(record['ollama_sha256'], runtime.hashlib.sha256(b'public test executable').hexdigest())
        self.assertEqual(len(record['runtime_identity_sha256']), 64)

    def test_capability_preflight_retains_identity_checks_without_rehashing_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'ollama'
            executable.write_bytes(b'public test executable')
            with patch.object(runtime, 'resolve_ollama', return_value=executable), \
                    patch.object(runtime, '_model_digest', return_value=runtime.MODEL_DIGEST), \
                    patch.object(runtime, '_verify_model_bytes') as verify, \
                    patch.object(runtime.subprocess, 'check_output', return_value='ollama version 1\n'):
                record = runtime.preflight(hash_model=False)
                verify.assert_called_once_with(hash_layers=False)
        self.assertEqual(record['model_id'], runtime.MODEL_DIGEST)
        self.assertEqual(record['weights_sha256'], runtime.WEIGHTS_DIGEST)

    def test_manifest_and_layer_corruption_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'manifests/registry.ollama.ai/library/translategemma/4b-it-q4_K_M'
            manifest.parent.mkdir(parents=True)
            manifest.write_bytes(b'wrong manifest')
            with patch.dict(runtime.os.environ, {'OLLAMA_MODELS': directory}):
                with self.assertRaisesRegex(ValueError, 'manifest differs'):
                    runtime._verify_model_bytes()
                manifest.write_text(json.dumps({'layers': [{'digest': 'sha256:' + runtime.WEIGHTS_DIGEST, 'size': 5}], 'config': {'digest': 'sha256:' + '1' * 64, 'size': 1}}))
                blobs = root / 'blobs'
                blobs.mkdir()
                (blobs / ('sha256-' + runtime.WEIGHTS_DIGEST)).write_bytes(b'wrong')
                original = runtime._sha_file
                with patch.object(runtime, '_sha_file', side_effect=lambda p: runtime.MODEL_DIGEST if p == manifest else original(p)):
                    with self.assertRaisesRegex(ValueError, 'layer bytes differ'):
                        runtime._verify_model_bytes()

    def test_response_must_be_complete_well_formed_and_exact_model(self):
        good = {'model': runtime.MODEL, 'done': True, 'done_reason': 'stop', 'message': {'content': 'Hello'}}
        bad = [[], None, {}, {**good, 'done': False}, {**good, 'done_reason': 'length'},
               {**good, 'model': 'qwen3:8b'}, {**good, 'message': {'content': ''}}]
        for payload in [good] + bad:
            with self.subTest(payload=payload), patch.object(runtime, '_model_digest', return_value=runtime.MODEL_DIGEST), \
                    patch.object(runtime, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
                if payload == good:
                    self.assertEqual(runtime._translate_text('Привет', 'ru', 'en', {'model': runtime.MODEL}), 'Hello')
                else:
                    with self.assertRaises(ValueError):
                        runtime._translate_text('Привет', 'ru', 'en', {'model': runtime.MODEL})

    def test_provided_runtime_cannot_bypass_fresh_preflight(self):
        with patch.object(runtime, 'preflight', return_value={'model': runtime.MODEL, 'model_id': runtime.MODEL_DIGEST}):
            with self.assertRaisesRegex(ValueError, 'required configuration'):
                runtime.translate(Path('unused'), Path('unused'), source='ru', target='en', runtime={'model': runtime.MODEL})

    def test_failed_cue_never_writes_partial_output_or_changes_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'in.srt', Path(directory) / 'out.json'
            original = b'3\n00:00:01,000 --> 00:00:02,000\nFirst\n\n8\n00:00:03,000 --> 00:00:04,000\nSecond\n'
            source.write_bytes(original)
            with patch.object(runtime, 'preflight', return_value={'model': runtime.MODEL}), \
                    patch.object(runtime, '_translate_text', side_effect=['First translated', ValueError('incomplete')]):
                with self.assertRaises(ValueError):
                    runtime.translate(source, output, source='en', target='ru')
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), original)
