"""Migration compatibility over public synthetic, governed contract fixtures.

Historical provider records are constructed in their original contract shape,
not passed through a current writer that could silently replace their identity.
No source applications, private projects or installed models are accessed.
"""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from integra_core.identity import derive_imported_id
from integra_core.media import (
    MediaError, create_media_recipe, dumps_media_recipe, loads_media_recipe,
)
from integra_core.protocol import canonical_json, content_sha256
from integra_core.transcript_topic_studio import (
    StudioError, dumps_studio, loads_studio, new_studio, register_translation,
    validate_studio,
)
from integra_core import translategemma_runtime as runtime
try:
    from tests.test_media import _source, _artifact, OPERATION_ID, NOW
    from tests import test_transcript_topic_studio as studio_fixtures
except ModuleNotFoundError:  # unittest discovery also places tests/ on sys.path.
    from test_media import _source, _artifact, OPERATION_ID, NOW
    import test_transcript_topic_studio as studio_fixtures


ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA = runtime.MODEL_DIGEST
LEGACY_IMPLEMENTATIONS = [{
    "function": "translate",
    "path": "Sources/videotext/Adapters/TranslationAdapter.swift",
    "sha256": "83e55d3cb82522cb431ee20617510b0c39f79ae0fa5309daedf5c7ff9911a577",
}]


def _schema_errors(value, name):
    # Use the governed, hashlocked review dependency; never skip schema proof.
    schema = json.loads((ROOT / "schemas" / name).read_bytes())
    Draft202012Validator.check_schema(schema)
    return [f"{error.json_path}: {error.message}" for error in
            Draft202012Validator(schema).iter_errors(value)]


def _translation_steps(model=runtime.MODEL):
    return [
        {"kind": "translation", "parameters": {
            "source_language": "ru", "target_language": "en",
        }, "model": {"id": model, "version": runtime.MODEL_DIGEST,
                     "identity_sha256": runtime.WEIGHTS_DIGEST},
         "inputs": [_artifact("transcript", "translation-input")]},
        {"kind": "qa", "parameters": {"checks": [
            "content_hash", "videotext_functional_validation", "output_kind_contract",
            "duration_or_timeline",
        ]}, "model": None, "inputs": []},
    ]


def _new_recipe(model=runtime.MODEL):
    return create_media_recipe(
        source=_source(), operation_id=OPERATION_ID,
        locator={"type": "time_interval", "start_seconds": 0.0, "end_seconds": 2.0},
        steps=_translation_steps(model), created_at=NOW,
    )


def _rehash_recipe(recipe):
    for step in recipe["steps"]:
        step["config_sha256"] = content_sha256({
            "inputs": step["inputs"], "parameters": step["parameters"],
            "model": step["model"],
        })
    identity = content_sha256({
        "source_artifact_id": recipe["source"]["artifact_id"],
        "source_sha256": recipe["source_sha256"], "operation_id": recipe["operation_id"],
        "locator": recipe["source_locator"], "steps": recipe["steps"],
        "component": recipe["component"], "created_at": recipe["created_at"],
    })
    recipe["recipe_id"] = derive_imported_id(
        "recipe", "videotext", recipe["source"]["artifact_id"], identity,
    )
    recipe["recipe_sha256"] = ""
    recipe["recipe_sha256"] = content_sha256(recipe)


def _legacy_recipe():
    # Synthetic saved Qwen recipe uses the exact pinned historical adapter.
    recipe = _new_recipe()
    step = recipe["steps"][0]
    step["videotext_operations"] = ["translate"]
    step["implementations"] = copy.deepcopy(LEGACY_IMPLEMENTATIONS)
    step["model"] = {"id": "qwen3:8b", "version": "1", "identity_sha256": "9" * 64}
    _rehash_recipe(recipe)
    return recipe


def _new_studio_translation():
    studio, _, source_id, revision_id, transcript_id, timeline_id = studio_fixtures.build_media_studio()
    registry = studio_fixtures._REGISTRIES[studio["studio_id"]]
    studio, translation_id = register_translation(
        studio, registry=registry, native_id="translated-r1", content_sha256="4" * 64,
        created_at="2026-09-11T00:03:00Z", transcript_id=transcript_id,
        source_language="ru", target_language="en", confidence=0.7,
        locators=[studio_fixtures.time_locator(), studio_fixtures.artifact_locator(
            source_id, revision_id, studio["source"]["source_revision_sha256"],
        )],
    )
    return studio, registry, transcript_id, timeline_id, translation_id


