"""Fail-closed S15 translation of persisted machine Topic text.

The source Topics artifact stays immutable.  This adapter sends only its
user-facing title/summary fields to the already selected VideoText translator
and writes a separate, hash-bound translation record.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .videotext_runtime import translate as translate_videotext


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _timestamp(seconds: int) -> str:
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},000"


def _load_topics(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("saved machine Topics are unavailable")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("saved machine Topics are invalid") from error
    topics = payload.get("topics") if isinstance(payload, dict) else None
    detail = payload.get("topic_detail") if isinstance(payload, dict) else None
    if (payload.get("component") != "seminartext" or not isinstance(topics, list) or not topics
            or not isinstance(detail, dict) or detail.get("requested") not in {"low", "auto", "high"}
            or detail.get("executed") != detail["requested"]):
        raise ValueError("saved machine Topics have invalid structure or detail provenance")
    for topic in topics:
        if (not isinstance(topic, dict) or topic.get("semantic_status") != "REVIEW_REQUIRED"
                or not isinstance(topic.get("title"), str) or not topic["title"].strip()
                or not isinstance(topic.get("summary"), str) or not topic["summary"].strip()):
            raise ValueError("saved machine Topics have no translatable text")
    return payload, topics, _sha256(path)


def load_topic_translation(topics_path: Path, translation_path: Path) -> dict[str, Any]:
    """Validate a saved translation against its immutable machine Topics source."""
    _payload, topics, topics_sha256 = _load_topics(topics_path)
    if translation_path.is_symlink() or not translation_path.is_file():
        raise ValueError("saved Topic translation is unavailable")
    try:
        translation = json.loads(translation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("saved Topic translation is invalid") from error
    rows = translation.get("translations") if isinstance(translation, dict) else None
    if (translation.get("schema_version") != "1.0" or translation.get("component") != "integra"
            or translation.get("capability") != "topic_translation" or translation.get("status") != "COMPLETED"
            or translation.get("semantic_status") != "MACHINE_TRANSLATION_REVIEW_REQUIRED"
            or translation.get("source_topics_sha256") != topics_sha256 or translation.get("source_language") != "ru"
            or translation.get("requested_target_language") != "en"
            or translation.get("executed_target_language") != "en"
            or translation.get("translated_topic_count") != len(topics) or not isinstance(rows, list)):
        raise ValueError("saved Topic translation does not match machine Topics")
    expected_ids = [f"machine-topic-{topics_sha256[:20]}-{index:04d}" for index in range(len(topics))]
    if [row.get("topic_id") if isinstance(row, dict) else None for row in rows] != expected_ids:
        raise ValueError("saved Topic translation changed Topic identity or ordering")
    for source, row in zip(topics, rows):
        if (not isinstance(row.get("title"), str) or not row["title"].strip()
                or not isinstance(row.get("summary"), str) or not row["summary"].strip()
                or row["title"].strip() == source["title"].strip()
                or row["summary"].strip() == source["summary"].strip()):
            raise ValueError("saved Topic translation is incomplete")
    return translation


def _request_srt(topics: list[dict[str, Any]], path: Path) -> None:
    cues: list[str] = []
    for index, topic in enumerate(topics):
        for field, offset in (("title", 0), ("summary", 1)):
            cue_id = index * 2 + offset + 1
            start = cue_id * 2
            cues.append(f"{cue_id}\n{_timestamp(start)} --> {_timestamp(start + 1)}\n{topic[field].strip()}")
    path.write_text("\n\n".join(cues) + "\n", encoding="utf-8")


def translate_topics(topics_path: Path, output_path: Path, *, target_language: str, runtime: dict[str, Any]) -> dict[str, Any]:
    """Translate title/summary only, retaining every source-bound Topic field."""
    if target_language != "en":
        raise ValueError("selected Topic translation language is unsupported")
    if output_path.exists() or output_path.is_symlink():
        raise ValueError("saved Topic translation already exists")
    payload, topics, topics_sha256 = _load_topics(topics_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".topic-translation-", dir=output_path.parent) as temporary:
        temporary_root = Path(temporary)
        source_srt = temporary_root / "topic-text.srt"
        translated_srt = temporary_root / "translated-topic-text.json"
        _request_srt(topics, source_srt)
        translated = translate_videotext(source_srt, translated_srt, target=target_language, runtime=runtime)
        cues = translated.get("cues") if isinstance(translated, dict) else None
        issues = translated.get("issues") if isinstance(translated, dict) else None
        if (translated.get("component") != "videotext" or translated.get("capability") != "translation"
                or translated.get("source_language") != "ru" or translated.get("target_language") != target_language
                or translated.get("model") != runtime.get("model") or not isinstance(cues, list)
                or not isinstance(issues, list) or issues or len(cues) != len(topics) * 2):
            raise ValueError("Topic translation did not return a complete verified result")
        values: list[str] = []
        for expected_id, cue in enumerate(cues, 1):
            text = cue.get("text") if isinstance(cue, dict) else None
            if cue.get("id") != expected_id or not isinstance(text, str) or not text.strip():
                raise ValueError("Topic translation changed the requested text mapping")
            values.append(text.strip())
    translations = []
    for index, topic in enumerate(topics):
        title, summary = values[index * 2:index * 2 + 2]
        if title == topic["title"].strip() or summary == topic["summary"].strip():
            raise ValueError("Topic translation returned source text instead of a translation")
        translations.append({"topic_id": f"machine-topic-{topics_sha256[:20]}-{index:04d}",
                             "title": title, "summary": summary})
    result = {
        "schema_version": "1.0", "component": "integra", "capability": "topic_translation",
        "status": "COMPLETED", "semantic_status": "MACHINE_TRANSLATION_REVIEW_REQUIRED",
        "source_topics_sha256": topics_sha256, "source_language": "ru",
        "requested_target_language": target_language, "executed_target_language": target_language,
        "topic_detail": dict(payload["topic_detail"]), "translated_topic_count": len(translations),
        "runtime": {key: runtime[key] for key in ("component", "commit_sha", "adapter_sha256", "model")},
        "translations": translations,
    }
    temporary_output = output_path.with_name(f".{output_path.name}.tmp")
    try:
        temporary_output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary_output, output_path)
    finally:
        temporary_output.unlink(missing_ok=True)
    result["output_sha256"] = _sha256(output_path)
    return result
