"""Fail-closed S15 Topic translation through Integra's TranslateGemma adapter.

The machine Topic snapshot remains the authority for its original Russian
wording, order and source spans.  This module translates only the two S15 text
fields (``title`` and ``summary``) through the governed Integra translation
path and records a separately bound derivative.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .protocol import canonical_json
from .translategemma_runtime import preflight, translate


SOURCE_LANGUAGE = "ru"
TARGET_LANGUAGE = "en"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _timestamp(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},000"


def _owned_file(project_dir: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str):
        raise ValueError(f"{label} path is invalid")
    path = Path(value)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is unavailable")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(project_dir.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise ValueError(f"{label} is outside this Integra project") from error
    return resolved


def _machine_topics(project_dir: Path, topics_path: Any) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    path = _owned_file(project_dir, topics_path, "machine Topics")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("saved machine Topics are invalid") from error
    topics = payload.get("topics") if isinstance(payload, dict) else None
    if payload.get("component") != "seminartext" or not isinstance(topics, list) or not topics:
        raise ValueError("saved machine Topics are unavailable")
    validated: list[dict[str, Any]] = []
    for sequence, topic in enumerate(topics):
        if not isinstance(topic, dict) or topic.get("semantic_status") != "REVIEW_REQUIRED":
            raise ValueError("saved machine Topics have invalid review authority")
        title, summary = topic.get("title"), topic.get("summary")
        start, end = topic.get("start_seconds"), topic.get("end_seconds")
        if (not isinstance(title, str) or not title.strip() or not isinstance(summary, str)
                or not summary.strip() or not isinstance(start, (int, float))
                or not isinstance(end, (int, float)) or end <= start):
            raise ValueError("a saved Topic has no usable source text")
        validated.append({"sequence": sequence, "topic": topic, "title": title.strip(), "summary": summary.strip()})
    return path, payload, validated


def _write_transport(path: Path, topics: list[dict[str, Any]]) -> dict[int, tuple[int, str]]:
    """Encode S15 fields as one reversible, temporary SRT transport.

    The artificial timing is never exposed as a Topic timestamp; it preserves
    the exact field order while Integra owns translation inference.
    """
    blocks: list[str] = []
    expected: dict[int, tuple[int, str]] = {}
    cue_id = 1
    for item in topics:
        for field in ("title", "summary"):
            text = item[field]
            if "-->" in text or "\x00" in text:
                raise ValueError("Topic text cannot be represented safely for translation")
            start = (cue_id - 1) * 2
            blocks.append(f"{cue_id}\n{_timestamp(start)} --> {_timestamp(start + 1)}\n{text}")
            expected[cue_id] = (item["sequence"], field)
            cue_id += 1
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return expected


def _validated_translation(value: Any, expected: dict[int, tuple[int, str]]) -> dict[int, str]:
    if not isinstance(value, dict):
        raise ValueError("Topic translation output is invalid")
    if (value.get("component") != "integra.translation" or value.get("capability") != "translation"
            or value.get("source_language") != SOURCE_LANGUAGE or value.get("target_language") != TARGET_LANGUAGE):
        raise ValueError("Topic translation runtime differs from the required contract")
    if value.get("issues"):
        raise ValueError("Topic translation requires review; no translated Topics were published")
    cues = value.get("cues")
    if not isinstance(cues, list) or len(cues) != len(expected):
        raise ValueError("Topic translation cue count differs from its source")
    translated: dict[int, str] = {}
    for cue in cues:
        if not isinstance(cue, dict):
            raise ValueError("Topic translation cue is invalid")
        try:
            cue_id = int(cue.get("id"))
        except (TypeError, ValueError) as error:
            raise ValueError("Topic translation cue identity is invalid") from error
        text = cue.get("text")
        if cue_id not in expected or cue_id in translated or not isinstance(text, str) or not text.strip():
            raise ValueError("Topic translation cues do not bind to their source")
        translated[cue_id] = text.strip()
    if set(translated) != set(expected):
        raise ValueError("Topic translation omitted a source field")
    return translated


def _review_lineage(project_dir: Path, outputs: dict[str, Any]) -> dict[str, str] | None:
    keys = ("process_reviewed_topics", "process_topic_review_receipt", "process_topic_review_decisions")
    values = {key: outputs.get(key) for key in keys}
    if not any(value is not None for value in values.values()):
        return None
    if not all(isinstance(value, str) for value in values.values()):
        raise ValueError("persisted Process Topic review is incomplete")
    return {key + "_sha256": _sha256(_owned_file(project_dir, value, key)) for key, value in values.items()}


def translate_topics(project_dir: Path, *, source_id: str, source_run_id: str,
                     source_outputs: dict[str, Any], artifact_dir: Path) -> dict[str, str]:
    """Create an additive S15 result only after all bindings validate."""
    if not isinstance(source_id, str) or not source_id or not isinstance(source_run_id, str) or not source_run_id:
        raise ValueError("Topic translation source identity is invalid")
    if not isinstance(source_outputs, dict):
        raise ValueError("Topic translation source outputs are invalid")
    source_path, payload, source_topics = _machine_topics(project_dir, source_outputs.get("topics"))
    detail = payload.get("topic_detail")
    if detail is not None and (not isinstance(detail, dict) or detail.get("requested") not in {"low", "auto", "high"}
                               or detail.get("executed") != detail.get("requested")):
        raise ValueError("saved machine Topics have invalid detail provenance")
    lineage = _review_lineage(project_dir, source_outputs)
    artifact_dir.mkdir(parents=True, exist_ok=False)
    transport = artifact_dir / "topic_translation_input.srt"
    raw = artifact_dir / "topic_translation_raw.json"
    expected = _write_transport(transport, source_topics)
    runtime = preflight()
    response = translate(transport, raw, source=SOURCE_LANGUAGE, target=TARGET_LANGUAGE, runtime=runtime)
    translated = _validated_translation(response, expected)
    source_digest = _sha256(source_path)
    presented = []
    text_lines: list[str] = []
    for item in source_topics:
        sequence = item["sequence"]
        topic = item["topic"]
        identifier = f"machine-topic-{source_digest[:20]}-{sequence:04d}"
        result = {
            "topic_id": identifier,
            "source_index": sequence,
            "original": {"title": item["title"], "summary": item["summary"]},
            "translation": {
                "title": translated[2 * sequence + 1],
                "summary": translated[2 * sequence + 2],
            },
            "start_seconds": topic["start_seconds"], "end_seconds": topic["end_seconds"],
            "source_span": {"start_segment_id": topic.get("start_segment_id"),
                            "evidence_start_id": topic.get("evidence_start_id"),
                            "evidence_end_id": topic.get("evidence_end_id")},
            "semantic_status": "MACHINE_TRANSLATION_REVIEW_REQUIRED",
        }
        presented.append(result)
        text_lines.extend([
            f"{result['start_seconds']:.3f}–{result['end_seconds']:.3f}",
            result["translation"]["title"], result["translation"]["summary"], "",
        ])
    translated_topics = {
        "schema_version": "1.0", "artifact_type": "integra.process_topic_translation",
        "source_id": source_id, "source_run_id": source_run_id,
        "source_topics_sha256": source_digest, "source_language": SOURCE_LANGUAGE,
        "target_language": TARGET_LANGUAGE, "topic_count": len(presented),
        "topic_detail": detail if detail is not None else {"status": "UNAVAILABLE_LEGACY"},
        "review_lineage": lineage, "topics": presented,
    }
    translated_path = artifact_dir / "topic_translation.json"
    translated_path.write_bytes(canonical_json(translated_topics) + b"\n")
    text_path = artifact_dir / "topic_translation.txt"
    text_path.write_text("\n".join(text_lines), encoding="utf-8")
    provenance = {
        "schema_version": "1.0", "artifact_type": "integra.process_topic_translation_provenance",
        "status": "COMPLETED", "source_id": source_id, "source_run_id": source_run_id,
        "source_topics_sha256": source_digest, "source_language": SOURCE_LANGUAGE,
        "requested_target_language": TARGET_LANGUAGE, "executed_target_language": TARGET_LANGUAGE,
        "translated_field_count": len(expected), "translated_topic_count": len(presented),
        "runtime": runtime, "review_lineage": lineage,
        "transport_sha256": _sha256(transport), "provider_output_sha256": _sha256(raw),
        "output_sha256": _sha256(translated_path), "text_sha256": _sha256(text_path),
    }
    provenance_path = artifact_dir / "topic_translation_provenance.json"
    provenance_path.write_bytes(canonical_json(provenance) + b"\n")
    return {"topic_translation": str(translated_path), "topic_translation_txt": str(text_path),
            "topic_translation_provenance": str(provenance_path),
            "topic_translation_raw": str(raw), "topic_translation_input": str(transport)}


def load_topic_translation(project_dir: Path, *, source_id: str, source_run_id: str,
                           source_outputs: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    """Load an existing S15 derivative without calling a provider on reopen."""
    source_path, _payload, source_topics = _machine_topics(project_dir, source_outputs.get("topics"))
    translated_path = _owned_file(project_dir, outputs.get("topic_translation"), "saved Topic translation")
    provenance_path = _owned_file(project_dir, outputs.get("topic_translation_provenance"), "saved Topic translation provenance")
    text_path = _owned_file(project_dir, outputs.get("topic_translation_txt"), "saved translated Topics text")
    try:
        translated = json.loads(translated_path.read_text(encoding="utf-8"))
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("saved Topic translation is invalid") from error
    source_digest = _sha256(source_path)
    if (not isinstance(source_run_id, str) or not source_run_id):
        raise ValueError("saved Topic translation source run is invalid")
    expected_lineage = _review_lineage(project_dir, source_outputs)
    if (not isinstance(translated, dict) or not isinstance(provenance, dict)
            or translated.get("artifact_type") != "integra.process_topic_translation"
            or translated.get("source_id") != source_id or translated.get("source_run_id") != source_run_id
            or translated.get("source_topics_sha256") != source_digest
            or translated.get("source_language") != SOURCE_LANGUAGE or translated.get("target_language") != TARGET_LANGUAGE
            or translated.get("topic_count") != len(source_topics)
            or translated.get("review_lineage") != expected_lineage
            or provenance.get("status") != "COMPLETED" or provenance.get("source_id") != source_id
            or provenance.get("source_run_id") != source_run_id
            or provenance.get("source_topics_sha256") != source_digest
            or provenance.get("review_lineage") != expected_lineage
            or provenance.get("output_sha256") != _sha256(translated_path)
            or provenance.get("text_sha256") != _sha256(text_path)
            or provenance.get("requested_target_language") != TARGET_LANGUAGE
            or provenance.get("executed_target_language") != TARGET_LANGUAGE):
        raise ValueError("saved Topic translation does not match its source evidence")
    topics = translated.get("topics")
    if not isinstance(topics, list) or len(topics) != len(source_topics):
        raise ValueError("saved Topic translation has invalid topic count")
    for sequence, (source, value) in enumerate(zip(source_topics, topics)):
        topic = source["topic"]
        expected_span = {"start_segment_id": topic.get("start_segment_id"),
                         "evidence_start_id": topic.get("evidence_start_id"),
                         "evidence_end_id": topic.get("evidence_end_id")}
        expected_id = f"machine-topic-{source_digest[:20]}-{sequence:04d}"
        if (not isinstance(value, dict) or value.get("source_index") != sequence
                or value.get("topic_id") != expected_id
                or value.get("original") != {"title": source["title"], "summary": source["summary"]}
                or value.get("start_seconds") != topic["start_seconds"]
                or value.get("end_seconds") != topic["end_seconds"]
                or value.get("source_span") != expected_span
                or value.get("semantic_status") != "MACHINE_TRANSLATION_REVIEW_REQUIRED"
                or not isinstance(value.get("translation"), dict)
                or not all(isinstance(value["translation"].get(field), str) and value["translation"][field].strip()
                           for field in ("title", "summary"))):
            raise ValueError("saved Topic translation has invalid source binding")
    return translated
