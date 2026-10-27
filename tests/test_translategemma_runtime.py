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
            (runtime.INSTALLED_ALIAS, runtime.MODEL_DIGEST, True),
            (runtime.MODEL, runtime.MODEL_DIGEST[:12], False),
            ('qwen3:8b', runtime.MODEL_DIGEST, False),
            (runtime.MODEL, '0' * 64, False),
        ):
            payload = json.dumps({'models': [{'name': name, 'digest': digest}]}).encode()
            with self.subTest(name=name, digest=digest), patch.object(runtime, 'urlopen', return_value=io.BytesIO(payload)):
                if accepted:
                    self.assertEqual(runtime._model_identity(), (name, runtime.MODEL_DIGEST))
                else:
                    with self.assertRaises(ValueError):
                        runtime._model_identity()

    def test_canonical_tag_wins_and_invalid_canonical_never_falls_back(self):
        canonical = {'name': runtime.MODEL, 'digest': runtime.MODEL_DIGEST}
        alias = {'name': runtime.INSTALLED_ALIAS, 'digest': runtime.MODEL_DIGEST}
        inventories = [
            ([alias, canonical], (runtime.MODEL, runtime.MODEL_DIGEST)),
            ([canonical, alias], (runtime.MODEL, runtime.MODEL_DIGEST)),
            ([{**canonical, 'digest': '0' * 64}, alias], None),
            ([{'name': runtime.MODEL}, alias], None),
            ([canonical, canonical, alias], None),
            ([alias, alias], None),
            ([{**alias, 'digest': '0' * 64}], None),
            ([{'name': runtime.INSTALLED_ALIAS}], None),
            ([{'name': 'translategemma:latest', 'digest': runtime.MODEL_DIGEST}], None),
            ([], None),
        ]
        for models, expected in inventories:
            with self.subTest(models=models), patch.object(
                runtime, 'urlopen', return_value=io.BytesIO(json.dumps({'models': models}).encode()),
            ):
                if expected:
                    self.assertEqual(runtime._model_identity(), expected)
                else:
                    with self.assertRaises(ValueError):
                        runtime._model_identity()
        for payload in (None, [], {}, {'models': None}, {'models': {}}):
            with self.subTest(payload=payload), patch.object(
                runtime, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode()),
            ):
                with self.assertRaises(ValueError):
                    runtime._model_identity()

    def test_preflight_binds_full_model_weights_and_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'ollama'
            executable.write_bytes(b'public test executable')
            with patch.object(runtime, 'resolve_ollama', return_value=executable), \
                    patch.object(runtime, '_model_identity', return_value=(runtime.MODEL, runtime.MODEL_DIGEST)), \
                    patch.object(runtime, '_verify_model_bytes') as verify, \
                    patch.object(runtime.subprocess, 'check_output', return_value='ollama version 1\n'):
                record = runtime.preflight()
                verify.assert_called_once_with(model=runtime.MODEL, hash_layers=True)
        self.assertEqual(record['model_id'], runtime.MODEL_DIGEST)
        self.assertEqual(record['weights_sha256'], runtime.WEIGHTS_DIGEST)
        self.assertEqual(record['ollama_sha256'], runtime.hashlib.sha256(b'public test executable').hexdigest())
        self.assertEqual(len(record['runtime_identity_sha256']), 64)
        self.assertNotIn('request_model', record)
        identity = {k: v for k, v in record.items()
                    if k not in ('state', 'ollama', 'runtime_identity_sha256')}
        self.assertEqual(record['runtime_identity_sha256'], runtime.hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest())

    def test_alias_preflight_preserves_contract_model_and_binds_actual_request(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'ollama'
            executable.write_bytes(b'public test executable')
            with patch.object(runtime, 'resolve_ollama', return_value=executable), \
                    patch.object(runtime, '_model_identity') as identity, \
                    patch.object(runtime, '_verify_model_bytes') as verify, \
                    patch.object(runtime.subprocess, 'check_output', return_value='ollama version 1\n'):
                identity.return_value = (runtime.MODEL, runtime.MODEL_DIGEST)
                canonical = runtime.preflight()
                identity.return_value = (runtime.INSTALLED_ALIAS, runtime.MODEL_DIGEST)
                alias = runtime.preflight()
                verify.assert_called_with(model=runtime.INSTALLED_ALIAS, hash_layers=True)
        self.assertEqual(alias['model'], canonical['model'])
        self.assertEqual(alias['model_id'], canonical['model_id'])
        self.assertEqual(alias['request_model'], runtime.INSTALLED_ALIAS)
        self.assertNotEqual(alias['runtime_identity_sha256'], canonical['runtime_identity_sha256'])
        original_identity = {k: v for k, v in canonical.items()
                             if k not in ('state', 'ollama', 'runtime_identity_sha256')}
        original_identity['request_model'] = runtime.INSTALLED_ALIAS
        self.assertEqual(alias['runtime_identity_sha256'], runtime.hashlib.sha256(
            json.dumps(original_identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest())

    def test_alias_uses_its_own_verified_manifest_and_all_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            weights, config = b'public synthetic weights', b'{}'
            weights_digest = runtime.hashlib.sha256(weights).hexdigest()
            config_digest = runtime.hashlib.sha256(config).hexdigest()
            record = {'layers': [{'digest': 'sha256:' + weights_digest, 'size': len(weights)}],
                      'config': {'digest': 'sha256:' + config_digest, 'size': len(config)}}
            manifest_bytes = json.dumps(record).encode()
            manifest = root / 'manifests/registry.ollama.ai/library/translategemma/4b'
            manifest.parent.mkdir(parents=True)
            manifest.write_bytes(manifest_bytes)
            blobs = root / 'blobs'
            blobs.mkdir()
            weight_file = blobs / ('sha256-' + weights_digest)
            config_file = blobs / ('sha256-' + config_digest)
            weight_file.write_bytes(weights)
            config_file.write_bytes(config)
            with patch.dict(runtime.os.environ, {'OLLAMA_MODELS': directory}), \
                    patch.object(runtime, 'MODEL_DIGEST', runtime.hashlib.sha256(manifest_bytes).hexdigest()), \
                    patch.object(runtime, 'WEIGHTS_DIGEST', weights_digest):
                runtime._verify_model_bytes(model=runtime.INSTALLED_ALIAS)
                with self.assertRaises(ValueError):
                    runtime._verify_model_bytes()  # A canonical manifest cannot be fabricated from an alias.
                weight_file.write_bytes(b'x' * len(weights))
                with self.assertRaisesRegex(ValueError, 'layer bytes differ'):
                    runtime._verify_model_bytes(model=runtime.INSTALLED_ALIAS)
                weight_file.write_bytes(weights)
                config_file.write_bytes(b'[]')
                with self.assertRaisesRegex(ValueError, 'layer bytes differ'):
                    runtime._verify_model_bytes(model=runtime.INSTALLED_ALIAS)
                config_file.write_bytes(config)
                manifest.write_bytes(b'changed manifest')
                with self.assertRaisesRegex(ValueError, 'manifest differs'):
                    runtime._verify_model_bytes(model=runtime.INSTALLED_ALIAS)
                with self.assertRaisesRegex(ValueError, 'tag is unsupported'):
                    runtime._verify_model_bytes(model='qwen3:8b')

    def test_capability_preflight_retains_identity_checks_without_rehashing_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'ollama'
            executable.write_bytes(b'public test executable')
            with patch.object(runtime, 'resolve_ollama', return_value=executable), \
                    patch.object(runtime, '_model_identity', return_value=(runtime.MODEL, runtime.MODEL_DIGEST)), \
                    patch.object(runtime, '_verify_model_bytes') as verify, \
                    patch.object(runtime.subprocess, 'check_output', return_value='ollama version 1\n'):
                record = runtime.preflight(hash_model=False)
                verify.assert_called_once_with(model=runtime.MODEL, hash_layers=False)
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
            with self.subTest(payload=payload), patch.object(runtime, '_model_identity', return_value=(runtime.MODEL, runtime.MODEL_DIGEST)), \
                    patch.object(runtime, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
                if payload == good:
                    self.assertEqual(runtime._translate_text('Привет', 'ru', 'en', {'model': runtime.MODEL}), 'Hello')
                else:
                    with self.assertRaises(ValueError):
                        runtime._translate_text('Привет', 'ru', 'en', {'model': runtime.MODEL})

    def test_alias_request_and_response_use_actual_tag(self):
        identity = {'model': runtime.MODEL, 'request_model': runtime.INSTALLED_ALIAS}
        for response_model in (runtime.INSTALLED_ALIAS, runtime.MODEL, 'qwen3:8b'):
            response = {'model': response_model, 'done': True, 'done_reason': 'stop',
                        'message': {'content': 'Hello'}}
            with self.subTest(response_model=response_model), patch.object(
                runtime, '_model_identity', return_value=(runtime.INSTALLED_ALIAS, runtime.MODEL_DIGEST),
            ), patch.object(runtime, 'urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as post:
                if response_model == runtime.INSTALLED_ALIAS:
                    self.assertEqual(runtime._translate_text('Привет', 'ru', 'en', identity), 'Hello')
                else:
                    with self.assertRaisesRegex(ValueError, 'identity or response is invalid'):
                        runtime._translate_text('Привет', 'ru', 'en', identity)
                request = post.call_args.args[0]
                body = json.loads(request.data)
                self.assertEqual(body['model'], runtime.INSTALLED_ALIAS)
                self.assertEqual(body['options'], {'temperature': 0.0, 'num_predict': 1024})
                self.assertEqual(body['messages'][0]['content'], runtime._prompt('Привет', 'ru', 'en'))

    def test_selected_tag_drift_before_or_after_request_is_rejected(self):
        alias_identity = (runtime.INSTALLED_ALIAS, runtime.MODEL_DIGEST)
        canonical_identity = (runtime.MODEL, runtime.MODEL_DIGEST)
        response = {'model': runtime.INSTALLED_ALIAS, 'done': True, 'done_reason': 'stop',
                    'message': {'content': 'Hello'}}
        for observed, calls in (([canonical_identity], 0), ([alias_identity, canonical_identity], 1),
                                ([alias_identity, ValueError('digest changed')], 1)):
            with self.subTest(observed=observed), patch.object(
                runtime, '_model_identity', side_effect=observed,
            ), patch.object(runtime, 'urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as post:
                with self.assertRaises(ValueError):
                    runtime._translate_text('Привет', 'ru', 'en', {
                        'model': runtime.MODEL, 'request_model': runtime.INSTALLED_ALIAS})
                self.assertEqual(post.call_count, calls)

    def test_alias_output_retains_canonical_model_and_exact_request_provenance(self):
        identity = {'model': runtime.MODEL, 'model_id': runtime.MODEL_DIGEST,
                    'request_model': runtime.INSTALLED_ALIAS, 'runtime_identity_sha256': 'a' * 64}
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'in.srt', Path(directory) / 'out.json'
            original = '3\n00:00:01,125 --> 00:00:02,375\nПривет\n'.encode()
            source.write_bytes(original)
            with patch.object(runtime, 'preflight', return_value=identity), \
                    patch.object(runtime, '_translate_text', return_value='Hello'):
                value = runtime.translate(source, output, source='ru', target='en', runtime=identity)
            self.assertEqual(value['model'], runtime.MODEL)
            self.assertEqual(value['request_model'], runtime.INSTALLED_ALIAS)
            self.assertEqual(value['runtime_identity_sha256'], identity['runtime_identity_sha256'])
            self.assertEqual(value['cues'], [{'id': 3, 'start_seconds': 1.125, 'end_seconds': 2.375, 'text': 'Hello'}])
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(json.loads(output.read_bytes()), value)

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
