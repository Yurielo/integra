from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import wave

from integra_core.identity import derive_imported_id
from integra_core.media import (
    CAPABILITY_IMPLEMENTATIONS,
    MediaError,
    PINNED_VIDEOTEXT,
    create_media_recipe,
    dumps_media_recipe,
    loads_media_recipe,
    media_operation_plan,
    probe_media_capabilities,
    register_verified_derivative,
    validate_media_operation_plan,
    validate_media_recipe,
)
from integra_core.operations import JobStore, ModelResidencyStore, resume_binding, validate_job
from integra_core.protocol import canonical_json, content_sha256

NOW = "2026-09-11T00:00:00Z"
LATER = "2026-09-11T00:01:00Z"
SOURCE_PAYLOAD = b"synthetic source media"
SOURCE_SHA = hashlib.sha256(SOURCE_PAYLOAD).hexdigest()
FFPROBE = Path(__file__).parent / "fixtures" / "media_v1" / "ffprobe_fixture.py"
OPERATION_ID = derive_imported_id("operation", "integra", "media-v1", "1" * 64)
JOB_ID = derive_imported_id("job", "integra", "media-v1", "2" * 64)
RESERVATION_ID = derive_imported_id("reservation", "integra", "media-v1", "3" * 64)


def _origin() -> dict:
    return {
        "component_id": "integra", "repository": "Yurielo/integra",
        "commit_sha": "1" * 40, "tree_sha": "2" * 40, "version": "1.0",
        "contracts": ["projects_sources_v1"],
        "runtime": {"kind": "python", "version": "3"},
    }


def _artifact(kind: str, label: str, *, storage: str = "SOURCE_READ_ONLY") -> dict:
    payload = f"{kind}:{label}".encode()
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "artifact_id": derive_imported_id("artifact", "integra", label, digest),
        "kind": kind, "schema_id": f"{kind}_v1", "schema_version": "1.0",
        "semantic_status": "NOT_APPLICABLE", "content_sha256": digest,
        "size_bytes": len(payload), "storage_scope": storage,
        "relative_path": f"inputs/{label}.json", "origin": _origin(),
        "provenance": {"parent_artifact_ids": [], "operation_id": OPERATION_ID},
    }


def _source() -> dict:
    value = _artifact("source_media", "media-source")
    value["content_sha256"] = SOURCE_SHA
    value["size_bytes"] = len(SOURCE_PAYLOAD)
    value["relative_path"] = "source/source.mp4"
    return value


def _model(name: str) -> dict:
    return {
        "id": name,
        "version": "1",
        "identity_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def _model_paths(recipe: dict) -> dict[str, Path]:
    return {
        f"media:{content_sha256(model)}": Path(__file__)
        for model in [step["model"] for step in recipe["steps"] if step["model"] is not None]
    }


def _wav_payload(seconds: int = 2) -> bytes:
    payload = io.BytesIO()
    with wave.open(payload, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 8000 * seconds)
    return payload.getvalue()


def _steps() -> list[dict]:
    return [
        {"kind": "clip", "parameters": {"mode": "timecode"}, "model": None, "inputs": []},
        {"kind": "subtitles", "parameters": {
            "language": "ru", "style": {
                "text_color_hex": "#FFFFFF", "outline_color_hex": "#000000",
                "font_name": "Helvetica", "font_size": 20, "outline_width": 2,
                "position": "bottom", "background_opacity": 0,
            },
        }, "model": None, "inputs": [_artifact("subtitles", "subtitle-cues")]},
        {"kind": "translation", "parameters": {"source_language": "ru", "target_language": "en"},
         "model": _model("translation-model"), "inputs": [_artifact("transcript", "translation-input")]},
        {"kind": "tts", "parameters": {"language": "en", "voice_id": "voice", "voice_provider_version": "1", "mix_mode": "replace"},
         "model": _model("tts-model"), "inputs": [_artifact("translated_subtitles", "tts-input")]},
        {"kind": "speed", "parameters": {"factor": 1.25}, "model": None, "inputs": []},
        {"kind": "blur", "parameters": {"region": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}, "intensity": 8, "start_seconds": 0.5, "end_seconds": 1.0}, "model": None, "inputs": []},
        {"kind": "watermark", "parameters": {"position": "bottomRight", "relative_width": 0.2, "margin": 0.03, "opacity": 0.75, "start_seconds": None, "end_seconds": None},
         "model": None, "inputs": [_artifact("watermark_image", "watermark-input")]},
        {"kind": "audio_enhancement", "parameters": {"profile": "normal"}, "model": _model("uvr-dereverb-model"), "inputs": []},
        {"kind": "filler_mute", "parameters": {"candidate_ids": ["filler:1"], "intervals": [{"start_seconds": 1.1, "end_seconds": 1.3}], "fade_seconds": 0.05},
         "model": None, "inputs": [_artifact("transcript_revision", "filler-transcript"), _artifact("filler_analysis", "filler-analysis")]},
        {"kind": "qa", "parameters": {"checks": ["content_hash", "videotext_functional_validation", "output_kind_contract", "duration_or_timeline"]}, "model": None, "inputs": []},
    ]


