"""One provider-neutral Process operation, isolated from normal project routing.

This pilot consumes only an explicitly supplied artifact and creates a fresh
OS-temporary attempt. Project/source IDs are descriptive, never filesystem grants.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

from . import _timed_transcript_provider as provider
from ._timed_transcript_provider import PilotFailure

CAPABILITY = "process.timed_transcript.normalize.v1"
MAX_INPUT_BYTES = 1024 * 1024
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
STAMP = r"([0-9]{2,6}):([0-5][0-9]):([0-5][0-9]),([0-9]{3})"
TIMES = re.compile(STAMP + r" --> " + STAMP + r"\Z")
MESSAGES = {
    "INVALID_REQUEST": "Некорректный запрос обработки.",
    "INPUT_UNAVAILABLE": "Исходная расшифровка недоступна.",
    "INPUT_CHANGED": "Исходная расшифровка изменилась.",
    "INVALID_TIMELINE": "Формат или временная шкала расшифровки некорректны.",
    "RUNTIME_UNAVAILABLE": "Исполнитель обработки недоступен.",
    "RUNTIME_IDENTITY_MISMATCH": "Проверка целостности исполнителя не пройдена.",
    "PROVIDER_FAILED": "Не удалось обработать расшифровку.",
    "INVALID_PROVIDER_RESULT": "Результат обработки не прошёл проверку.",
    "CANCELLED": "Обработка остановлена.",
    "TIMED_OUT": "Превышено время обработки.",
    "OUTPUT_LIMIT": "Превышен допустимый размер результата.",
    "INTERNAL_ERROR": "Не удалось завершить изолированную обработку.",
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _fields(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise PilotFailure("INVALID_REQUEST")


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise PilotFailure("INVALID_REQUEST")


def validate_request(request):
    _fields(request, {"schema_version", "capability_id", "project_id", "run_id", "source", "input", "options"})
    if request["schema_version"] != "1.0" or request["capability_id"] != CAPABILITY:
        raise PilotFailure("INVALID_REQUEST")
    _fields(request["source"], {"source_id", "revision"})
    _fields(request["input"], {"artifact_id", "sha256", "format"})
    for value in (request["project_id"], request["run_id"], request["source"]["source_id"],
                  request["source"]["revision"], request["input"]["artifact_id"]):
        _id(value)
    if (request["input"]["format"] != "srt" or not isinstance(request["input"]["sha256"], str)
            or not HASH.fullmatch(request["input"]["sha256"])):
        raise PilotFailure("INVALID_REQUEST")
    options = request["options"]
    if not isinstance(options, dict) or set(options) - {"media_duration_ms"}:
        raise PilotFailure("INVALID_REQUEST")
    duration = options.get("media_duration_ms")
    if duration is not None and (type(duration) is not int or not 0 < duration <= 3599999999999):
        raise PilotFailure("INVALID_REQUEST")
    return json.loads(canonical({**request, "options": {"media_duration_ms": duration}}))


def inspect_transcript(data, duration, *, output=False):
    """Validate the pilot's narrow integer-millisecond contract, not ASR quality."""
    try:
        text = data.decode("utf-8").replace("\r\n", "\n")
        if "\r" in text or "\x00" in text:
            raise ValueError("characters")
        blocks = [b for b in text.split("\n\n") if b.strip()]
        if not 0 < len(blocks) <= 10000:
            raise ValueError("count")
        cues = []
        numbered = None
        previous_id = 0
        for ordinal, block in enumerate(blocks, 1):
            lines = block.split("\n")
            has_id = bool(re.fullmatch(r"[0-9]+", lines[0].strip()))
            if numbered is not None and numbered != has_id:
                raise ValueError("mixed labels")
            numbered = has_id
            label = int(lines.pop(0)) if has_id else ordinal
            if label <= previous_id or (output and (not has_id or label != ordinal)):
                raise ValueError("labels")
            previous_id = label
            match = TIMES.fullmatch(lines.pop(0))
            if match is None:
                raise ValueError("timestamp")
            values = [int(v) for v in match.groups()]
            start = ((values[0] * 60 + values[1]) * 60 + values[2]) * 1000 + values[3]
            end = ((values[4] * 60 + values[5]) * 60 + values[6]) * 1000 + values[7]
            body = "\n".join(lines).strip()
            if (not body or end <= start or (cues and start < cues[-1][1])
                    or (duration is not None and end > duration)):
                raise ValueError("interval")
            cues.append((start, end, body))
        return cues
    except (ValueError, IndexError, UnicodeError) as error:
        raise PilotFailure("INVALID_PROVIDER_RESULT" if output else "INVALID_TIMELINE") from error


def _read_input(path):
    path = Path(path)
    # Check before resolve: an input grant never follows a link in any component.
    if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
        raise PilotFailure("INPUT_UNAVAILABLE")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise PilotFailure("INPUT_UNAVAILABLE")
    with path.open("rb") as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise PilotFailure("INPUT_UNAVAILABLE")
    return data


