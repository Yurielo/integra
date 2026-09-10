"""Dependency-free validators for the R6 pinned real-media stage contracts."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import PurePosixPath
from typing import Any


class RealStageContractError(ValueError):
    """Raised when a real-stage payload does not satisfy its exact contract."""


def _exact(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise RealStageContractError(f"{label} fields are invalid")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RealStageContractError(f"{label} must be non-empty text")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RealStageContractError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: Any, label: str, *, minimum: float = 0.0) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < minimum
    ):
        raise RealStageContractError(f"{label} must be a number >= {minimum}")
    return float(value)


def _sha256(value: Any, label: str) -> str:
    value = _text(value, label)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RealStageContractError(f"{label} must be a lowercase SHA-256")
    return value


def _string_list(value: Any, label: str, *, non_empty: bool = False) -> list[str]:
    if (
        not isinstance(value, list)
        or (non_empty and not value)
        or not all(isinstance(item, str) and item for item in value)
        or len(value) != len(set(value))
    ):
        raise RealStageContractError(f"{label} must be a unique string list")
    return value


def _time_interval(value: Any, label: str) -> tuple[float, float]:
    value = _exact(value, {"type", "start_seconds", "end_seconds"}, label)
    if value["type"] != "time_interval":
        raise RealStageContractError(f"{label} must use time_interval")
    start = _number(value["start_seconds"], f"{label}.start_seconds")
    end = _number(value["end_seconds"], f"{label}.end_seconds")
    if end <= start:
        raise RealStageContractError(f"{label} must have positive duration")
    return start, end


def _validate_transcript(result: Any, stage_data: Any) -> None:
    result = _exact(
        result,
        {"assurance", "language", "model_sha256", "text_sha256", "word_count"},
        "transcript result",
    )
    if result["assurance"] != "MACHINE_UNVERIFIED" or result["language"] != "ru":
        raise RealStageContractError("transcript assurance or language is invalid")
    _sha256(result["model_sha256"], "transcript model_sha256")
    text_hash = _sha256(result["text_sha256"], "transcript text_sha256")
    word_count = _integer(result["word_count"], "transcript word_count", minimum=1)
    stage_data = _exact(
        stage_data,
        {
            "review_checkpoint",
            "srt_text",
            "transcript_text",
            "whisper_document",
            "word_intervals",
            "omitted_zero_duration_tokens",
        },
        "transcript stage_data",
    )
    if stage_data["review_checkpoint"] != "SOURCE_TRANSCRIPT":
        raise RealStageContractError("transcript review checkpoint is invalid")
    _text(stage_data["srt_text"], "transcript srt_text")
    transcript_text = _text(stage_data["transcript_text"], "transcript text")
    if hashlib.sha256(transcript_text.encode("utf-8")).hexdigest() != text_hash:
        raise RealStageContractError("transcript text hash differs")
    whisper = stage_data["whisper_document"]
    if (
        not isinstance(whisper, dict)
        or not isinstance(whisper.get("transcription"), list)
        or not whisper["transcription"]
        or not isinstance(whisper.get("result"), dict)
        or whisper["result"].get("language") != "ru"
    ):
        raise RealStageContractError("Whisper document is invalid")
    words = stage_data["word_intervals"]
    if not isinstance(words, list) or len(words) != word_count:
        raise RealStageContractError("transcript word interval count differs")
    previous_start = -1.0
    for index, word in enumerate(words):
        word = _exact(word, {"word", "start", "end", "score"}, f"word {index}")
        _text(word["word"], f"word {index}.word")
        start = _number(word["start"], f"word {index}.start")
        end = _number(word["end"], f"word {index}.end")
        score = _number(word["score"], f"word {index}.score")
        if end <= start or start < previous_start or score > 1:
            raise RealStageContractError(f"word {index} interval or score is invalid")
        previous_start = start
    omitted = stage_data["omitted_zero_duration_tokens"]
    if not isinstance(omitted, list):
        raise RealStageContractError("omitted token list is invalid")
    for index, token in enumerate(omitted):
        token = _exact(
            token,
            {"word", "start", "end", "score", "reason", "segment_index"},
            f"omitted token {index}",
        )
        _text(token["word"], f"omitted token {index}.word")
        start = _number(token["start"], f"omitted token {index}.start")
        end = _number(token["end"], f"omitted token {index}.end")
        score = _number(token["score"], f"omitted token {index}.score")
        _integer(token["segment_index"], f"omitted token {index}.segment_index")
        if token["reason"] != "WHISPER_ZERO_DURATION_TOKEN" or end != start or score > 1:
            raise RealStageContractError(f"omitted token {index} is invalid")


def _validate_topics(result: Any, stage_data: Any) -> None:
    result = _exact(
        result,
        {"model_digest", "model_weights_sha256", "topic_count"},
        "topics result",
    )
    _sha256(result["model_digest"], "topics model digest")
    _sha256(result["model_weights_sha256"], "topics model weights")
    topic_count = _integer(result["topic_count"], "topic_count", minimum=1)
    stage_data = _exact(stage_data, {"topics_document"}, "topics stage_data")
    document = _exact(
        stage_data["topics_document"],
        {"component", "component_entrypoint", "model", "schema_version", "topics", "windows"},
        "topics document",
    )
    if document["component"] != "seminartext" or document["schema_version"] != "1.0":
        raise RealStageContractError("topics document identity is invalid")
    _text(document["component_entrypoint"], "topics component entrypoint")
    _text(document["model"], "topics model")
    topics = document["topics"]
    if not isinstance(topics, list) or len(topics) != topic_count:
        raise RealStageContractError("topics document count differs")
    topic_fields = {
        "end", "end_seconds", "evidence_end_id", "evidence_start_id", "number",
        "qa_attempt", "qa_status", "semantic_status", "start", "start_seconds",
        "start_segment_id", "summary", "title",
    }
    for index, topic in enumerate(topics):
        topic = _exact(topic, topic_fields, f"topic {index}")
        for field in ("start", "end", "qa_attempt", "qa_status", "summary", "title"):
            _text(topic[field], f"topic {index}.{field}")
        start = _number(topic["start_seconds"], f"topic {index}.start_seconds")
        end = _number(topic["end_seconds"], f"topic {index}.end_seconds")
        for field in ("evidence_end_id", "evidence_start_id", "number", "start_segment_id"):
            _integer(topic[field], f"topic {index}.{field}", minimum=1)
        if end <= start or topic["semantic_status"] != "REVIEW_REQUIRED":
            raise RealStageContractError(f"topic {index} interval or authority is invalid")
    windows = document["windows"]
    if not isinstance(windows, list) or not windows:
        raise RealStageContractError("topic windows are invalid")
    row_fields = {
        "evidence_end_id", "evidence_start_id", "qa_attempt", "qa_status",
        "semantic_status", "start_id", "summary", "title",
    }
    for index, window in enumerate(windows):
        window = _exact(window, {"boundaries", "rows", "window"}, f"window {index}")
        _integer(window["window"], f"window {index}.window", minimum=1)
        if not isinstance(window["boundaries"], list) or not all(
            isinstance(item, int) and not isinstance(item, bool) and item >= 1
            for item in window["boundaries"]
        ):
            raise RealStageContractError(f"window {index} boundaries are invalid")
        if not isinstance(window["rows"], list) or not window["rows"]:
            raise RealStageContractError(f"window {index} rows are invalid")
        for row_index, row in enumerate(window["rows"]):
            row = _exact(row, row_fields, f"window {index} row {row_index}")
            if row["semantic_status"] != "REVIEW_REQUIRED":
                raise RealStageContractError("topic window row escaped review authority")
            for field in ("qa_attempt", "qa_status", "summary", "title"):
                _text(row[field], f"window {index} row {row_index}.{field}")
            for field in ("evidence_end_id", "evidence_start_id", "start_id"):
                _integer(row[field], f"window {index} row {row_index}.{field}", minimum=1)


def _validate_review(result: Any, stage_data: Any) -> None:
    result = _exact(
        result,
        {"human_decision_required", "technical_status", "unreviewed"},
        "review result",
    )
    unreviewed = _integer(result["unreviewed"], "review unreviewed", minimum=1)
    if result["human_decision_required"] is not True or result["technical_status"] != "REVIEW_REQUIRED":
        raise RealStageContractError("review result authority is invalid")
    stage_data = _exact(
        stage_data,
        {"alignment_result", "canonical_bundle", "draft_input_document", "review_package"},
        "review stage_data",
    )
    alignment = _exact(
        stage_data["alignment_result"],
        {"alignment_run_id", "bundle", "status", "unaligned_words"},
        "alignment result",
    )
    _text(alignment["alignment_run_id"], "alignment run ID")
    if alignment["bundle"] != "evidence/canonical_bundle.json" or alignment["status"] != "review_required":
        raise RealStageContractError("alignment result identity is invalid")
    if not isinstance(alignment["unaligned_words"], list) or not all(
        isinstance(item, int) and not isinstance(item, bool) and item >= 0
        for item in alignment["unaligned_words"]
    ):
        raise RealStageContractError("alignment unaligned_words is invalid")
    bundle = _exact(
        stage_data["canonical_bundle"],
        {
            "alignment_runs", "artifact_id", "artifact_type", "benchmark_segments",
            "cues", "evidence_refs", "project", "schema_version", "sources",
            "topics", "transcript_revisions", "words",
        },
        "canonical bundle",
    )
    if bundle["schema_version"] != "1.0.0" or bundle["artifact_type"] != "seminartext.canonical_evidence":
        raise RealStageContractError("canonical bundle identity is invalid")
    _text(bundle["artifact_id"], "canonical bundle artifact_id")
    project = _exact(bundle["project"], {"id", "lifecycle_status", "title"}, "canonical project")
    _text(project["id"], "canonical project ID")
    _text(project["title"], "canonical project title")
    if project["lifecycle_status"] != "active":
        raise RealStageContractError("canonical project lifecycle is invalid")
    if not isinstance(bundle["sources"], list) or not bundle["sources"]:
        raise RealStageContractError("canonical sources are invalid")
    source_ids: set[str] = set()
    source_by_id: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(bundle["sources"]):
        source = _exact(
            source,
            {"content_sha256", "duration_seconds", "id", "kind", "lifecycle_status", "project_id", "sequence", "title"},
            f"canonical source {index}",
        )
        source_id = _text(source["id"], f"canonical source {index}.id")
        source_ids.add(source_id)
        source_by_id[source_id] = source
        _sha256(source["content_sha256"], f"canonical source {index}.content_sha256")
        if source["project_id"] != project["id"] or source["kind"] != "video" or source["lifecycle_status"] != "active":
            raise RealStageContractError(f"canonical source {index} identity is invalid")
        _number(source["duration_seconds"], f"canonical source {index}.duration_seconds")
        _integer(source["sequence"], f"canonical source {index}.sequence")
        _text(source["title"], f"canonical source {index}.title")
    if len(source_ids) != len(bundle["sources"]):
        raise RealStageContractError("canonical source IDs are not unique")
    revisions = bundle["transcript_revisions"]
    if not isinstance(revisions, list) or not revisions:
        raise RealStageContractError("canonical transcript revisions are invalid")
    revision_ids: set[str] = set()
    revision_by_id: dict[str, dict[str, Any]] = {}
    for index, revision in enumerate(revisions):
        revision = _exact(
            revision,
            {"authority", "canonical_text", "id", "lifecycle_status", "parent_revision_id", "revision_kind", "revision_number", "source_id", "text_sha256", "transcript_provenance"},
            f"canonical revision {index}",
        )
        revision_id = _text(revision["id"], f"canonical revision {index}.id")
        revision_ids.add(revision_id)
        revision_by_id[revision_id] = revision
        canonical_text = _text(revision["canonical_text"], f"canonical revision {index}.canonical_text")
        if hashlib.sha256(canonical_text.encode("utf-8")).hexdigest() != _sha256(revision["text_sha256"], f"canonical revision {index}.text_sha256"):
            raise RealStageContractError("canonical transcript hash differs")
        if revision["source_id"] not in source_ids or revision["authority"] != "candidate" or revision["lifecycle_status"] != "active" or revision["revision_kind"] != "asr":
            raise RealStageContractError(f"canonical revision {index} identity is invalid")
        _integer(revision["revision_number"], f"canonical revision {index}.revision_number", minimum=1)
        provenance = _exact(
            revision["transcript_provenance"],
            {"method", "origin", "reviewer", "verification_ranges", "verification_state"},
            f"canonical revision {index}.provenance",
        )
        if provenance["origin"] != "machine_generated" or provenance["verification_state"] != "machine_unverified" or provenance["reviewer"] is not None or provenance["verification_ranges"] != []:
            raise RealStageContractError("canonical transcript provenance is invalid")
        _text(provenance["method"], "canonical transcript method")
    if len(revision_ids) != len(revisions):
        raise RealStageContractError("canonical transcript revision IDs are not unique")
    words = bundle["words"]
    if not isinstance(words, list) or not words:
        raise RealStageContractError("canonical words are invalid")
    word_fields = {
        "alignment_status", "char_end", "char_start", "confidence", "end_seconds",
        "id", "lifecycle_status", "normalized_text", "qa_flags", "sequence",
        "source_cue_ids", "source_id", "speaker_id", "start_seconds", "text",
        "timing_provenance", "transcript_revision_id",
    }
    word_by_id: dict[str, dict[str, Any]] = {}
    for index, word in enumerate(words):
        word = _exact(word, word_fields, f"canonical word {index}")
        if word["sequence"] != index or word["source_id"] not in source_ids or word["transcript_revision_id"] not in revision_ids or word["alignment_status"] not in {"aligned", "unaligned"} or word["lifecycle_status"] != "active":
            raise RealStageContractError(f"canonical word {index} identity is invalid")
        word_id = _text(word["id"], f"canonical word {index}.id")
        if word_id in word_by_id:
            raise RealStageContractError("canonical word IDs are not unique")
        word_by_id[word_id] = word
        _text(word["text"], f"canonical word {index}.text")
        char_start = _integer(word["char_start"], f"canonical word {index}.char_start")
        char_end = _integer(word["char_end"], f"canonical word {index}.char_end")
        if char_end < char_start:
            raise RealStageContractError(f"canonical word {index} character range is invalid")
        if word["normalized_text"] is not None and not isinstance(word["normalized_text"], str):
            raise RealStageContractError(f"canonical word {index} normalized_text is invalid")
        if word["speaker_id"] is not None and not isinstance(word["speaker_id"], str):
            raise RealStageContractError(f"canonical word {index} speaker_id is invalid")
        if not isinstance(word["qa_flags"], list) or not all(
            isinstance(flag, str) and flag for flag in word["qa_flags"]
        ):
            raise RealStageContractError(f"canonical word {index} QA flags are invalid")
        _string_list(word["source_cue_ids"], f"canonical word {index}.source_cue_ids", non_empty=True)
        timing = _exact(word["timing_provenance"], {"alignment_run_id", "kind", "method"}, f"canonical word {index}.timing")
        if word["alignment_status"] == "aligned":
            start = _number(word["start_seconds"], f"canonical word {index}.start_seconds")
            end = _number(word["end_seconds"], f"canonical word {index}.end_seconds")
            confidence = _number(word["confidence"], f"canonical word {index}.confidence")
            if end <= start or confidence > 1 or timing["kind"] != "forced_alignment":
                raise RealStageContractError(f"canonical word {index} alignment is invalid")
            _text(timing["alignment_run_id"], "canonical alignment run ID")
            _text(timing["method"], "canonical timing method")
        elif (
            word["start_seconds"] is not None
            or word["end_seconds"] is not None
            or word["confidence"] is not None
            or timing != {"alignment_run_id": None, "kind": "unavailable", "method": None}
            or "unaligned_review_required" not in word["qa_flags"]
        ):
            raise RealStageContractError(f"canonical word {index} unaligned state is invalid")
    for collection in ("benchmark_segments", "cues", "alignment_runs"):
        if not isinstance(bundle[collection], list) or not bundle[collection] or not all(isinstance(item, dict) and item for item in bundle[collection]):
            raise RealStageContractError(f"canonical {collection} are invalid")
    for index, run in enumerate(bundle["alignment_runs"]):
        run = _exact(
            run,
            {
                "aligner", "aligner_version", "config_sha256", "id", "model",
                "model_revision", "model_sha256", "source_content_sha256",
                "source_id", "status", "transcript_revision_id",
                "transcript_text_sha256",
            },
            f"canonical alignment run {index}",
        )
        for field in (
            "aligner", "aligner_version", "id", "model", "model_revision",
            "source_id", "transcript_revision_id",
        ):
            _text(run[field], f"canonical alignment run {index}.{field}")
        for field in (
            "config_sha256", "model_sha256", "source_content_sha256",
            "transcript_text_sha256",
        ):
            _sha256(run[field], f"canonical alignment run {index}.{field}")
        source = source_by_id.get(run["source_id"])
        revision = revision_by_id.get(run["transcript_revision_id"])
        if (
            run["status"] != "valid"
            or source is None
            or revision is None
            or revision["source_id"] != run["source_id"]
            or run["source_content_sha256"] != source["content_sha256"]
            or run["transcript_text_sha256"] != revision["text_sha256"]
        ):
            raise RealStageContractError("canonical alignment run is not valid")
    for index, segment in enumerate(bundle["benchmark_segments"]):
        segment = _exact(
            segment,
            {"id", "lifecycle_status", "sequence", "transcript_revision_id", "word_count", "word_end_id", "word_start_id"},
            f"canonical benchmark segment {index}",
        )
        for field in ("id", "transcript_revision_id", "word_end_id", "word_start_id"):
            _text(segment[field], f"canonical benchmark segment {index}.{field}")
        _integer(segment["sequence"], f"canonical benchmark segment {index}.sequence")
        _integer(segment["word_count"], f"canonical benchmark segment {index}.word_count", minimum=1)
        start_word = word_by_id.get(segment["word_start_id"])
        end_word = word_by_id.get(segment["word_end_id"])
        if (
            segment["lifecycle_status"] != "active"
            or start_word is None
            or end_word is None
            or start_word["transcript_revision_id"] != segment["transcript_revision_id"]
            or end_word["transcript_revision_id"] != segment["transcript_revision_id"]
            or start_word["sequence"] > end_word["sequence"]
            or segment["word_count"] != end_word["sequence"] - start_word["sequence"] + 1
        ):
            raise RealStageContractError("canonical benchmark segment lifecycle is invalid")
    for index, cue in enumerate(bundle["cues"]):
        cue = _exact(
            cue,
            {"char_end", "char_start", "id", "lifecycle_status", "sequence", "source_locator", "text", "transcript_revision_id"},
            f"canonical cue {index}",
        )
        start = _integer(cue["char_start"], f"canonical cue {index}.char_start")
        end = _integer(cue["char_end"], f"canonical cue {index}.char_end")
        if end < start or cue["lifecycle_status"] != "active":
            raise RealStageContractError(f"canonical cue {index} is invalid")
        _integer(cue["sequence"], f"canonical cue {index}.sequence")
        for field in ("id", "text", "transcript_revision_id"):
            _text(cue[field], f"canonical cue {index}.{field}")
        _time_interval(cue["source_locator"], f"canonical cue {index}.locator")
    if not isinstance(bundle["topics"], list) or not isinstance(bundle["evidence_refs"], list):
        raise RealStageContractError("canonical optional collections are invalid")
    package = _exact(
        stage_data["review_package"],
        {"artifact_id", "artifact_type", "canonical_evidence", "draft_input", "evidence", "project", "review_policy", "schema_version", "seminar", "topics"},
        "review package",
    )
    if package["artifact_type"] != "seminartext.topic_review_package" or package["schema_version"] != "1.0.0":
        raise RealStageContractError("review package identity is invalid")
    for field in ("canonical_evidence", "draft_input"):
        binding = _exact(
            package[field], {"artifact_id", "sha256"}, f"review package {field}"
        )
        _text(binding["artifact_id"], f"review package {field}.artifact_id")
        _sha256(binding["sha256"], f"review package {field}.sha256")
    canonical_binding = package["canonical_evidence"]
    expected_bundle_bytes = (
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if (
        canonical_binding["artifact_id"] != bundle["artifact_id"]
        or canonical_binding["sha256"] != hashlib.sha256(expected_bundle_bytes).hexdigest()
    ):
        raise RealStageContractError("review package canonical evidence binding differs")
    draft_input = stage_data["draft_input_document"]
    if not isinstance(draft_input, dict) or not draft_input:
        raise RealStageContractError("review draft input is invalid")
    draft_binding = package["draft_input"]
    expected_draft_bytes = (
        json.dumps(draft_input, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if (
        draft_binding["artifact_id"] != draft_input.get("artifact_id")
        or draft_binding["sha256"] != hashlib.sha256(expected_draft_bytes).hexdigest()
    ):
        raise RealStageContractError("review package draft input binding differs")
    package_project = _exact(package["project"], {"id", "title"}, "review project")
    package_seminar = _exact(package["seminar"], {"id", "title"}, "review seminar")
    for label, record in (("review project", package_project), ("review seminar", package_seminar)):
        _text(record["id"], f"{label}.id")
        _text(record["title"], f"{label}.title")
    if package_project["id"] != project["id"]:
        raise RealStageContractError("review project differs from canonical project")
    policy = _exact(
        package["review_policy"],
        {"authoring_gate", "automatic_acceptance", "machine_assisted_default", "review_gate"},
        "review policy",
    )
    if policy != {
        "authoring_gate": "DOMAIN_AUTHORING",
        "automatic_acceptance": False,
        "machine_assisted_default": "REVIEW_REQUIRED",
        "review_gate": "DOMAIN_REVIEW",
    }:
        raise RealStageContractError("review policy weakens semantic authority")
    evidence = package["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise RealStageContractError("review evidence is invalid")
    evidence_ids: set[str] = set()
    evidence_fields = {
        "claim", "id", "locator", "quote", "source_id", "transcript_provenance",
        "transcript_revision_id", "word_end_id", "word_end_sequence",
        "word_start_id", "word_start_sequence",
    }
    for index, item in enumerate(evidence):
        item = _exact(item, evidence_fields, f"review evidence {index}")
        evidence_ids.add(_text(item["id"], f"review evidence {index}.id"))
        for field in ("claim", "quote", "source_id", "transcript_revision_id", "word_end_id", "word_start_id"):
            _text(item[field], f"review evidence {index}.{field}")
        locator = _time_interval(item["locator"], f"review evidence {index}.locator")
        for field in ("word_end_sequence", "word_start_sequence"):
            _integer(item[field], f"review evidence {index}.{field}")
        _validate_machine_provenance(
            item["transcript_provenance"], f"review evidence {index}.provenance"
        )
        if item["source_id"] not in source_ids or item["transcript_revision_id"] not in revision_ids:
            raise RealStageContractError(f"review evidence {index} source lineage is unknown")
        start_word = word_by_id.get(item["word_start_id"])
        end_word = word_by_id.get(item["word_end_id"])
        if (
            start_word is None
            or end_word is None
            or start_word["sequence"] != item["word_start_sequence"]
            or end_word["sequence"] != item["word_end_sequence"]
            or start_word["sequence"] > end_word["sequence"]
            or start_word["start_seconds"] is None
            or end_word["end_seconds"] is None
            or locator != (float(start_word["start_seconds"]), float(end_word["end_seconds"]))
        ):
            raise RealStageContractError(f"review evidence {index} word lineage differs")
    topics = package["topics"]
    if not isinstance(topics, list) or len(topics) != unreviewed:
        raise RealStageContractError("review package topic count differs")
    review_topic_fields = {
        "evidence_refs", "evidence_sha256", "generator", "id", "lifecycle_status",
        "locator", "proposed_summary", "proposed_title", "quote", "review_history",
        "semantic_origin", "seminar_id", "sequence", "source_id", "topic_set_id",
        "topic_sha256", "transcript_provenance", "transcript_revision_id",
        "word_end_id", "word_end_sequence", "word_start_id", "word_start_sequence",
    }
    for index, topic in enumerate(topics):
        topic = _exact(topic, review_topic_fields, f"review topic {index}")
        if topic["lifecycle_status"] != "REVIEW_REQUIRED" or topic["semantic_origin"] != "machine_assisted" or topic["review_history"] != []:
            raise RealStageContractError(f"review topic {index} authority is invalid")
        locator = _time_interval(topic["locator"], f"review topic {index}.locator")
        for field in ("id", "proposed_summary", "proposed_title", "quote", "seminar_id", "source_id", "topic_set_id", "transcript_revision_id", "word_end_id", "word_start_id"):
            _text(topic[field], f"review topic {index}.{field}")
        for field in ("evidence_sha256", "topic_sha256"):
            _sha256(topic[field], f"review topic {index}.{field}")
        _string_list(topic["evidence_refs"], f"review topic {index}.evidence_refs", non_empty=True)
        if not set(topic["evidence_refs"]).issubset(evidence_ids):
            raise RealStageContractError(f"review topic {index} has unknown evidence")
        generator = _exact(
            topic["generator"], {"configuration_sha256", "id", "version"},
            f"review topic {index}.generator",
        )
        _sha256(generator["configuration_sha256"], f"review topic {index}.generator hash")
        _text(generator["id"], f"review topic {index}.generator ID")
        _text(generator["version"], f"review topic {index}.generator version")
        _validate_machine_provenance(
            topic["transcript_provenance"], f"review topic {index}.provenance"
        )
        for field in ("sequence", "word_end_sequence", "word_start_sequence"):
            _integer(topic[field], f"review topic {index}.{field}")
        start_word = word_by_id.get(topic["word_start_id"])
        end_word = word_by_id.get(topic["word_end_id"])
        if (
            topic["seminar_id"] != package_seminar["id"]
            or topic["source_id"] not in source_ids
            or topic["transcript_revision_id"] not in revision_ids
            or start_word is None
            or end_word is None
            or start_word["sequence"] != topic["word_start_sequence"]
            or end_word["sequence"] != topic["word_end_sequence"]
            or start_word["sequence"] > end_word["sequence"]
            or start_word["start_seconds"] is None
            or end_word["end_seconds"] is None
            or locator != (float(start_word["start_seconds"]), float(end_word["end_seconds"]))
        ):
            raise RealStageContractError(f"review topic {index} lineage differs")


def _validate_machine_provenance(value: Any, label: str) -> None:
    value = _exact(
        value,
        {"method", "origin", "reviewer", "verification_ranges", "verification_state"},
        label,
    )
    if (
        value["origin"] != "machine_generated"
        or value["verification_state"] != "machine_unverified"
        or value["reviewer"] is not None
        or value["verification_ranges"] != []
    ):
        raise RealStageContractError(f"{label} is not machine-unverified")
    _text(value["method"], f"{label}.method")


def _validate_knowledge(result: Any, stage_data: Any) -> None:
    result = _exact(result, {"lifecycle", "manifest_sha256"}, "knowledge result")
    if result["lifecycle"] != "PROVISIONAL":
        raise RealStageContractError("knowledge lifecycle is invalid")
    manifest_hash = _sha256(result["manifest_sha256"], "knowledge manifest SHA-256")
    stage_data = _exact(
        stage_data,
        {
            "canonical_evidence_document", "canonical_knowledge_document",
            "coverage_document", "export_files", "export_manifest",
            "export_manifest_text",
        },
        "knowledge stage_data",
    )
    manifest = _exact(
        stage_data["export_manifest"],
        {"artifact_type", "canonical_evidence_artifact_id", "canonical_evidence_sha256", "canonical_knowledge_artifact_id", "canonical_knowledge_sha256", "coverage", "files", "kind", "ownership_classes", "resolver_states", "schema_version"},
        "knowledge export manifest",
    )
    if manifest["artifact_type"] != "seminartext.managed_generated_export" or manifest["kind"] != "obsidian_derived_view" or manifest["schema_version"] != 1:
        raise RealStageContractError("knowledge export manifest identity is invalid")
    for field in ("canonical_evidence_artifact_id", "canonical_knowledge_artifact_id"):
        _text(manifest[field], f"knowledge {field}")
    for field in ("canonical_evidence_sha256", "canonical_knowledge_sha256"):
        _sha256(manifest[field], f"knowledge {field}")
    canonical_evidence = stage_data["canonical_evidence_document"]
    canonical_knowledge = stage_data["canonical_knowledge_document"]
    coverage_document = stage_data["coverage_document"]
    if not isinstance(canonical_evidence, dict) or not isinstance(canonical_knowledge, dict):
        raise RealStageContractError("knowledge canonical documents are invalid")
    for label, value, id_field, hash_field in (
        ("evidence", canonical_evidence, "canonical_evidence_artifact_id", "canonical_evidence_sha256"),
        ("knowledge", canonical_knowledge, "canonical_knowledge_artifact_id", "canonical_knowledge_sha256"),
    ):
        encoded = (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if value.get("artifact_id") != manifest[id_field] or hashlib.sha256(encoded).hexdigest() != manifest[hash_field]:
            raise RealStageContractError(f"knowledge canonical {label} binding differs")
    knowledge_evidence = canonical_knowledge.get("canonical_evidence")
    if not isinstance(knowledge_evidence, dict) or (
        knowledge_evidence.get("artifact_id") != canonical_evidence.get("artifact_id")
        or knowledge_evidence.get("sha256") != manifest["canonical_evidence_sha256"]
    ):
        raise RealStageContractError("canonical knowledge evidence pointer differs")
    if manifest["ownership_classes"] != ["MANAGED_GENERATED", "USER_OWNED"]:
        raise RealStageContractError("knowledge ownership classes are invalid")
    if not isinstance(manifest["resolver_states"], dict) or not manifest["resolver_states"] or not all(isinstance(key, str) and key and isinstance(value, str) and value for key, value in manifest["resolver_states"].items()):
        raise RealStageContractError("knowledge resolver states are invalid")
    files = manifest["files"]
    export_files = stage_data["export_files"]
    if not isinstance(files, dict) or not files or not isinstance(export_files, dict) or set(export_files) != set(files):
        raise RealStageContractError("knowledge export file inventory differs")
    for path, expected_hash in files.items():
        _text(path, "knowledge export path")
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts or path != parsed.as_posix():
            raise RealStageContractError(f"knowledge export path is unsafe: {path}")
        _sha256(expected_hash, f"knowledge file hash {path}")
        content = export_files[path]
        if not isinstance(content, str) or hashlib.sha256(content.encode("utf-8")).hexdigest() != expected_hash:
            raise RealStageContractError(f"knowledge export bytes differ: {path}")
    manifest_text = _text(
        stage_data["export_manifest_text"], "knowledge export_manifest_text"
    )
    try:
        decoded_manifest = json.loads(manifest_text)
    except (ValueError, TypeError) as error:
        raise RealStageContractError("knowledge export manifest text is invalid") from error
    if decoded_manifest != manifest or hashlib.sha256(manifest_text.encode("utf-8")).hexdigest() != manifest_hash:
        raise RealStageContractError("knowledge result manifest hash differs")
    coverage = manifest["coverage"]
    if not isinstance(coverage, dict) or coverage.get("full_seminar_coverage") is not True or not isinstance(coverage.get("sources"), list) or not coverage["sources"]:
        raise RealStageContractError("knowledge coverage is invalid")
    coverage = _exact(
        coverage,
        {"artifact_type", "full_seminar_coverage", "project_id", "schema_version", "sources"},
        "knowledge coverage",
    )
    if coverage["artifact_type"] != "seminartext.project_knowledge_coverage" or coverage["schema_version"] != 1:
        raise RealStageContractError("knowledge coverage identity is invalid")
    _text(coverage["project_id"], "knowledge coverage project_id")
    if coverage_document != coverage:
        raise RealStageContractError("knowledge coverage document differs from manifest")
    source_fields = {
        "evidence_ids", "reason", "source_id", "status", "topic_ids",
        "transcript_revision_ids", "word_count",
    }
    for index, source in enumerate(coverage["sources"]):
        source = _exact(source, source_fields, f"knowledge coverage source {index}")
        for field in ("evidence_ids", "topic_ids", "transcript_revision_ids"):
            _string_list(source[field], f"knowledge coverage source {index}.{field}", non_empty=True)
        _text(source["reason"], f"knowledge coverage source {index}.reason")
        _text(source["source_id"], f"knowledge coverage source {index}.source_id")
        _integer(source["word_count"], f"knowledge coverage source {index}.word_count", minimum=1)
        if source["status"] != "COVERED":
            raise RealStageContractError("knowledge coverage source is not COVERED")


def validate_real_stage_document(stage: str, document: Any) -> None:
    document = _exact(
        document,
        {"input_artifact_ids", "input_content_sha256", "result", "schema_version", "semantic_status", "stage", "stage_data"},
        f"{stage} document",
    )
    if document["schema_version"] != "1.0" or document["stage"] != stage:
        raise RealStageContractError(f"{stage} document identity is invalid")
    expected_status = {
        "transcript": "REVIEW_REQUIRED",
        "topics": "REVIEW_REQUIRED",
        "review": "REVIEW_REQUIRED",
        "knowledge": "PROVISIONAL",
    }.get(stage)
    if expected_status is None or document["semantic_status"] != expected_status:
        raise RealStageContractError(f"{stage} semantic status is invalid")
    _string_list(document["input_artifact_ids"], f"{stage} input IDs", non_empty=True)
    hashes = document["input_content_sha256"]
    if not isinstance(hashes, list) or not hashes or len(hashes) != len(document["input_artifact_ids"]):
        raise RealStageContractError(f"{stage} input hashes are invalid")
    for index, value in enumerate(hashes):
        _sha256(value, f"{stage} input hash {index}")
    validators = {
        "transcript": _validate_transcript,
        "topics": _validate_topics,
        "review": _validate_review,
        "knowledge": _validate_knowledge,
    }
    validators[stage](document["result"], document["stage_data"])


def validate_mp4_clip(payload: bytes) -> None:
    """Validate the bounded v1 media contract as a complete ISO-BMFF file."""

    if not isinstance(payload, bytes) or len(payload) < 24:
        raise RealStageContractError("media clip is too small for ISO-BMFF")
    offset = 0
    boxes: list[tuple[bytes, int, int]] = []
    while offset < len(payload):
        if len(payload) - offset < 8:
            raise RealStageContractError("media clip has a truncated box header")
        size = int.from_bytes(payload[offset : offset + 4], "big")
        kind = payload[offset + 4 : offset + 8]
        header = 8
        if size == 1:
            if len(payload) - offset < 16:
                raise RealStageContractError("media clip has a truncated extended box")
            size = int.from_bytes(payload[offset + 8 : offset + 16], "big")
            header = 16
        elif size == 0:
            size = len(payload) - offset
        if size < header or offset + size > len(payload):
            raise RealStageContractError("media clip box length is invalid")
        if any(byte < 0x20 or byte > 0x7E for byte in kind):
            raise RealStageContractError("media clip box type is invalid")
        boxes.append((kind, size, header))
        offset += size
    kinds = [kind for kind, _, _ in boxes]
    if (
        offset != len(payload)
        or kinds[:1] != [b"ftyp"]
        or b"moov" not in kinds
        or b"mdat" not in kinds
    ):
        raise RealStageContractError("media clip lacks required ftyp/moov/mdat boxes")
    ftyp = boxes[0]
    if ftyp[1] - ftyp[2] < 8:
        raise RealStageContractError("media clip ftyp box is incomplete")
    for required in (b"moov", b"mdat"):
        _, size, header = next(record for record in boxes if record[0] == required)
        if size <= header:
            raise RealStageContractError(f"media clip {required.decode()} box is empty")