def _recipe(*, steps: list[dict] | None = None) -> dict:
    return create_media_recipe(
        source=_source(), operation_id=OPERATION_ID,
        locator={"type": "time_interval", "start_seconds": 0.0, "end_seconds": 2.0},
        steps=_steps() if steps is None else steps, created_at=NOW,
    )


def _plan(recipe: dict) -> dict:
    report = probe_media_capabilities(
        recipe, runtime_executable_path=FFPROBE,
        model_paths=_model_paths(recipe), measured_at=NOW,
    )
    payload = canonical_json(report) + b"\n"
    digest = hashlib.sha256(payload).hexdigest()
    reference = {
        "artifact_id": derive_imported_id("artifact", "videotext", "capability-report", digest),
        "kind": "capabilityReport", "schema_id": "media_capability_report_v1", "schema_version": "1.0",
        "semantic_status": "NOT_APPLICABLE", "content_sha256": digest, "size_bytes": len(payload),
        "storage_scope": "INTEGRA_STORE", "relative_path": "inputs/capability-report.json",
        "origin": copy.deepcopy(PINNED_VIDEOTEXT),
        "provenance": {"parent_artifact_ids": [recipe["recipe_id"]], "operation_id": recipe["operation_id"]},
    }
    return media_operation_plan(
        recipe, capability_report=report, capability_report_reference=reference,
        capability_report_payload=payload,
        collection_id="playlist:1",
    )


def _output_reference(recipe: dict, payload: bytes, *, kind: str = "mutedVideo") -> dict:
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "artifact_id": derive_imported_id("artifact", "videotext", "derivative", digest),
        "kind": kind, "schema_id": "media_derivative_v1", "schema_version": "1.0",
        "semantic_status": "NOT_APPLICABLE", "content_sha256": digest,
        "size_bytes": len(payload), "storage_scope": "INTEGRA_STORE",
        "relative_path": "media/output.bin", "origin": copy.deepcopy(PINNED_VIDEOTEXT),
        "provenance": {"parent_artifact_ids": [recipe["source"]["artifact_id"], recipe["recipe_id"]],
                       "operation_id": OPERATION_ID, "source_locator": copy.deepcopy(recipe["source_locator"])},
    }


def _qa_payload(recipe: dict, plan: dict, output: dict, *, job_id: str = JOB_ID) -> bytes:
    implementations = CAPABILITY_IMPLEMENTATIONS["qa"]["implementations"]
    if output["kind"] == "subtitles":
        validator_kind, selected = "VIDEOTEXT_SRT_TIMELINE", implementations[3:]
        expected = measured = None
        streams, cue_count = [], 1
        probe = canonical_json({"cue_count": 1, "parse_errors": [], "timeline_findings": []}).decode()
    elif output["kind"] == "enhancedAudio":
        validator_kind, selected = "VIDEOTEXT_AUDIO_PROBE", implementations[1:3]
        expected = measured = 2.0
        streams, cue_count = ["audio"], None
        probe = "[STREAM]\ncodec_type=audio\nduration=2.000\n[/STREAM]"
    else:
        validator_kind, selected = "VIDEOTEXT_STRICT_VIDEO", implementations[:1]
        expected = measured = 2.0
        streams, cue_count = ["video", "audio"], None
        probe = "Ожидаемая длительность: 2.000\n[STREAM]\ncodec_type=video\nduration=2.000\n[/STREAM]\n[STREAM]\ncodec_type=audio\nduration=2.000\n[/STREAM]"
    report = {
        "schema_version": "1.0", "status": "PASS", "validator_kind": validator_kind,
        "validator_implementations": selected, "job_id": job_id,
        "operation_id": recipe["operation_id"], "recipe_id": recipe["recipe_id"],
        "recipe_sha256": recipe["recipe_sha256"], "plan_sha256": plan["plan_sha256"],
        "output_artifact_id": output["artifact_id"], "output_kind": output["kind"],
        "output_sha256": output["content_sha256"], "output_size_bytes": output["size_bytes"],
        "expected_duration_seconds": expected, "measured_duration_seconds": measured,
        "streams": streams, "cue_count": cue_count, "timeline_findings": [],
        "probe_payload": probe, "probe_sha256": hashlib.sha256(probe.encode()).hexdigest(),
        "report_sha256": "",
    }
    report["report_sha256"] = content_sha256(report)
    return canonical_json(report) + b"\n"