def execute(request, input_path, *, resources, cancelled=None, timeout_seconds=5.0,
            max_output_bytes=1024 * 1024):
    """Return a public result and private evidence; never look up a user project."""
    cancelled = cancelled or (lambda: False)
    attempt_id = uuid.uuid4().hex
    attempt = Path(tempfile.mkdtemp(prefix="integra-process-pilot-"))
    stage = attempt / "private"
    stage.mkdir(mode=0o700)
    publish = attempt / "pending"
    publish.mkdir(mode=0o700)
    result = {"schema_version": "1.0", "capability_id": CAPABILITY, "attempt_id": attempt_id,
              "request_sha256": None, "status": "FAILED", "error": None, "artifacts": [],
              "semantic_authority": "MACHINE_UNVERIFIED"}
    evidence = {"schema_version": "1.0", "mode": "ISOLATED_PILOT", "attempt_id": attempt_id,
                "executor_sha256": provider.digest(Path(__file__)),
                "adapter_sha256": provider.digest(Path(provider.__file__)),
                "canonical_routing_changed": False}
    try:
        request = validate_request(request)
        if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= 30 or type(max_output_bytes) is not int
                or not 1 <= max_output_bytes <= 2 * MAX_INPUT_BYTES):
            raise PilotFailure("INVALID_REQUEST")
        result.update(request_sha256=sha(canonical(request)), project_id=request["project_id"],
                      run_id=request["run_id"], source=request["source"])
        evidence["request"] = request
        evidence["request_sha256"] = result["request_sha256"]
        if cancelled():
            raise PilotFailure("CANCELLED")
        original = _read_input(input_path)
        if sha(original) != request["input"]["sha256"]:
            raise PilotFailure("INPUT_CHANGED")
        cues = inspect_transcript(original, request["options"]["media_duration_ms"])
        owned_source = stage / "input.srt"
        owned_source.write_bytes(original)
        owned_source.chmod(0o400)
        if provider.digest(owned_source) != request["input"]["sha256"]:
            raise PilotFailure("INPUT_CHANGED")
        runtime = provider.preflight(Path(resources))
        evidence["runtime"] = runtime
        target = stage / "normalized.srt"
        response = provider.run(runtime, owned_source, target, cancelled=cancelled,
                                timeout_seconds=timeout_seconds, max_output_bytes=max_output_bytes)
        if (target.is_symlink() or not target.is_file() or target.stat().st_size > max_output_bytes):
            raise PilotFailure("INVALID_PROVIDER_RESULT")
        output = target.read_bytes()
        produced = inspect_transcript(output, request["options"]["media_duration_ms"], output=True)
        if produced != cues or response.get("cue_count") != len(cues):
            raise PilotFailure("INVALID_PROVIDER_RESULT")
        if (provider.digest(owned_source) != request["input"]["sha256"]
                or sha(_read_input(input_path)) != request["input"]["sha256"]):
            raise PilotFailure("INPUT_CHANGED")
        if cancelled():
            raise PilotFailure("CANCELLED")
        result.update(status="COMPLETED", artifacts=[{
            "artifact_id": "sha256:" + sha(output), "path": "transcript.srt", "format": "srt",
            "sha256": sha(output), "size_bytes": len(output), "cue_count": len(cues),
            "cue_labels": "POSITIONAL_ORDINALS", "derived_from": request["input"],
        }])
        (publish / "transcript.srt").write_bytes(output)
        evidence.update(input_sha256=sha(original), output_sha256=sha(output))
    except PilotFailure as error:
        code = error.code if error.code in MESSAGES else "INTERNAL_ERROR"
        result.update(status=code if code in {"CANCELLED", "TIMED_OUT"} else "FAILED",
                      error={"code": code, "message": MESSAGES[code]}, artifacts=[])
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        result.update(status="FAILED", error={"code": "INTERNAL_ERROR", "message": MESSAGES["INTERNAL_ERROR"]}, artifacts=[])
        evidence["exception_type"] = type(error).__name__
    finally:
        shutil.rmtree(stage)
    # Only this fresh private attempt can publish. The directory rename exposes
    # the output and its matching terminal record together; no late cancellation.
    if result["status"] != "COMPLETED":
        (publish / "transcript.srt").unlink(missing_ok=True)
    try:
        _publish(publish, attempt, result, evidence)
    except OSError as error:
        result.update(status="FAILED", artifacts=[], error={
            "code": "INTERNAL_ERROR", "message": MESSAGES["INTERNAL_ERROR"]})
        evidence["publication_error"] = type(error).__name__
        evidence.pop("output_sha256", None)
        # Disk failure cannot guarantee a durable terminal record. Discard the
        # unpublished success and return a truthful in-memory failure regardless.
        try:
            publish.chmod(0o700)
            shutil.rmtree(publish)
            publish.mkdir(mode=0o700)
            _publish(publish, attempt, result, evidence)
        except OSError as retry_error:
            evidence["publication_persisted"] = False
            evidence["publication_retry_error"] = type(retry_error).__name__
            try:
                if publish.exists():
                    publish.chmod(0o700)
                    shutil.rmtree(publish)
            except OSError:
                evidence["unpublished_cleanup_failed"] = True
            evidence["result_sha256"] = sha(canonical(result))
    return {"result": result, "evidence": evidence, "attempt_path": str(attempt)}


def _publish(publish, attempt, result, evidence):
    evidence["result_sha256"] = sha(canonical(result))
    (publish / "result.json").write_bytes(canonical(result) + b"\n")
    (publish / "evidence.json").write_bytes(canonical(evidence) + b"\n")
    for path in publish.iterdir():
        path.chmod(0o400)
    publish.chmod(0o500)
    os.rename(publish, attempt / "published")
