#!/usr/bin/env python3
"""Validate Canonical Evidence v1 shape and cross-record invariants.

The JSON Schema owns the record shapes. This dependency-free companion owns
constraints JSON Schema cannot express portably: references, ordered ranges,
revision/hash consistency, timing semantics, and deterministic array order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ID_RE = re.compile(r"^[a-z][a-z0-9._:-]{2,127}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
LIFECYCLES = {"draft", "active", "verified", "superseded", "invalidated", "archived"}
SOURCE_KINDS = {"video", "audio", "pdf", "pptx", "docx", "text", "image", "other"}
ARRAYS = (
    "sources",
    "transcript_revisions",
    "cues",
    "alignment_runs",
    "words",
    "benchmark_segments",
    "topics",
    "evidence_refs",
)
REQUIRED_TOP_LEVEL = {"schema_version", "artifact_type", "artifact_id", "project", *ARRAYS}


def _record_index(records: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        return {}
    return {
        record["id"]: record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }


def _require_fields(errors: list[str], path: str, value: Any, fields: set[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{path}: expected object")
        return False
    missing = sorted(fields - value.keys())
    if missing:
        errors.append(f"{path}: missing fields {missing}")
        return False
    return True


def _check_id(errors: list[str], path: str, value: Any) -> None:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        errors.append(f"{path}: invalid stable id")


def _check_hash(errors: list[str], path: str, value: Any) -> None:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        errors.append(f"{path}: expected lowercase SHA-256")


def _check_sequence(errors: list[str], path: str, records: list[dict[str, Any]]) -> None:
    actual = [record.get("sequence") for record in records]
    expected = list(range(len(records)))
    if actual != expected:
        errors.append(f"{path}: sequence must be contiguous {expected}, got {actual}")


def _check_locator(
    errors: list[str], path: str, locator: Any, source: dict[str, Any] | None
) -> None:
    if not isinstance(locator, dict):
        errors.append(f"{path}: expected locator object")
        return
    locator_type = locator.get("type")
    source_kind = source.get("kind") if source else None
    compatible = {
        "time_interval": {"video", "audio"},
        "pdf_page_range": {"pdf"},
        "pptx_slide_range": {"pptx"},
        "text_char_range": {"docx", "text"},
        "image_region": {"image"},
    }
    if locator_type not in compatible:
        errors.append(f"{path}.type: unsupported locator")
        return
    if source_kind not in compatible[locator_type]:
        errors.append(f"{path}: {locator_type} is incompatible with source kind {source_kind!r}")

    if locator_type == "time_interval":
        start, end = locator.get("start_seconds"), locator.get("end_seconds")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or start < 0 or end <= start:
            errors.append(f"{path}: invalid positive time interval")
        elif source and source.get("duration_seconds") is not None and end > source["duration_seconds"]:
            errors.append(f"{path}: interval exceeds source duration")
    elif locator_type == "pdf_page_range":
        start, end = locator.get("page_start"), locator.get("page_end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            errors.append(f"{path}: invalid PDF page range")
    elif locator_type == "pptx_slide_range":
        start, end = locator.get("slide_start"), locator.get("slide_end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            errors.append(f"{path}: invalid slide range")
    elif locator_type == "text_char_range":
        start, end = locator.get("char_start"), locator.get("char_end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            errors.append(f"{path}: invalid character range")
    elif locator_type == "image_region":
        values = [locator.get(key) for key in ("x", "y", "width", "height")]
        if (
            locator.get("coordinate_space") != "normalized_0_1"
            or not all(isinstance(value, (int, float)) for value in values)
            or values[0] < 0
            or values[1] < 0
            or values[2] <= 0
            or values[3] <= 0
            or values[0] + values[2] > 1
            or values[1] + values[3] > 1
        ):
            errors.append(f"{path}: invalid normalized image region")


def validate_bundle(bundle: Any) -> list[str]:
    """Return deterministic human-readable errors; an empty list means valid."""
    errors: list[str] = []
    if not _require_fields(errors, "$", bundle, REQUIRED_TOP_LEVEL):
        return errors
    if bundle.get("schema_version") != "1.0.0":
        errors.append("$.schema_version: expected 1.0.0")
    if bundle.get("artifact_type") != "seminartext.canonical_evidence":
        errors.append("$.artifact_type: unexpected artifact type")
    _check_id(errors, "$.artifact_id", bundle.get("artifact_id"))

    project = bundle.get("project")
    if _require_fields(errors, "$.project", project, {"id", "title", "lifecycle_status"}):
        _check_id(errors, "$.project.id", project["id"])
        if not isinstance(project["title"], str) or not project["title"]:
            errors.append("$.project.title: expected non-empty string")
        if project["lifecycle_status"] not in LIFECYCLES:
            errors.append("$.project.lifecycle_status: invalid lifecycle")

    arrays: dict[str, list[dict[str, Any]]] = {}
    for name in ARRAYS:
        value = bundle.get(name)
        if not isinstance(value, list):
            errors.append(f"$.{name}: expected array")
            arrays[name] = []
        else:
            arrays[name] = value

    required = {
        "sources": {"id", "project_id", "sequence", "kind", "title", "content_sha256", "duration_seconds", "lifecycle_status"},
        "transcript_revisions": {"id", "source_id", "revision_number", "revision_kind", "parent_revision_id", "canonical_text", "text_sha256", "authority", "lifecycle_status"},
        "cues": {"id", "transcript_revision_id", "sequence", "char_start", "char_end", "text", "source_locator", "lifecycle_status"},
        "alignment_runs": {"id", "source_id", "source_content_sha256", "transcript_revision_id", "transcript_text_sha256", "aligner", "aligner_version", "model", "model_revision", "model_sha256", "config_sha256", "status"},
        "words": {"id", "source_id", "transcript_revision_id", "sequence", "char_start", "char_end", "text", "normalized_text", "source_cue_ids", "start_seconds", "end_seconds", "alignment_status", "confidence", "speaker_id", "timing_provenance", "qa_flags", "lifecycle_status"},
        "benchmark_segments": {"id", "transcript_revision_id", "sequence", "word_start_id", "word_end_id", "word_count", "lifecycle_status"},
        "topics": {"id", "transcript_revision_id", "topic_set_id", "sequence", "title", "benchmark_segment_ids", "word_start_id", "word_end_id", "origin", "lifecycle_status"},
        "evidence_refs": {"id", "project_id", "source_id", "transcript_revision_id", "target", "locator", "lifecycle_status"},
    }
    for name, records in arrays.items():
        for index, record in enumerate(records):
            path = f"$.{name}[{index}]"
            if _require_fields(errors, path, record, required[name]):
                _check_id(errors, f"{path}.id", record["id"])
                if record.get("lifecycle_status") is not None and record["lifecycle_status"] not in LIFECYCLES:
                    errors.append(f"{path}.lifecycle_status: invalid lifecycle")

    all_ids: list[str] = []
    if isinstance(project, dict) and isinstance(project.get("id"), str):
        all_ids.append(project["id"])
    for records in arrays.values():
        all_ids.extend(record["id"] for record in records if isinstance(record, dict) and isinstance(record.get("id"), str))
    duplicates = sorted({item for item in all_ids if all_ids.count(item) > 1})
    if duplicates:
        errors.append(f"$: entity ids must be globally unique: {duplicates}")

    sources = _record_index(arrays["sources"])
    transcripts = _record_index(arrays["transcript_revisions"])
    cues = _record_index(arrays["cues"])
    runs = _record_index(arrays["alignment_runs"])
    words = _record_index(arrays["words"])
    segments = _record_index(arrays["benchmark_segments"])
    topics = _record_index(arrays["topics"])
    project_id = project.get("id") if isinstance(project, dict) else None

    for index, source in enumerate(arrays["sources"]):
        path = f"$.sources[{index}]"
        if not isinstance(source, dict):
            continue
        if source.get("project_id") != project_id:
            errors.append(f"{path}.project_id: orphan project reference")
        if source.get("kind") not in SOURCE_KINDS:
            errors.append(f"{path}.kind: unsupported source kind")
        _check_hash(errors, f"{path}.content_sha256", source.get("content_sha256"))
        duration = source.get("duration_seconds")
        if source.get("kind") in {"video", "audio"}:
            if not isinstance(duration, (int, float)) or duration <= 0:
                errors.append(f"{path}.duration_seconds: timed source requires positive duration")
        elif duration is not None:
            errors.append(f"{path}.duration_seconds: non-timed source must use null")
    _check_sequence(errors, "$.sources", arrays["sources"])

    revisions_by_source: dict[str, list[dict[str, Any]]] = {}
    for index, transcript in enumerate(arrays["transcript_revisions"]):
        path = f"$.transcript_revisions[{index}]"
        if not isinstance(transcript, dict):
            continue
        source_id = transcript.get("source_id")
        if source_id not in sources:
            errors.append(f"{path}.source_id: orphan source reference")
        revisions_by_source.setdefault(source_id, []).append(transcript)
        text = transcript.get("canonical_text")
        expected_hash = hashlib.sha256(text.encode("utf-8")).hexdigest() if isinstance(text, str) else None
        _check_hash(errors, f"{path}.text_sha256", transcript.get("text_sha256"))
        if expected_hash is not None and transcript.get("text_sha256") != expected_hash:
            errors.append(f"{path}.text_sha256: does not match canonical_text")
        parent_id = transcript.get("parent_revision_id")
        if parent_id is not None:
            parent = transcripts.get(parent_id)
            if parent is None or parent.get("source_id") != source_id or parent.get("revision_number", 0) >= transcript.get("revision_number", 0):
                errors.append(f"{path}.parent_revision_id: invalid revision parent")
        if transcript.get("revision_kind") not in {"asr", "verified", "corrected"}:
            errors.append(f"{path}.revision_kind: invalid revision kind")
        if transcript.get("authority") not in {"candidate", "authoritative", "superseded"}:
            errors.append(f"{path}.authority: invalid authority")
        provenance = transcript.get("transcript_provenance")
        if provenance is not None:
            if not isinstance(provenance, dict):
                errors.append(f"{path}.transcript_provenance: expected object")
                continue
            required_provenance = {"origin", "method", "verification_state", "verification_ranges", "reviewer"}
            missing = sorted(required_provenance - provenance.keys())
            if missing:
                errors.append(f"{path}.transcript_provenance: missing fields {missing}")
                continue
            origin = provenance.get("origin")
            state = provenance.get("verification_state")
            if origin not in {"machine_generated", "human_verified", "human_corrected"}:
                errors.append(f"{path}.transcript_provenance.origin: invalid origin")
            if not isinstance(provenance.get("method"), str) or not provenance["method"]:
                errors.append(f"{path}.transcript_provenance.method: expected non-empty string")
            if state not in {"machine_unverified", "selectively_verified", "fully_human_verified"}:
                errors.append(f"{path}.transcript_provenance.verification_state: invalid state")
            ranges = provenance.get("verification_ranges")
            if not isinstance(ranges, list):
                errors.append(f"{path}.transcript_provenance.verification_ranges: expected array")
                ranges = []
            previous_end = -1
            for number, item in enumerate(ranges):
                if not isinstance(item, dict) or not isinstance(item.get("char_start"), int) or not isinstance(item.get("char_end"), int):
                    errors.append(f"{path}.transcript_provenance.verification_ranges[{number}]: invalid range")
                    continue
                start, end = item["char_start"], item["char_end"]
                if start < 0 or end <= start or end > len(text):
                    errors.append(f"{path}.transcript_provenance.verification_ranges[{number}]: out of bounds")
                if start < previous_end:
                    errors.append(f"{path}.transcript_provenance.verification_ranges: must be sorted and non-overlapping")
                previous_end = end
            reviewer = provenance.get("reviewer")
            if reviewer is not None and (not isinstance(reviewer, str) or not reviewer):
                errors.append(f"{path}.transcript_provenance.reviewer: expected non-empty string or null")
            if state == "machine_unverified" and (origin != "machine_generated" or ranges or reviewer is not None):
                errors.append(f"{path}.transcript_provenance: machine_unverified requires machine origin, no ranges, and no reviewer")
            if state == "selectively_verified" and (not ranges or reviewer is None or origin not in {"machine_generated", "human_corrected"}):
                errors.append(f"{path}.transcript_provenance: selectively_verified requires ranges, reviewer, and machine/corrected origin")
            if state == "fully_human_verified":
                covered = len(ranges) == 1 and ranges[0].get("char_start") == 0 and ranges[0].get("char_end") == len(text)
                if origin != "human_verified" or transcript.get("authority") != "authoritative" or transcript.get("lifecycle_status") != "verified" or reviewer is None or not covered:
                    errors.append(f"{path}.transcript_provenance: fully_human_verified requires authoritative full-range human verification")

    for source_id, revisions in revisions_by_source.items():
        numbers = [item.get("revision_number") for item in revisions]
        if numbers != list(range(1, len(revisions) + 1)):
            errors.append(f"$.transcript_revisions: revisions for {source_id} must be ordered and contiguous")
        authoritative = [item for item in revisions if item.get("authority") == "authoritative"]
        if len(authoritative) > 1:
            errors.append(f"$.transcript_revisions: multiple authoritative revisions for {source_id}")

    for index, cue in enumerate(arrays["cues"]):
        path = f"$.cues[{index}]"
        if not isinstance(cue, dict):
            continue
        transcript = transcripts.get(cue.get("transcript_revision_id"))
        if transcript is None:
            errors.append(f"{path}.transcript_revision_id: orphan transcript reference")
            continue
        start, end = cue.get("char_start"), cue.get("char_end")
        text = transcript.get("canonical_text", "")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start or end > len(text):
            errors.append(f"{path}: invalid transcript character span")
        elif cue.get("text") != text[start:end]:
            errors.append(f"{path}.text: does not equal canonical transcript span")
        source = sources.get(transcript.get("source_id"))
        if cue.get("source_locator") is not None:
            _check_locator(errors, f"{path}.source_locator", cue["source_locator"], source)

    for index, run in enumerate(arrays["alignment_runs"]):
        path = f"$.alignment_runs[{index}]"
        if not isinstance(run, dict):
            continue
        source = sources.get(run.get("source_id"))
        transcript = transcripts.get(run.get("transcript_revision_id"))
        if source is None or transcript is None or transcript.get("source_id") != run.get("source_id"):
            errors.append(f"{path}: orphan or cross-source alignment reference")
        else:
            if run.get("source_content_sha256") != source.get("content_sha256"):
                errors.append(f"{path}.source_content_sha256: stale source content")
            if run.get("transcript_text_sha256") != transcript.get("text_sha256"):
                errors.append(f"{path}.transcript_text_sha256: stale transcript text")
            if transcript.get("authority") == "superseded" and run.get("status") == "valid":
                errors.append(f"{path}.status: alignment of superseded text must not remain valid")
        for field in ("source_content_sha256", "transcript_text_sha256", "model_sha256", "config_sha256"):
            _check_hash(errors, f"{path}.{field}", run.get(field))
        if run.get("status") not in {"valid", "superseded", "stale"}:
            errors.append(f"{path}.status: invalid alignment status")

    words_by_transcript: dict[str, list[dict[str, Any]]] = {}
    for index, word in enumerate(arrays["words"]):
        path = f"$.words[{index}]"
        if not isinstance(word, dict):
            continue
        transcript = transcripts.get(word.get("transcript_revision_id"))
        source = sources.get(word.get("source_id"))
        if transcript is None or source is None or transcript.get("source_id") != word.get("source_id"):
            errors.append(f"{path}: orphan or cross-source word reference")
            continue
        words_by_transcript.setdefault(transcript["id"], []).append(word)
        start_char, end_char = word.get("char_start"), word.get("char_end")
        text = transcript.get("canonical_text", "")
        if not isinstance(start_char, int) or not isinstance(end_char, int) or start_char < 0 or end_char <= start_char or end_char > len(text):
            errors.append(f"{path}: invalid transcript character span")
        elif word.get("text") != text[start_char:end_char]:
            errors.append(f"{path}.text: does not equal canonical transcript span")
        cue_ids = word.get("source_cue_ids")
        if not isinstance(cue_ids, list) or not cue_ids:
            errors.append(f"{path}.source_cue_ids: expected non-empty unique list")
        else:
            if len(cue_ids) != len(set(cue_ids)):
                errors.append(f"{path}.source_cue_ids: duplicate cue reference")
            for cue_id in cue_ids:
                cue = cues.get(cue_id)
                if cue is None or cue.get("transcript_revision_id") != transcript["id"]:
                    errors.append(f"{path}.source_cue_ids: orphan or cross-revision cue {cue_id!r}")
        timing = word.get("timing_provenance")
        if not isinstance(timing, dict) or not {"kind", "alignment_run_id", "method"} <= timing.keys():
            errors.append(f"{path}.timing_provenance: incomplete timing provenance")
            continue
        status = word.get("alignment_status")
        start, end = word.get("start_seconds"), word.get("end_seconds")
        kind, run_id, method = timing.get("kind"), timing.get("alignment_run_id"), timing.get("method")
        if status == "unaligned":
            if start is not None or end is not None or kind != "unavailable" or run_id is not None:
                errors.append(f"{path}: unaligned word must have null timing and unavailable provenance")
        else:
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or start < 0 or end <= start:
                errors.append(f"{path}: timed word requires a positive interval")
            elif source.get("duration_seconds") is not None and end > source["duration_seconds"]:
                errors.append(f"{path}: word interval exceeds source duration")
            expected_kind = {"source_timed": "source_exact", "aligned": "forced_alignment", "estimated": "derived_estimate"}.get(status)
            if kind != expected_kind:
                errors.append(f"{path}: alignment_status and timing provenance disagree")
            if status == "aligned":
                run = runs.get(run_id)
                if run is None or run.get("status") != "valid" or run.get("source_id") != source["id"] or run.get("transcript_revision_id") != transcript["id"]:
                    errors.append(f"{path}.timing_provenance.alignment_run_id: invalid alignment run")
            elif run_id is not None:
                errors.append(f"{path}.timing_provenance.alignment_run_id: only forced alignment may reference a run")
            if status == "estimated" and (not isinstance(method, str) or not method):
                errors.append(f"{path}.timing_provenance.method: estimate requires an explicit method")

    for transcript_id, transcript_words in words_by_transcript.items():
        _check_sequence(errors, f"$.words[{transcript_id}]", transcript_words)
        prior_end = -1
        for word in transcript_words:
            if isinstance(word.get("char_start"), int) and word["char_start"] < prior_end:
                errors.append(f"$.words[{transcript_id}]: character spans overlap or are out of order")
            if isinstance(word.get("char_end"), int):
                prior_end = word["char_end"]

    segments_by_transcript: dict[str, list[dict[str, Any]]] = {}
    for index, segment in enumerate(arrays["benchmark_segments"]):
        path = f"$.benchmark_segments[{index}]"
        if not isinstance(segment, dict):
            continue
        transcript_id = segment.get("transcript_revision_id")
        segments_by_transcript.setdefault(transcript_id, []).append(segment)
        first, last = words.get(segment.get("word_start_id")), words.get(segment.get("word_end_id"))
        if first is None or last is None or first.get("transcript_revision_id") != transcript_id or last.get("transcript_revision_id") != transcript_id:
            errors.append(f"{path}: orphan or cross-revision word range")
            continue
        count = last.get("sequence", -1) - first.get("sequence", 0) + 1
        if count <= 0 or segment.get("word_count") != count:
            errors.append(f"{path}: word range must be contiguous and word_count exact")
    for transcript_id, transcript_segments in segments_by_transcript.items():
        _check_sequence(errors, f"$.benchmark_segments[{transcript_id}]", transcript_segments)
        prior_end = -1
        for segment in transcript_segments:
            first, last = words.get(segment.get("word_start_id")), words.get(segment.get("word_end_id"))
            if first and last:
                if first.get("sequence", -1) <= prior_end:
                    errors.append(f"$.benchmark_segments[{transcript_id}]: ranges overlap or are out of order")
                prior_end = last.get("sequence", prior_end)

    topics_by_set: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for index, topic in enumerate(arrays["topics"]):
        path = f"$.topics[{index}]"
        if not isinstance(topic, dict):
            continue
        transcript_id = topic.get("transcript_revision_id")
        topics_by_set.setdefault((transcript_id, topic.get("topic_set_id")), []).append(topic)
        segment_ids = topic.get("benchmark_segment_ids")
        topic_segments = [segments.get(item) for item in segment_ids] if isinstance(segment_ids, list) else []
        if not topic_segments or any(item is None or item.get("transcript_revision_id") != transcript_id for item in topic_segments):
            errors.append(f"{path}.benchmark_segment_ids: orphan or cross-revision reference")
            continue
        sequences = [item["sequence"] for item in topic_segments]
        if sequences != list(range(sequences[0], sequences[-1] + 1)):
            errors.append(f"{path}.benchmark_segment_ids: segments must be contiguous and ordered")
        if topic.get("word_start_id") != topic_segments[0].get("word_start_id") or topic.get("word_end_id") != topic_segments[-1].get("word_end_id"):
            errors.append(f"{path}: topic word range must match its segment range")
    for key, topic_set in topics_by_set.items():
        _check_sequence(errors, f"$.topics[{key[0]},{key[1]}]", topic_set)

    target_maps = {
        "source": sources,
        "transcript_revision": transcripts,
        "cue": cues,
        "word": words,
        "benchmark_segment": segments,
        "topic": topics,
    }
    for index, evidence in enumerate(arrays["evidence_refs"]):
        path = f"$.evidence_refs[{index}]"
        if not isinstance(evidence, dict):
            continue
        source = sources.get(evidence.get("source_id"))
        if evidence.get("project_id") != project_id or source is None:
            errors.append(f"{path}: orphan project or source reference")
            continue
        transcript_id = evidence.get("transcript_revision_id")
        if transcript_id is not None:
            transcript = transcripts.get(transcript_id)
            if transcript is None or transcript.get("source_id") != source["id"]:
                errors.append(f"{path}.transcript_revision_id: orphan or cross-source reference")
        target = evidence.get("target")
        if not isinstance(target, dict) or target.get("entity_type") not in target_maps or target.get("entity_id") not in target_maps.get(target.get("entity_type"), {}):
            errors.append(f"{path}.target: orphan target reference")
        else:
            target_type = target["entity_type"]
            target_record = target_maps[target_type][target["entity_id"]]
            if target_type == "source":
                target_source = target_record["id"]
                target_transcript = None
            elif target_type == "transcript_revision":
                target_source = target_record.get("source_id")
                target_transcript = target_record["id"]
            else:
                target_transcript = target_record.get("transcript_revision_id")
                target_source = target_record.get("source_id")
                if target_source is None and target_transcript in transcripts:
                    target_source = transcripts[target_transcript].get("source_id")
            if target_source is not None and target_source != source["id"]:
                errors.append(f"{path}.target: target belongs to another source")
            if target_transcript is not None and target_transcript != transcript_id:
                errors.append(f"{path}.target: target belongs to another transcript revision")
            if target_type == "source" and transcript_id is not None:
                errors.append(f"{path}.transcript_revision_id: source target must not claim a transcript revision")
        _check_locator(errors, f"{path}.locator", evidence.get("locator"), source)

    order_keys = {
        "sources": lambda item: (item.get("sequence", -1), item.get("id", "")),
        "transcript_revisions": lambda item: (item.get("source_id", ""), item.get("revision_number", -1), item.get("id", "")),
        "cues": lambda item: (item.get("transcript_revision_id", ""), item.get("sequence", -1), item.get("id", "")),
        "alignment_runs": lambda item: (item.get("transcript_revision_id", ""), item.get("id", "")),
        "words": lambda item: (item.get("transcript_revision_id", ""), item.get("sequence", -1), item.get("id", "")),
        "benchmark_segments": lambda item: (item.get("transcript_revision_id", ""), item.get("sequence", -1), item.get("id", "")),
        "topics": lambda item: (item.get("transcript_revision_id", ""), item.get("topic_set_id", ""), item.get("sequence", -1), item.get("id", "")),
        "evidence_refs": lambda item: item.get("id", ""),
    }
    for name, key in order_keys.items():
        records = arrays[name]
        if records and all(isinstance(item, dict) for item in records) and records != sorted(records, key=key):
            errors.append(f"$.{name}: records are not in canonical deterministic order")

    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("documents", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.documents:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{path}: invalid JSON: {exc}")
            failed = True
            continue
        errors = validate_bundle(document)
        if errors:
            failed = True
            print(f"{path}: INVALID")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"{path}: VALID")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