def _qa_reference(recipe: dict, output: dict, payload: bytes) -> dict:
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "artifact_id": derive_imported_id("artifact", "videotext", "media-qa", digest),
        "kind": "reviewReport", "schema_id": "media_qa_report_v1", "schema_version": "1.0",
        "semantic_status": "NOT_APPLICABLE", "content_sha256": digest,
        "size_bytes": len(payload), "storage_scope": "INTEGRA_STORE",
        "relative_path": "media/output.qa.json", "origin": copy.deepcopy(PINNED_VIDEOTEXT),
        "provenance": {"parent_artifact_ids": [recipe["recipe_id"], output["artifact_id"]], "operation_id": OPERATION_ID},
    }


def _succeeded_job(plan: dict, output: dict, qa: dict) -> dict:
    input_hashes = plan["input_hashes"] + [output["content_sha256"], qa["content_sha256"]]
    protocol_digest = resume_binding(JOB_ID, "videotext.media_recipe@1.0", PINNED_VIDEOTEXT["commit_sha"], input_hashes)
    execution_digest = content_sha256({
        "capability": {"id": "videotext.media_recipe", "version": "1.0"},
        "capability_report_sha256": plan["capability_report"]["report_sha256"],
        "config_sha256": plan["plan_sha256"], "job_id": JOB_ID,
        "operation_id": OPERATION_ID, "resume_scope": "PIPELINE_PREFIX",
    })
    facts = {"checkpoint_id": "media-final-output-binding", "input_hashes": input_hashes,
             "worker_commit_sha": PINNED_VIDEOTEXT["commit_sha"],
             "capability_report_sha256": plan["capability_report"]["report_sha256"],
             "config_sha256": plan["plan_sha256"], "execution_identity_sha256": execution_digest,
             "protocol_binding_sha256": protocol_digest}
    checkpoint = {**facts, "created_at": NOW, "binding_sha256": content_sha256(facts)}
    transitions = [
        (None, "QUEUED", None), ("QUEUED", "PREFLIGHT", None),
        ("PREFLIGHT", "WAITING_RESOURCES", plan["capability_report"]["report_sha256"]),
        ("WAITING_RESOURCES", "RUNNING", "2" * 64),
        ("RUNNING", "PAUSE_REQUESTED", checkpoint["binding_sha256"]),
        ("PAUSE_REQUESTED", "PAUSED", checkpoint["binding_sha256"]),
        ("PAUSED", "RESUMING", checkpoint["binding_sha256"]),
        ("RESUMING", "PREFLIGHT", checkpoint["binding_sha256"]),
        ("PREFLIGHT", "WAITING_RESOURCES", plan["capability_report"]["report_sha256"]),
        ("WAITING_RESOURCES", "RUNNING", "2" * 64), ("RUNNING", "SUCCEEDED", "3" * 64),
    ]
    events = [{"sequence": index, "at": NOW if index < 10 else LATER,
               "from_state": left, "to_state": right, "evidence_sha256": evidence}
              for index, (left, right, evidence) in enumerate(transitions)]
    value = {
        "schema_version": "1.0", "job_id": JOB_ID, "operation_id": OPERATION_ID,
        "revision": len(events), "job_class": "heavy-media",
        "capability": {"id": "videotext.media_recipe", "version": "1.0"},
        "resume_scope": "PIPELINE_PREFIX", "state": "SUCCEEDED",
        "progress": {"sequence": 1, "fraction": 1.0, "stage": "complete", "eta_status": "ESTIMATED", "eta_seconds": 0},
        "cancellation": {"requested_at": None, "acknowledged_at": None}, "checkpoint": checkpoint,
        "preflight": {"report_sha256": plan["capability_report"]["report_sha256"], "measured_at": NOW},
        "reservation_id": RESERVATION_ID, "events": events,
        "terminal": {"finished_at": LATER, "outcome": "SUCCEEDED", "error_code": None},
        "created_at": NOW, "updated_at": LATER,
    }
    validate_job(value)
    return value


