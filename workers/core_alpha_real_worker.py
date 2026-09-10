#!/usr/bin/env python3
"""Execute one pinned R6 stage behind the accepted local stdio JSONL contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integra_core.core_alpha import (  # noqa: E402
    STAGE_CAPABILITIES,
    STAGE_COMPONENTS,
    STAGE_PARENTS,
    load_component_identities,
    reject_symlink_components,
    stage_output_contract,
)
from integra_core.identity import derive_imported_id  # noqa: E402
from integra_core.protocol import (  # noqa: E402
    PROTOCOL_VERSION,
    canonical_json,
    content_sha256,
    validate_artifact_reference,
    validate_message,
)
from integra_core.real_media import aggregate_whisper_words, sha256_file  # noqa: E402


SEMANTIC_STATUS = {
    "transcript": "REVIEW_REQUIRED",
    "topics": "REVIEW_REQUIRED",
    "review": "REVIEW_REQUIRED",
    "knowledge": "PROVISIONAL",
    "media_clip": "NOT_APPLICABLE",
}
CONFIG_FIELDS = {
    "artifact_store",
    "session_store",
    "seminartext_checkout",
    "videotext_checkout",
    "whisper_model",
    "whisper_model_sha256",
    "topic_model",
    "topic_model_digest",
    "source_sha256",
    "source_suffix",
}


class WorkerFailure(RuntimeError):
    pass


def run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise WorkerFailure(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_marker(output: str, marker: str) -> dict[str, Any]:
    values = [line[len(marker) + 1 :] for line in output.splitlines() if line.startswith(marker + " ")]
    if len(values) != 1:
        raise WorkerFailure(f"component did not emit exactly one {marker}")
    value = json.loads(values[0])
    if not isinstance(value, dict):
        raise WorkerFailure(f"{marker} payload is invalid")
    return value


def build_videotext_worker(checkout: Path, worker: Path, output: Path) -> None:
    swift_sources = sorted(
        path
        for path in (checkout / "Sources/videotext").rglob("*.swift")
        if "/App/" not in path.as_posix() and "/UI/" not in path.as_posix()
    )
    if not swift_sources:
        raise WorkerFailure("pinned VideoText sources are missing")
    run(
        [
            "swiftc",
            "-O",
            "-framework",
            "SwiftUI",
            "-framework",
            "AppKit",
            "-framework",
            "AVKit",
            "-framework",
            "AVFoundation",
            "-framework",
            "UserNotifications",
            "-o",
            str(output),
            *map(str, swift_sources),
            str(worker),
        ]
    )


def confined(path: Path, root: Path, label: str) -> Path:
    candidate = path.expanduser().absolute()
    reject_symlink_components(candidate, label=label)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise WorkerFailure(f"{label} escaped its governed root") from error
    return resolved


def read_input(reference: dict[str, Any], artifact_store: Path) -> tuple[Path, bytes]:
    validate_artifact_reference(reference)
    path = confined(artifact_store / reference["relative_path"], artifact_store, "job input")
    if not path.is_file():
        raise WorkerFailure("job input artifact is missing")
    payload = path.read_bytes()
    if len(payload) != reference["size_bytes"] or hashlib.sha256(payload).hexdigest() != reference["content_sha256"]:
        raise WorkerFailure("job input artifact content differs")
    return path, payload


def read_json_input(reference: dict[str, Any], artifact_store: Path, stage: str) -> dict[str, Any]:
    _, payload = read_input(reference, artifact_store)
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkerFailure(f"{stage} input is not JSON") from error
    if not isinstance(value, dict) or value.get("stage") != stage:
        raise WorkerFailure(f"expected {stage} input payload")
    return value


def source_path(config: dict[str, Any], artifact_store: Path) -> Path:
    source_hash = config["source_sha256"]
    candidates = list(artifact_store.glob(f"projects/*/artifacts/{source_hash}.source"))
    if len(candidates) != 1:
        raise WorkerFailure("governed source artifact cannot be resolved uniquely")
    path = confined(candidates[0], artifact_store, "source artifact")
    if sha256_file(path) != source_hash:
        raise WorkerFailure("governed source artifact hash differs")
    return path


def stage_payload(
    stage: str,
    inputs: list[dict[str, Any]],
    result: dict[str, Any],
    stage_data: dict[str, Any],
) -> bytes:
    return canonical_json(
        {
            "input_artifact_ids": [item["artifact_id"] for item in inputs],
            "input_content_sha256": [item["content_sha256"] for item in inputs],
            "result": result,
            "schema_version": "1.0",
            "semantic_status": SEMANTIC_STATUS[stage],
            "stage": stage,
            "stage_data": stage_data,
        }
    )


def execute_transcript(config: dict[str, Any], inputs: list[dict[str, Any]], session: Path) -> tuple[bytes, dict[str, Any]]:
    artifact_store = Path(config["artifact_store"])
    governed_media, _ = read_input(inputs[0], artifact_store)
    output_root = session / "transcript"
    output_root.mkdir(parents=True, exist_ok=False)
    media = output_root / f"source{config['source_suffix']}"
    shutil.copy2(governed_media, media)
    if sha256_file(media) != config["source_sha256"]:
        raise WorkerFailure("transcript source copy differs")
    binary = output_root / "videotext-transcript-worker"
    build_videotext_worker(
        Path(config["videotext_checkout"]),
        ROOT / "workers/videotext_transcript_worker.swift",
        binary,
    )
    environment = os.environ.copy()
    environment["VIDEOTEXT_HISTORY_PATH"] = str(output_root / "videotext-history.json")
    result = parse_marker(
        run([str(binary), str(media), config["whisper_model"]], env=environment),
        "INTEGRA_VIDEOTEXT_TRANSCRIPT_RESULT",
    )
    if result.get("review_checkpoint") != "SOURCE_TRANSCRIPT" or result.get("semantic_authority") != "MACHINE_UNVERIFIED":
        raise WorkerFailure("VideoText did not stop at SOURCE_TRANSCRIPT")
    files = {
        name: confined(Path(result[field]), session, f"VideoText {name}")
        for name, field in {
            "srt": "srt_path",
            "transcript": "transcript_path",
            "whisper": "whisper_json_path",
        }.items()
    }
    whisper = json.loads(files["whisper"].read_text(encoding="utf-8"))
    words, omitted = aggregate_whisper_words(whisper)
    transcript_text = files["transcript"].read_text(encoding="utf-8")
    payload = stage_payload(
        "transcript",
        inputs,
        {
            "assurance": "MACHINE_UNVERIFIED",
            "language": "ru",
            "text_sha256": hashlib.sha256(transcript_text.encode("utf-8")).hexdigest(),
            "word_count": len(words),
        },
        {
            "review_checkpoint": "SOURCE_TRANSCRIPT",
            "srt_text": files["srt"].read_text(encoding="utf-8"),
            "transcript_text": transcript_text,
            "whisper_document": whisper,
            "word_intervals": words,
            "omitted_zero_duration_tokens": omitted,
        },
    )
    return payload, {
        "type": "time_interval",
        "start_seconds": words[0]["start"],
        "end_seconds": words[-1]["end"],
    }


def execute_topics(config: dict[str, Any], inputs: list[dict[str, Any]], session: Path) -> tuple[bytes, dict[str, Any]]:
    artifact_store = Path(config["artifact_store"])
    transcript = read_json_input(inputs[0], artifact_store, "transcript")
    output_root = session / "topics"
    output_root.mkdir(parents=True, exist_ok=False)
    srt = output_root / "input.srt"
    srt.write_text(transcript["stage_data"]["srt_text"], encoding="utf-8")
    output = output_root / "topics.json"
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    run(
        [
            sys.executable,
            str(ROOT / "workers/seminartext_topics_worker.py"),
            "--checkout",
            config["seminartext_checkout"],
            "--srt",
            str(srt),
            "--output",
            str(output),
            "--model",
            config["topic_model"],
        ],
        env=environment,
    )
    document = json.loads(output.read_text(encoding="utf-8"))
    topics = document.get("topics")
    if not isinstance(topics, list) or len(topics) != 1:
        raise WorkerFailure("bounded R6 execution requires exactly one Topic draft")
    if any(item.get("semantic_status") != "REVIEW_REQUIRED" for item in topics):
        raise WorkerFailure("machine Topic escaped REVIEW_REQUIRED")
    topic = topics[0]
    payload = stage_payload(
        "topics",
        inputs,
        {"topic_count": len(topics), "model_digest": config["topic_model_digest"]},
        {"topics_document": document},
    )
    return payload, {
        "type": "time_interval",
        "start_seconds": float(topic["start_seconds"]),
        "end_seconds": float(topic["end_seconds"]),
    }


def make_topic_drafts(bundle: dict[str, Any], topic: dict[str, Any], model: str) -> dict[str, Any]:
    revision = bundle["transcript_revisions"][0]
    first, last = bundle["words"][0], bundle["words"][-1]
    config_hash = hashlib.sha256(
        f"seminartext_topics:detail=low:model={model}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "1.0.0",
        "artifact_type": "seminartext.topic_drafts",
        "artifact_id": "topic_drafts_integra_r6_actual_v1",
        "project": {"id": bundle["project"]["id"], "title": bundle["project"]["title"]},
        "seminar": {"id": "seminar_integra_r6_core_alpha", "title": "Integra R6 Core Alpha"},
        "generator": {"id": "seminartext_topics", "version": "4.0.0", "configuration_sha256": config_hash},
        "evidence": [{"id": "evidence_integra_r6_topic_001", "claim": "Machine-generated transcript interval supporting the provisional Topic draft.", "source_id": revision["source_id"], "transcript_revision_id": revision["id"], "word_start_id": first["id"], "word_end_id": last["id"]}],
        "topics": [{"id": "topic_integra_r6_001", "seminar_id": "seminar_integra_r6_core_alpha", "source_id": revision["source_id"], "transcript_revision_id": revision["id"], "topic_set_id": "topic_set_integra_r6_actual_v1", "sequence": 0, "word_start_id": first["id"], "word_end_id": last["id"], "proposed_title": topic["title"], "proposed_summary": topic["summary"], "evidence_refs": ["evidence_integra_r6_topic_001"], "semantic_origin": "machine_assisted", "lifecycle_status": "REVIEW_REQUIRED"}],
    }


def execute_review(config: dict[str, Any], inputs: list[dict[str, Any]], session: Path) -> tuple[bytes, None]:
    artifact_store = Path(config["artifact_store"])
    transcript = read_json_input(inputs[0], artifact_store, "transcript")
    topics_payload = read_json_input(inputs[1], artifact_store, "topics")
    topics = topics_payload["stage_data"]["topics_document"]["topics"]
    project_root = session / "review" / "projects"
    project_root.mkdir(parents=True, exist_ok=False)
    title = f"Integra R6 {config['source_sha256'][:12]}"
    cli = str(Path(config["seminartext_checkout"]) / "seminartext")
    environment = os.environ.copy()
    environment["SEMINARTEXT_PROJECTS"] = str(project_root)
    run([cli, "init", title], env=environment)
    project = project_root / title
    review_source = session / "review" / f"source{config['source_suffix']}"
    shutil.copy2(source_path(config, artifact_store), review_source)
    if sha256_file(review_source) != config["source_sha256"]:
        raise WorkerFailure("review source copy differs")
    run([cli, "project-add", str(project), "--video-link", str(review_source)], env=environment)
    project_transcript = project / "transcript/video_001/transcript.txt"
    project_transcript.parent.mkdir(parents=True)
    project_transcript.write_text(transcript["stage_data"]["transcript_text"], encoding="utf-8")
    alignment = {
        "aligner": "videotext.whisper-cli-token-timestamps",
        "aligner_version": "0.6.4",
        "config": {"language": "ru", "mode": "whisper_token_aggregation", "no_asr": False},
        "model": Path(config["whisper_model"]).name,
        "model_revision": "local_whisper_cpp_model_file",
        "model_sha256": config["whisper_model_sha256"],
        "words": transcript["stage_data"]["word_intervals"],
    }
    alignment_path = project / "alignment.json"
    write_json(alignment_path, alignment)
    promoted = json.loads(run([cli, "project-promote-transcript", str(project), "--source-id", "video_001", "--text-file", str(project_transcript), "--state", "review_required", "--generation-method", "videotext_whisper_cli_0_6_4"], env=environment))
    aligned = json.loads(run([cli, "project-align", str(project), "--source-id", "video_001", "--revision-id", promoted["revision_id"], "--alignment-json", str(alignment_path), "--media", str(project / f"source/video/{review_source.name}")], env=environment))
    evidence_check = json.loads(run([cli, "project-evidence-check", str(project), "--json"], env=environment))
    if evidence_check.get("status") != "PASS" or aligned.get("status") != "review_required":
        raise WorkerFailure("SeminarText Canonical Evidence validation failed")
    # The CLI reports its local project path for diagnostics. Persist a stable
    # project-relative locator so independent runs produce identical artifacts.
    if "bundle" in aligned:
        aligned["bundle"] = "evidence/canonical_bundle.json"
    bundle = json.loads((project / "evidence/canonical_bundle.json").read_text(encoding="utf-8"))
    drafts = make_topic_drafts(bundle, topics[0], config["topic_model"])
    drafts_path = project / "topic_drafts.json"
    write_json(drafts_path, drafts)
    review_dir = project / "review"
    review = json.loads(run([cli, "project-review-prepare", str(project), "--drafts", str(drafts_path), "--output", str(review_dir)], env=environment))
    if review.get("status") != "REVIEW_REQUIRED" or review.get("unreviewed") != 1:
        raise WorkerFailure("exception-only review package did not remain unresolved")
    review_package = json.loads((review_dir / "review_package.json").read_text(encoding="utf-8"))
    return stage_payload(
        "review",
        inputs,
        {"unreviewed": 1, "human_decision_required": True, "technical_status": "REVIEW_REQUIRED"},
        {
            "alignment_result": aligned,
            "canonical_bundle": bundle,
            "review_package": review_package,
        },
    ), None


def make_knowledge_input(bundle: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    source = bundle["sources"][0]
    revision = bundle["transcript_revisions"][0]
    first, last = bundle["words"][0], bundle["words"][-1]
    topic = review["topics"][0]
    artifact_id = "project_knowledge_input_integra_r6_actual_v1"
    provenance = {"origin": "derived", "source_artifact_id": artifact_id}
    return {
        "schema_version": "1.0.0", "artifact_type": "seminartext.project_knowledge_input", "artifact_id": artifact_id,
        "project": {"id": bundle["project"]["id"], "title": bundle["project"]["title"], "status": "PROVISIONAL", "version": 1, "provenance": provenance},
        "seminars": [{"id": "seminar_integra_r6_core_alpha", "project_id": bundle["project"]["id"], "title": "Integra R6 Core Alpha", "status": "PROVISIONAL", "version": 1, "topic_refs": ["topic_integra_r6_001"], "provenance": provenance}],
        "topics": [{"id": "topic_integra_r6_001", "seminar_id": "seminar_integra_r6_core_alpha", "title": topic["proposed_title"], "summary": topic["proposed_summary"], "status": "PROVISIONAL", "version": 1, "order_scope": {"sequence": 0}, "temporal_scope": {"start_seconds": first["start_seconds"], "end_seconds": last["end_seconds"]}, "source_scope": {"source_ids": [source["id"]], "transcript_revision_ids": [revision["id"]], "order_start": 0, "order_end": last["sequence"]}, "concept_refs": [], "evidence_refs": ["evidence_integra_r6_topic_001"], "provenance": {"origin": "derived", "source_artifact_id": artifact_id, "source_status": "product_review_required"}}],
        "topic_sources": [{"topic_id": "topic_integra_r6_001", "topic_set_id": "topic_set_integra_r6_actual_v1", "transcript_revision_id": revision["id"], "sequence": 0, "word_start_id": first["id"], "word_end_id": last["id"], "origin": "semi_automatic"}],
        "concepts": [], "relations": [], "review_decisions": [],
        "evidence": [{"id": "evidence_integra_r6_topic_001", "claim": "Machine-generated transcript interval supporting the provisional Topic draft.", "source_id": source["id"], "transcript_revision_id": revision["id"], "word_start_id": first["id"], "word_end_id": last["id"]}],
        "coverage": [{"source_id": source["id"], "status": "COVERED", "reason": "Machine-assisted provisional Topic and exact source evidence are supplied; semantic review remains required."}],
        "relation_type_registry": [
            {"id": "supports", "description": "The source concept provides support for the target claim."},
            {"id": "contradicts", "description": "The source and target claims are explicitly competing or conflicting."},
            {"id": "refines", "description": "The source concept narrows or elaborates the target concept."},
            {"id": "depends_on", "description": "The source concept requires the target concept as a prerequisite."},
            {"id": "associated_with", "description": "The source and target concepts are associated without an inferred ontology."},
        ],
    }


def execute_knowledge(config: dict[str, Any], inputs: list[dict[str, Any]], session: Path) -> tuple[bytes, dict[str, Any]]:
    artifact_store = Path(config["artifact_store"])
    transcript = read_json_input(inputs[0], artifact_store, "transcript")
    read_json_input(inputs[1], artifact_store, "topics")
    review = read_json_input(inputs[2], artifact_store, "review")
    stage_data = review["stage_data"]
    project = session / "knowledge" / "project"
    (project / "evidence").mkdir(parents=True, exist_ok=False)
    write_json(project / "evidence" / "canonical_bundle.json", stage_data["canonical_bundle"])
    knowledge_input = make_knowledge_input(stage_data["canonical_bundle"], stage_data["review_package"])
    input_path = project / "knowledge_input.json"
    write_json(input_path, knowledge_input)
    destination = session / "knowledge" / "view"
    cli = str(Path(config["seminartext_checkout"]) / "seminartext")
    environment = os.environ.copy()
    environment["SEMINARTEXT_PROJECTS"] = str(session / "knowledge")
    result = json.loads(run([cli, "project-obsidian-export", str(project), "--knowledge-input", str(input_path), "--destination", str(destination)], env=environment))
    if result.get("status") != "EXPORTED":
        raise WorkerFailure("provisional knowledge view was not exported")
    manifest_path = destination / ".seminartext-export.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    words = transcript["stage_data"]["word_intervals"]
    return stage_payload(
        "knowledge",
        inputs,
        {"lifecycle": "PROVISIONAL", "manifest_sha256": sha256_file(manifest_path)},
        {"export_manifest": manifest},
    ), {"type": "time_interval", "start_seconds": words[0]["start"], "end_seconds": words[-1]["end"]}


def execute_media_clip(config: dict[str, Any], inputs: list[dict[str, Any]], session: Path) -> tuple[bytes, dict[str, Any]]:
    artifact_store = Path(config["artifact_store"])
    governed_media, _ = read_input(inputs[0], artifact_store)
    topics = read_json_input(inputs[1], artifact_store, "topics")
    read_json_input(inputs[2], artifact_store, "review")
    topic = topics["stage_data"]["topics_document"]["topics"][0]
    output_root = session / "media_clip"
    output_root.mkdir(parents=True, exist_ok=False)
    media = output_root / f"source{config['source_suffix']}"
    shutil.copy2(governed_media, media)
    if sha256_file(media) != config["source_sha256"]:
        raise WorkerFailure("clip source copy differs")
    binary = output_root / "videotext-clip-worker"
    build_videotext_worker(
        Path(config["videotext_checkout"]),
        ROOT / "workers/videotext_clip_worker.swift",
        binary,
    )
    output = output_root / "topic-001.mp4"
    result = parse_marker(
        run([str(binary), str(media), str(topic["start_seconds"]), str(topic["end_seconds"]), str(output)]),
        "INTEGRA_VIDEOTEXT_CLIP_RESULT",
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise WorkerFailure("VideoText media clip output is missing")
    return output.read_bytes(), {
        "type": "time_interval",
        "start_seconds": float(result["start_seconds"]),
        "end_seconds": float(result["end_seconds"]),
    }


EXECUTORS = {
    "transcript": execute_transcript,
    "topics": execute_topics,
    "review": execute_review,
    "knowledge": execute_knowledge,
    "media_clip": execute_media_clip,
}


def message(kind: str, correlation: str, discriminator: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "message_id": derive_imported_id("message", "integra", f"{discriminator}:{correlation}", content_sha256(payload)),
        "correlation_id": correlation,
        "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "type": kind,
        "payload": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=sorted(EXECUTORS), required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config_path = args.config.expanduser().absolute()
    reject_symlink_components(config_path, label="worker config")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != CONFIG_FIELDS:
        raise WorkerFailure("worker config fields differ from R6")
    artifact_store = Path(config["artifact_store"]).resolve()
    session = Path(config["session_store"]).resolve()
    for path, label in ((artifact_store, "artifact store"), (session, "session store")):
        reject_symlink_components(path, label=label)
    handshake_line = sys.stdin.buffer.readline()
    if not handshake_line or handshake_line.count(b"\n") != 1:
        raise WorkerFailure("worker requires one JSONL handshake request")
    handshake = json.loads(handshake_line)
    validate_message(handshake)
    if handshake["type"] != "HANDSHAKE_REQUEST":
        raise WorkerFailure("worker request lifecycle must start with HANDSHAKE_REQUEST")
    stage = args.stage
    capability = STAGE_CAPABILITIES[stage]
    if handshake["payload"]["requested_capabilities"] != [capability]:
        raise WorkerFailure("requested capability differs from stage")
    expected_parents = STAGE_PARENTS[stage]
    components = load_component_identities(ROOT)
    component = components[STAGE_COMPONENTS[stage]]
    worker_identity = dict(component)
    if stage == "transcript":
        worker_identity["models"] = [{"id": Path(config["whisper_model"]).name, "identity_sha256": config["whisper_model_sha256"]}]
    elif stage == "topics":
        worker_identity["models"] = [{"id": config["topic_model"], "identity_sha256": config["topic_model_digest"]}]
    kind, schema_id = stage_output_contract(stage, "PINNED_REAL_MEDIA")
    expected_input_schemas = [
        "local_video_v1"
        if parent == "source"
        else stage_output_contract(parent, "PINNED_REAL_MEDIA")[1]
        for parent in expected_parents
    ]
    response = message(
        "HANDSHAKE_RESPONSE",
        handshake["correlation_id"],
        "handshake-response",
        {
            "selected_protocol_version": PROTOCOL_VERSION,
            "worker": worker_identity,
            "capabilities": [{
                "id": capability,
                "version": "1.0",
                "input_schema_ids": expected_input_schemas,
                "output_schema_ids": [schema_id],
                "supports_resume": False,
            }],
            "compatibility": {"schema_policy": "EXACT_SCHEMA_VERSION", "backward_compatible_protocol_versions": []},
        },
    )
    validate_message(response)
    sys.stdout.buffer.write(canonical_json(response) + b"\n")
    sys.stdout.buffer.flush()
    job_line = sys.stdin.buffer.readline()
    if not job_line or job_line.count(b"\n") != 1 or sys.stdin.buffer.readline():
        raise WorkerFailure("worker requires exactly one JSONL job after handshake")
    job = json.loads(job_line)
    validate_message(job)
    if job["type"] != "JOB_REQUEST" or handshake["correlation_id"] != job["correlation_id"]:
        raise WorkerFailure("worker job lifecycle or correlation differs")
    if job["payload"]["capability"] != capability:
        raise WorkerFailure("job capability differs from stage")
    inputs = job["payload"]["inputs"]
    if len(inputs) != len(expected_parents) or [item["schema_id"] for item in inputs] != expected_input_schemas:
        raise WorkerFailure("stage inputs differ from the declared capability")
    for reference in inputs:
        read_input(reference, artifact_store)
    payload, locator = EXECUTORS[stage](config, inputs, session)
    digest = hashlib.sha256(payload).hexdigest()
    suffix = "bin" if stage == "media_clip" else "json"
    job_key = job["payload"]["job_id"].rsplit(":", 1)[-1]
    relative = f".staging/{job_key}/{digest}.{suffix}"
    output_path = confined(artifact_store / relative, artifact_store, "worker output")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + f".tmp-{os.getpid()}")
    temporary.write_bytes(payload)
    os.replace(temporary, output_path)
    provenance: dict[str, Any] = {
        "parent_artifact_ids": [item["artifact_id"] for item in inputs],
        "operation_id": job["payload"]["operation_id"],
    }
    if locator is not None:
        provenance["source_locator"] = locator
    reference = {
        "artifact_id": derive_imported_id("artifact", component["component_id"], stage, digest),
        "kind": kind,
        "schema_id": schema_id,
        "schema_version": "1.0",
        "semantic_status": SEMANTIC_STATUS[stage],
        "content_sha256": digest,
        "size_bytes": len(payload),
        "storage_scope": "INTEGRA_STORE",
        "relative_path": relative,
        "origin": component,
        "provenance": provenance,
    }
    validate_artifact_reference(reference)
    progress = message("PROGRESS", job["correlation_id"], "progress", {"job_id": job["payload"]["job_id"], "sequence": 0, "fraction": 1.0, "stage": stage})
    result = message("RESULT", job["correlation_id"], "result", {"job_id": job["payload"]["job_id"], "operation_id": job["payload"]["operation_id"], "status": "SUCCEEDED", "outputs": [reference]})
    for outgoing in (progress, result):
        validate_message(outgoing)
        sys.stdout.buffer.write(canonical_json(outgoing) + b"\n")
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"R3_WORKER_ERROR {error}", file=sys.stderr)
        raise SystemExit(1)