def _legacy_studio():
    studio, registry, transcript_id, timeline_id, _ = _new_studio_translation()
    binding = studio["component_bindings"]["translation"]
    # The historical Studio contract recorded provider ownership and exact
    # pinned VideoText commit, not a Qwen runtime model digest. Preserve nulls.
    binding["components"] = [studio_fixtures.component("videotext", "translation")]
    translated = next(a for a in studio["artifacts"] if a["kind"] == "TRANSLATION")
    translated["component_binding_sha256"] = content_sha256(binding)
    identity = content_sha256({
        "kind": translated["kind"], "component_ids": ["videotext"],
        "native_id": translated["native_id"], "content_sha256": translated["content_sha256"],
    })
    translated["artifact_id"] = derive_imported_id(
        "artifact", "videotext", translated["native_id"], identity,
    )
    studio["artifacts"].sort(key=lambda a: a["artifact_id"])
    studio["record_sha256"] = ""
    studio["record_sha256"] = content_sha256(studio)
    return studio, registry, transcript_id, timeline_id


class TranslateGemmaMigrationCompatibilityTests(unittest.TestCase):
    def test_legacy_saved_recipe_reopens_without_provider_or_byte_rewrite(self):
        recipe = _legacy_recipe()
        self.assertEqual(_schema_errors(recipe, "media_recipe_v1.schema.json"), [])
        payload = canonical_json(recipe) + b"\n"
        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / "saved-recipe.json"
            saved.write_bytes(payload)
            for _ in range(2):
                loaded = loads_media_recipe(saved.read_bytes())
                self.assertEqual(loaded, recipe)
                self.assertEqual(canonical_json(loaded) + b"\n", payload)
                self.assertEqual(saved.read_bytes(), payload)
                self.assertEqual(loaded["steps"][0]["model"]["id"], "qwen3:8b")
                self.assertEqual(loaded["steps"][0]["implementations"], LEGACY_IMPLEMENTATIONS)

    def test_legacy_saved_studio_reopens_without_lineage_or_provider_rewrite(self):
        studio, registry, transcript_id, timeline_id = _legacy_studio()
        self.assertEqual(_schema_errors(studio, "transcript_topic_studio_v1.schema.json"), [])
        payload = canonical_json(studio) + b"\n"
        registry_before = canonical_json(registry)
        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / "saved-studio.json"
            saved.write_bytes(payload)
            for _ in range(2):
                loaded = loads_studio(saved.read_bytes(), registry)
                self.assertEqual(loaded, studio)
                self.assertEqual(dumps_studio(loaded, registry), payload)
                self.assertEqual(saved.read_bytes(), payload)
                translated = next(a for a in loaded["artifacts"] if a["kind"] == "TRANSLATION")
                self.assertEqual(translated["parent_ids"], [transcript_id])
                self.assertEqual(translated["metadata"]["original_transcript_id"], transcript_id)
                self.assertEqual(loaded["component_bindings"]["translation"]["components"][0]["component_id"], "videotext")
                self.assertIn(timeline_id, [a["artifact_id"] for a in loaded["artifacts"]])
        self.assertEqual(canonical_json(registry), registry_before)

    def test_new_recipe_rejects_qwen_models(self):
        for model in ("qwen3:8b", "qwen2.5:7b"):
            with self.subTest(model=model), self.assertRaises(MediaError):
                _new_recipe(model)

    def test_new_recipe_rejects_changed_manifest_or_weights_identity(self):
        for field, value in (("version", "0" * 64), ("identity_sha256", "0" * 64)):
            steps = _translation_steps()
            steps[0]["model"][field] = value
            with self.subTest(field=field), self.assertRaises(MediaError):
                create_media_recipe(source=_source(), operation_id=OPERATION_ID,
                                    locator={"type": "time_interval", "start_seconds": 0.0,
                                             "end_seconds": 2.0}, steps=steps, created_at=NOW)

    def test_new_provider_saved_record_cannot_launder_qwen_as_legacy(self):
        recipe = _new_recipe()
        recipe["steps"][0]["model"] = {
            "id": "qwen3:8b", "version": "1", "identity_sha256": "9" * 64,
        }
        _rehash_recipe(recipe)
        with self.assertRaises(MediaError):
            loads_media_recipe(canonical_json(recipe) + b"\n")

    def test_legacy_recipe_cannot_be_written_as_new_runtime_recipe(self):
        with self.assertRaises(MediaError):
            dumps_media_recipe(_legacy_recipe())

    def test_new_studio_rejects_legacy_provider_and_qwen_identity(self):
        registry, project_id, source_id, revision_id = studio_fixtures.registry()
        for legacy in (True, False):
            bindings = studio_fixtures.bindings()
            translation = next(b for b in bindings if b["capability"] == "translation")
            if legacy:
                translation["components"] = [studio_fixtures.component("videotext", "translation")]
            else:
                translation["components"][0].update(model_id="qwen3:8b", model_sha256="9" * 64)
            with self.subTest(legacy=legacy), self.assertRaises(StudioError):
                new_studio(registry, project_id=project_id, source_id=source_id,
                           source_revision_id=revision_id, bindings=bindings, created_at=NOW)

    def test_legacy_studio_cannot_append_new_translation_with_historical_provider(self):
        studio, registry, transcript_id, _ = _legacy_studio()
        before = canonical_json(studio)
        with self.assertRaises(StudioError):
            register_translation(
                studio, registry=registry, native_id="new-translation", content_sha256="5" * 64,
                created_at="2026-09-11T00:04:00Z", transcript_id=transcript_id,
                source_language="ru", target_language="en", confidence=0.7,
                locators=studio["artifacts"][0]["locators"],
            )
        self.assertEqual(canonical_json(studio), before)

    def test_new_translation_studio_schema_and_source_lineage(self):
        studio, registry, transcript_id, timeline_id, translation_id = _new_studio_translation()
        validate_studio(studio, registry)
        self.assertEqual(_schema_errors(studio, "transcript_topic_studio_v1.schema.json"), [])
        translated = next(a for a in studio["artifacts"] if a["artifact_id"] == translation_id)
        timeline = next(a for a in studio["artifacts"] if a["artifact_id"] == timeline_id)
        self.assertEqual(translated["parent_ids"], [transcript_id])
        self.assertEqual(translated["semantic_status"], "REVIEW_REQUIRED")
        self.assertEqual(translated["metadata"]["wording"], "DERIVED_TRANSLATION")
        self.assertEqual(timeline["parent_ids"], [transcript_id])
        self.assertFalse(studio["source_artifacts_modified"])
        self.assertEqual(studio["review_decisions"], [])
        self.assertEqual(loads_studio(dumps_studio(studio, registry), registry), studio)

    def test_new_translation_recipe_schema_and_source_binding(self):
        recipe = _new_recipe()
        self.assertEqual(_schema_errors(recipe, "media_recipe_v1.schema.json"), [])
        self.assertEqual(recipe["steps"][0]["model"]["id"], runtime.MODEL)
        self.assertEqual(recipe["source"], _source())
        self.assertEqual(recipe["source_sha256"], _source()["content_sha256"])
        self.assertEqual(recipe["semantic_authority"], "DERIVATIVE_ONLY")
        self.assertEqual(recipe["knowledge_truth_mutation"], "DENIED")
        self.assertEqual(loads_media_recipe(dumps_media_recipe(recipe)), recipe)

    def test_cue_identity_order_timestamps_and_source_bytes_are_preserved(self):
        source_bytes = ("3\n00:00:00,125 --> 00:00:01,375\nПервая строка\nВторая строка\n\n"
                        "8\n00:00:02,500 --> 00:00:04,625\nЧисло 42\n\n"
                        "19\n00:00:07,001 --> 00:00:08,999\nИмя Анна\n").encode()
        identity = {"component": runtime.COMPONENT, "model": runtime.MODEL,
                    "model_id": MODEL_SHA, "runtime_identity_sha256": "6" * 64}
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.srt", Path(directory) / "translated.json"
            source.write_bytes(source_bytes)
            with patch.object(runtime, "preflight", return_value=identity), patch.object(
                runtime, "_translate_text", side_effect=["First line\nSecond line", "Number 42", "Name Anna"],
            ) as infer:
                result = runtime.translate(source, output, source="ru", target="en", runtime=identity)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual([c["id"] for c in result["cues"]], [3, 8, 19])
            self.assertEqual([(c["start_seconds"], c["end_seconds"]) for c in result["cues"]],
                             [(0.125, 1.375), (2.5, 4.625), (7.001, 8.999)])
            self.assertEqual([call.args[0] for call in infer.call_args_list],
                             ["Первая строка\nВторая строка", "Число 42", "Имя Анна"])
            self.assertEqual(result["model"], runtime.MODEL)
            self.assertEqual(result["semantic_status"], "MACHINE_TRANSLATION_REVIEW_REQUIRED")
            self.assertEqual(json.loads(output.read_bytes()), result)


if __name__ == "__main__":
    unittest.main()