def _write_job(store: JobStore, value: dict) -> None:
    store._path(value["job_id"]).write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _write_model_residencies(root: Path, recipe: dict) -> ModelResidencyStore:
    store = ModelResidencyStore(root / "models")
    seen = set()
    for model in [step["model"] for step in recipe["steps"] if step["model"] is not None]:
        if model["id"] in seen:
            continue
        seen.add(model["id"])
        residency_id = f"media:{content_sha256(model)}"
        record = {"schema_version": "1.0", "model_id": residency_id, "job_id": JOB_ID,
                  "operation_id": OPERATION_ID, "state": "RELEASED", "acquired_at": NOW, "released_at": LATER}
        store._path(residency_id).write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    return store


def _materialize_inputs(root: Path, recipe: dict, plan: dict) -> dict[str, Path]:
    input_roots = {}
    for reference in [item for step in recipe["steps"] for item in step["inputs"]]:
        path = root / reference["relative_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        label = Path(reference["relative_path"]).stem
        path.write_bytes(f"{reference['kind']}:{label}".encode())
        input_roots[reference["artifact_id"]] = root
    capability_reference = plan["capability_report_reference"]
    capability_path = root / capability_reference["relative_path"]
    capability_path.parent.mkdir(parents=True, exist_ok=True)
    capability_path.write_bytes(canonical_json(plan["capability_report"]) + b"\n")
    input_roots[capability_reference["artifact_id"]] = root
    return input_roots


def _register(root: Path, recipe: dict, plan: dict, output: dict, output_payload: bytes,
              qa: dict, qa_payload: bytes) -> dict:
    source_path = root / recipe["source"]["relative_path"]
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(SOURCE_PAYLOAD)
    input_roots = _materialize_inputs(root, recipe, plan)
    output_path = root / output["relative_path"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_payload)
    (root / qa["relative_path"]).write_bytes(qa_payload)
    jobs = JobStore(root / "jobs")
    _write_job(jobs, _succeeded_job(plan, output, qa))
    return register_verified_derivative(
        recipe, operation_plan=plan, source_root=root, input_roots=input_roots,
        output_root=root,
        output_reference=output, qa_reference=qa, job_store=jobs,
        model_residency_store=_write_model_residencies(root, recipe),
        runtime_executable_path=FFPROBE, model_paths=_model_paths(recipe), job_id=JOB_ID,
        completed_at=LATER,
    )


class MediaIntegrationTests(unittest.TestCase):
    def test_published_schemas_are_closed_and_match_runtime_bindings(self) -> None:
        root = Path(__file__).resolve().parents[1]
        recipe_schema = json.loads((root / "schemas/media_recipe_v1.schema.json").read_text())
        self.assertEqual(
            recipe_schema["properties"]["source"]["properties"]["storage_scope"]["const"],
            "SOURCE_READ_ONLY",
        )
        self.assertFalse(recipe_schema["$defs"]["component"]["additionalProperties"])
        self.assertFalse(
            recipe_schema["$defs"]["component"]["properties"]["runtime"]["additionalProperties"]
        )
        steps = recipe_schema["properties"]["steps"]
        self.assertEqual((steps["minItems"], steps["maxContains"]), (2, 1))
        branches = {
            item["properties"]["kind"]["const"]: item
            for item in steps["items"]["oneOf"]
        }
        self.assertEqual(set(branches), set(CAPABILITY_IMPLEMENTATIONS))
        for kind, binding in CAPABILITY_IMPLEMENTATIONS.items():
            properties = branches[kind]["properties"]
            self.assertEqual(properties["videotext_operations"]["const"], binding["videotext_operations"])
            self.assertEqual(properties["videotext_artifact_kind"]["const"], binding["artifact_kind"])
            self.assertFalse(branches[kind]["additionalProperties"])
        derivative = json.loads((root / "schemas/media_derivative_v1.schema.json").read_text())
        self.assertTrue({"plan_sha256", "execution_checkpoint", "qa"}.issubset(derivative["required"]))
        self.assertIn("reference", derivative["properties"]["qa"]["required"])
        qa = json.loads((root / "schemas/media_qa_report_v1.schema.json").read_text())
        self.assertFalse(qa["additionalProperties"])
        self.assertIn("validator_implementations", qa["required"])
        capability = json.loads((root / "schemas/media_capability_report_v1.schema.json").read_text())
        self.assertFalse(capability["additionalProperties"])
        self.assertEqual(capability["properties"]["component"]["const"], PINNED_VIDEOTEXT)
        self.assertIn("runtime_probe", capability["required"])

    def test_exact_pinned_videotext_functions_are_exposed(self) -> None:
        expected = {"clip": ["cutAccurate"], "subtitles": ["burnSubtitles"],
                    "translation": ["translate"], "tts": ["synthesize"],
                    "speed": ["adjustSpeed"], "blur": ["applyStaticBlur"],
                    "watermark": ["applyWatermark"], "audio_enhancement": ["enhance"],
                    "filler_mute": ["analyze", "muteAudioIntervals"],
                    "qa": ["strictValidationReport", "validate", "duration", "parseWithReport", "validateTimeline"]}
        self.assertEqual({kind: value["videotext_operations"] for kind, value in CAPABILITY_IMPLEMENTATIONS.items()}, expected)

    def test_recipe_is_deterministic_content_bound_and_round_trips(self) -> None:
        left, right = _recipe(), _recipe()
        self.assertEqual(left, right)
        self.assertEqual(loads_media_recipe(dumps_media_recipe(left)), left)
        self.assertEqual([item["kind"] for step in left["steps"] for item in step["inputs"]],
                         ["subtitles", "transcript", "translated_subtitles", "watermark_image", "transcript_revision", "filler_analysis"])
        changed = _steps(); changed[1]["inputs"][0]["content_sha256"] = "0" * 64
        self.assertNotEqual(_recipe(steps=changed)["recipe_sha256"], left["recipe_sha256"])

    def test_operation_plan_binds_measured_capabilities_models_and_all_inputs(self) -> None:
        recipe = _recipe(); plan = _plan(recipe)
        validate_media_operation_plan(plan, recipe)
        self.assertEqual(plan["resource_request"]["collection_kind"], "PLAYLIST")
        self.assertEqual([item["id"] for item in plan["model_bindings"]], ["translation-model", "tts-model", "uvr-dereverb-model"])
        self.assertEqual(
            plan["capability_report"]["models"][0]["status"],
            "MEASURED_AVAILABLE",
        )
        self.assertTrue(plan["capability_report"]["runtime_probe"]["version"].startswith("ffprobe version "))
        self.assertEqual(len(plan["input_hashes"]), 9)
        tampered = copy.deepcopy(plan); tampered["capability_report"]["models"][0]["identity_sha256"] = "0" * 64
        with self.assertRaises(MediaError):
            validate_media_operation_plan(tampered, recipe)

    def test_verified_derivative_requires_exact_plan_checkpoint_output_and_worker_qa(self) -> None:
        recipe = _recipe(steps=[_steps()[7], _steps()[-1]]); plan = _plan(recipe)
        payload = _wav_payload()
        output = _output_reference(recipe, payload, kind="enhancedAudio")
        qa_payload = _qa_payload(recipe, plan, output); qa = _qa_reference(recipe, output, qa_payload)
        with tempfile.TemporaryDirectory() as temporary:
            record = _register(Path(temporary), recipe, plan, output, payload, qa, qa_payload)
        self.assertEqual(record["qa"]["validator_kind"], "VIDEOTEXT_AUDIO_PROBE")
        self.assertEqual(record["plan_sha256"], plan["plan_sha256"])
        self.assertEqual(record["execution_checkpoint"]["input_hashes"][-2:], [output["content_sha256"], qa["content_sha256"]])

    def test_wrong_recipe_cannot_reuse_successful_job(self) -> None:
        recipe_a = _recipe(); plan_a = _plan(recipe_a); payload = b"output"
        output_a = _output_reference(recipe_a, payload); qa_payload_a = _qa_payload(recipe_a, plan_a, output_a)
        qa_a = _qa_reference(recipe_a, output_a, qa_payload_a)
        changed = _steps(); changed[4]["parameters"]["factor"] = 1.75
        recipe_b = _recipe(steps=changed); plan_b = _plan(recipe_b)
        output_b = _output_reference(recipe_b, payload); qa_payload_b = _qa_payload(recipe_b, plan_b, output_b)
        qa_b = _qa_reference(recipe_b, output_b, qa_payload_b)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / output_b["relative_path"]).parent.mkdir(parents=True)
            (root / output_b["relative_path"]).write_bytes(payload); (root / qa_b["relative_path"]).write_bytes(qa_payload_b)
            jobs = JobStore(root / "jobs"); _write_job(jobs, _succeeded_job(plan_a, output_a, qa_a))
            with self.assertRaisesRegex(MediaError, "exact plan and outputs"):
                source_path = root / recipe_b["source"]["relative_path"]
                source_path.parent.mkdir(parents=True, exist_ok=True); source_path.write_bytes(SOURCE_PAYLOAD)
                register_verified_derivative(recipe_b, operation_plan=plan_b, source_root=root,
                    input_roots=_materialize_inputs(root, recipe_b, plan_b), output_root=root,
                    output_reference=output_b, qa_reference=qa_b, job_store=jobs,
                    model_residency_store=_write_model_residencies(root, recipe_b),
                    runtime_executable_path=FFPROBE, model_paths=_model_paths(recipe_b),
                    job_id=JOB_ID, completed_at=LATER)

    def test_intermediate_artifact_cannot_masquerade_as_final_output(self) -> None:
        recipe, payload = _recipe(), b"intermediate-output"
        plan = _plan(recipe)
        output = _output_reference(recipe, payload, kind="watermarkedVideo")
        qa_payload = _qa_payload(recipe, plan, output); qa = _qa_reference(recipe, output, qa_payload)
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(MediaError, "final recipe operation"):
            _register(Path(temporary), recipe, plan, output, payload, qa, qa_payload)

    def test_missing_or_changed_auxiliary_input_bytes_fail_closed(self) -> None:
        recipe, payload = _recipe(), b"output"; plan = _plan(recipe)
        output = _output_reference(recipe, payload)
        qa_payload = _qa_payload(recipe, plan, output); qa = _qa_reference(recipe, output, qa_payload)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / recipe["source"]["relative_path"]
            source.parent.mkdir(parents=True); source.write_bytes(SOURCE_PAYLOAD)
            output_path = root / output["relative_path"]
            output_path.parent.mkdir(parents=True); output_path.write_bytes(payload)
            (root / qa["relative_path"]).write_bytes(qa_payload)
            roots = _materialize_inputs(root, recipe, plan)
            watermark = next(item for step in recipe["steps"] for item in step["inputs"] if item["kind"] == "watermark_image")
            (root / watermark["relative_path"]).write_bytes(b"changed-watermark")
            jobs = JobStore(root / "jobs"); _write_job(jobs, _succeeded_job(plan, output, qa))
            with self.assertRaisesRegex(MediaError, "changed between Integrity"):
                register_verified_derivative(
                    recipe, operation_plan=plan, source_root=root, input_roots=roots,
                    output_root=root, output_reference=output, qa_reference=qa,
                    job_store=jobs, model_residency_store=_write_model_residencies(root, recipe),
                    runtime_executable_path=FFPROBE, model_paths=_model_paths(recipe),
                    job_id=JOB_ID, completed_at=LATER,
                )

    def test_fully_rehashed_forged_qa_cannot_validate_non_media_bytes(self) -> None:
        recipe, payload = _recipe(), b"definitely-not-media"; plan = _plan(recipe)
        output = _output_reference(recipe, payload)
        qa_payload = _qa_payload(recipe, plan, output)
        qa = _qa_reference(recipe, output, qa_payload)
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(
            MediaError, "independent ffprobe"
        ):
            _register(Path(temporary), recipe, plan, output, payload, qa, qa_payload)

    def test_subtitle_and_audio_variants_require_exact_qa_contracts(self) -> None:
        for steps, kind, expected in (([_steps()[2], _steps()[-1]], "subtitles", "VIDEOTEXT_SRT_TIMELINE"),
                                      ([_steps()[7], _steps()[-1]], "enhancedAudio", "VIDEOTEXT_AUDIO_PROBE")):
            recipe = _recipe(steps=steps); plan = _plan(recipe)
            payload = (
                b"1\n00:00:00,000 --> 00:00:01,000\nSubtitle\n"
                if kind == "subtitles" else _wav_payload()
            )
            output = _output_reference(recipe, payload, kind=kind)
            qa_payload = _qa_payload(recipe, plan, output); qa = _qa_reference(recipe, output, qa_payload)
            with tempfile.TemporaryDirectory() as temporary:
                record = _register(Path(temporary), recipe, plan, output, payload, qa, qa_payload)
            self.assertEqual(record["qa"]["validator_kind"], expected)

    def test_missing_external_inputs_and_model_identity_fail_closed(self) -> None:
        steps = _steps(); steps[1]["inputs"] = []
        with self.assertRaisesRegex(MediaError, "content-bound input"):
            _recipe(steps=steps)
        steps = _steps(); steps[2]["model"] = None
        with self.assertRaisesRegex(MediaError, "model binding"):
            _recipe(steps=steps)
        steps = _steps(); steps[3]["model"] = {**steps[2]["model"], "identity_sha256": "0" * 64}
        with self.assertRaisesRegex(MediaError, "conflicting identities"):
            _recipe(steps=steps)

    def test_duplicate_artifact_identity_cannot_collapse_distinct_inputs(self) -> None:
        steps = _steps()
        duplicated = copy.deepcopy(steps[8]["inputs"][0])
        duplicated["kind"] = "filler_analysis"
        duplicated["relative_path"] = "inputs/other-analysis.json"
        steps[8]["inputs"][1] = duplicated
        with self.assertRaisesRegex(MediaError, "globally unique"):
            _recipe(steps=steps)

    def test_capability_models_are_remeasured_before_registration(self) -> None:
        recipe = _recipe(steps=[_steps()[7], _steps()[-1]])
        plan = _plan(recipe)
        payload = _wav_payload()
        output = _output_reference(recipe, payload, kind="enhancedAudio")
        qa_payload = _qa_payload(recipe, plan, output)
        qa = _qa_reference(recipe, output, qa_payload)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad_model = root / "changed-model.bin"
            bad_model.write_bytes(b"not-the-measured-model")
            model_paths = {
                key: bad_model for key in _model_paths(recipe)
            }
            source_path = root / recipe["source"]["relative_path"]
            source_path.parent.mkdir(parents=True); source_path.write_bytes(SOURCE_PAYLOAD)
            input_roots = _materialize_inputs(root, recipe, plan)
            output_path = root / output["relative_path"]
            output_path.parent.mkdir(parents=True); output_path.write_bytes(payload)
            (root / qa["relative_path"]).write_bytes(qa_payload)
            jobs = JobStore(root / "jobs"); _write_job(jobs, _succeeded_job(plan, output, qa))
            with self.assertRaisesRegex(MediaError, "measured media model"):
                register_verified_derivative(
                    recipe, operation_plan=plan, source_root=root,
                    input_roots=input_roots, output_root=root,
                    output_reference=output, qa_reference=qa, job_store=jobs,
                    model_residency_store=_write_model_residencies(root, recipe),
                    runtime_executable_path=FFPROBE, model_paths=model_paths,
                    job_id=JOB_ID, completed_at=LATER,
                )

    def test_recipe_tampering_and_authority_fail_closed(self) -> None:
        recipe = _recipe(); mutations = []
        changed = copy.deepcopy(recipe); changed["component"]["commit_sha"] = "0" * 40; mutations.append(changed)
        changed = copy.deepcopy(recipe); changed["steps"][0]["implementations"][0]["function"] = "cutRange"; mutations.append(changed)
        changed = copy.deepcopy(recipe); changed["steps"][-1]["parameters"]["checks"] = ["hash"]; mutations.append(changed)
        changed = copy.deepcopy(recipe); changed["knowledge_truth_mutation"] = "ALLOW"; mutations.append(changed)
        for value in mutations:
            with self.assertRaises(MediaError):
                validate_media_recipe(value)
        source = _source(); source["storage_scope"] = "INTEGRA_STORE"
        with self.assertRaisesRegex(MediaError, "read-only"):
            create_media_recipe(source=source, operation_id=OPERATION_ID,
                                locator={"type": "time_interval", "start_seconds": 0, "end_seconds": 1},
                                steps=_steps(), created_at=NOW)


if __name__ == "__main__":
    unittest.main()
