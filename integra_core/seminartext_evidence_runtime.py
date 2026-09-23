"""Controlled adapter for SeminarText's canonical Evidence Foundation.

Preparing a human review creates only an Integra-owned request bound to exact
media, transcript and word-timeline bytes. Applying it requires an explicit
human acknowledgement. The separate machine path invokes the same pinned
component with candidate authority and machine_unverified assurance (PR-012);
it never records a human decision or accepts semantic content.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .protocol import canonical_json, content_sha256
from .seminartext_runtime import PINNED_COMMIT
from .transcript_output import resolve_persisted_project_path


EVIDENCE_ENTRYPOINT = Path("seminartext_modules/evidence_foundation.py")
VALIDATOR = Path("schemas/validate_canonical_evidence_v1.py")
EVIDENCE_ENTRYPOINT_SHA256 = "6adcf15e9767c36ad2d0dfe3a6a995d90c41b5f1671b4c9434a4b48f590e3856"
VALIDATOR_SHA256 = "889e6cdf3dc2dd7504f76923c04e2d8d1eceabdb828d0c110ddc1059b107860e"
BUNDLED_RUNTIME_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "seminartext"
REVIEWER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{1,127}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{label} is unavailable") from error
    if path.is_symlink() or not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    return resolved


def _inside(path: Path, root: Path, label: str) -> Path:
    resolved = _regular(path, label)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as error:
        raise ValueError(f"{label} must be owned by this Integra project") from error
    return resolved


def _runtime_root() -> tuple[Path, str]:
    configured = os.environ.get("INTEGRA_SEMINARTEXT_CHECKOUT")
    if configured:
        root = Path(configured).expanduser()
        if root.is_symlink() or not root.is_dir():
            raise ValueError("SeminarText checkout is unsafe or missing")
        try:
            commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                                    capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError("SeminarText checkout cannot be verified") from error
        if commit != PINNED_COMMIT:
            raise ValueError("SeminarText checkout does not match the pinned commit")
        origin = "EXTERNAL_PINNED_CHECKOUT"
    else:
        root = BUNDLED_RUNTIME_ROOT
        commit = PINNED_COMMIT
        origin = "BUNDLED_PERSONAL_RUNTIME"
        if root.is_symlink() or not root.is_dir():
            raise ValueError("SeminarText Evidence runtime is not configured")
    entrypoint, validator = root / EVIDENCE_ENTRYPOINT, root / VALIDATOR
    if entrypoint.is_symlink() or not entrypoint.is_file() or _sha256(entrypoint) != EVIDENCE_ENTRYPOINT_SHA256:
        raise ValueError("SeminarText Evidence Foundation differs from the pinned runtime")
    if validator.is_symlink() or not validator.is_file() or _sha256(validator) != VALIDATOR_SHA256:
        raise ValueError("SeminarText Evidence validator differs from the pinned runtime")
    return root.resolve(strict=True), origin


def preflight() -> dict[str, Any]:
    """Verify the exact read-only SeminarText Evidence runtime."""
    root, origin = _runtime_root()
    return {"state": "READY", "component": "seminartext", "capability": "canonical_evidence",
            "commit_sha": PINNED_COMMIT, "checkout": str(root), "origin": origin,
            "entrypoint": str(root / EVIDENCE_ENTRYPOINT), "entrypoint_sha256": EVIDENCE_ENTRYPOINT_SHA256,
            "validator_sha256": VALIDATOR_SHA256}


def _review_root(project_dir: Path, source_id: str) -> Path:
    token = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:24]
    path = project_dir / "review" / "transcript-evidence" / token
    try:
        path.resolve().relative_to(project_dir.resolve(strict=True))
    except ValueError as error:
        raise ValueError("review directory escapes its project") from error
    return path


def _alignment(timeline: dict[str, Any]) -> dict[str, Any]:
    words = timeline.get("words")
    if not isinstance(words, list) or not words:
        raise ValueError("Word Timeline contains no words")
    evidence_words: list[dict[str, Any]] = []
    for item in words:
        if not isinstance(item, dict):
            raise ValueError("Word Timeline contains an invalid word")
        if item.get("alignment_status") == "UNALIGNED":
            continue
        token = item.get("text", item.get("word"))
        start = item.get("start_seconds", item.get("start"))
        end = item.get("end_seconds", item.get("end"))
        if not isinstance(token, str) or not token or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise ValueError("Word Timeline has invalid aligned timing")
        evidence_words.append({"word": token, "start": start, "end": end, "score": item.get("score")})
    if not evidence_words:
        raise ValueError("Word Timeline has no aligned words")
    model = timeline.get("model") if isinstance(timeline.get("model"), dict) else {}
    model_sha = model.get("weights_sha256", timeline.get("model_sha256"))
    if not isinstance(model_sha, str) or re.fullmatch(r"[0-9a-f]{64}", model_sha) is None:
        raise ValueError("Word Timeline has no pinned model hash")
    return {
        "aligner": (timeline.get("aligner") or {}).get("name", "WhisperX") if isinstance(timeline.get("aligner"), dict) else "WhisperX",
        "aligner_version": (timeline.get("aligner") or {}).get("version", "3.8.6") if isinstance(timeline.get("aligner"), dict) else "3.8.6",
        "config": {"mode": "integra_owned_word_timeline", "no_asr": True, "timeline_sha256": content_sha256(timeline)},
        "model": model.get("id", "jonatasgrosman/wav2vec2-large-xlsr-53-russian"),
        "model_revision": model.get("revision", timeline.get("model_revision", "unknown")),
        "model_sha256": model_sha,
        "words": evidence_words,
    }


def prepare_transcript_review(project_dir: Path, *, source_id: str, media_path: str, transcript_path: str,
                              word_timeline_path: str) -> dict[str, Any]:
    """Persist an immutable review request; this never promotes semantic state."""
    root = Path(project_dir).resolve(strict=True)
    media = _inside(Path(media_path), root, "source media")
    transcript = _inside(Path(transcript_path), root, "transcript")
    timeline_file = _inside(Path(word_timeline_path), root, "Word Timeline")
    text = transcript.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("transcript is empty")
    try:
        timeline = json.loads(timeline_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Word Timeline is invalid JSON") from error
    alignment = _alignment(timeline)
    request = {
        "schema_version": "1.0", "artifact_type": "integra.transcript_review_request",
        "status": "REVIEW_REQUIRED", "semantic_authority": "MACHINE_OUTPUT_REQUIRES_HUMAN_DECISION",
        "source_id": source_id, "media_path": str(media), "media_sha256": _sha256(media),
        "transcript_path": str(transcript), "transcript_sha256": _sha256(transcript),
        "word_timeline_path": str(timeline_file), "word_timeline_sha256": _sha256(timeline_file),
        "alignment_sha256": content_sha256(alignment), "created_at": _now(),
        "required_action": "Inspect the complete TXT transcript and explicitly confirm it is accurate enough for Canonical Evidence.",
        "automatic_acceptance": False,
    }
    request["request_sha256"] = content_sha256({key: value for key, value in request.items() if key != "request_sha256"})
    directory = _review_root(root, source_id); directory.mkdir(parents=True, exist_ok=True)
    path = directory / "review_request.json"
    if path.exists():
        previous = json.loads(_inside(path, root, "prepared review request").read_text(encoding="utf-8"))
        comparable = lambda value: {key: item for key, item in value.items() if key not in {"created_at", "request_sha256"}}
        if comparable(previous) == comparable(request) and previous.get("request_sha256") == content_sha256({key: item for key, item in previous.items() if key != "request_sha256"}):
            return previous | {"review_request_path": str(path)}
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(canonical_json(request) + b"\n")
    os.replace(temporary, path)
    return request | {"review_request_path": str(path)}


def _invoke(runtime: Path, *arguments: str) -> dict[str, Any]:
    completed = subprocess.run([sys.executable, str(runtime / EVIDENCE_ENTRYPOINT), *arguments], capture_output=True,
                               text=True, timeout=120)
    if completed.returncode != 0:
        raise ValueError((completed.stderr or completed.stdout or "SeminarText Evidence Foundation failed").strip()[:500])
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("SeminarText Evidence Foundation returned invalid JSON") from error


def _apply_human_transcript_review(project_dir: Path, *, source_id: str, media_path: str, transcript_path: str,
                                  word_timeline_path: str, reviewer_id: str, acknowledged: bool,
                                  expected_request_sha256: str = "") -> dict[str, Any]:
    """Apply a user's whole-transcript confirmation through pinned SeminarText.

    This method is intentionally unusable without the caller's explicit positive
    acknowledgement.  It must only be invoked by the macOS review action after
    the user has inspected the TXT artifact.
    """
    if not acknowledged:
        raise ValueError("human transcript review acknowledgement is required")
    if REVIEWER_ID.fullmatch(reviewer_id or "") is None:
        raise ValueError("reviewer identifier is invalid")
    root = Path(project_dir).resolve(strict=True)
    review_dir = _review_root(root, source_id)
    request_path = _inside(review_dir / "review_request.json", root, "prepared review request")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    actual_request_sha = content_sha256({key: value for key, value in request.items() if key != "request_sha256"})
    if not expected_request_sha256 or actual_request_sha != expected_request_sha256 or request.get("request_sha256") != expected_request_sha256:
        raise ValueError("prepared review request changed; inspect the transcript again")
    if request.get("source_id") != source_id:
        raise ValueError("prepared review belongs to another source")
    for key, supplied in (("media", media_path), ("transcript", transcript_path), ("word_timeline", word_timeline_path)):
        artifact = _inside(Path(supplied), root, key)
        if str(artifact) != request.get(key + "_path") or _sha256(artifact) != request.get(key + "_sha256"):
            raise ValueError("reviewed artifact changed; inspect the transcript again")
    runtime, origin = _runtime_root()
    if (review_dir / "review_result.json").exists():
        result_path = _inside(review_dir / "review_result.json", root, "persisted review result")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("review_request_sha256") != expected_request_sha256 or result.get("reviewer_id") != reviewer_id or result.get("result_sha256") != content_sha256({key: value for key, value in result.items() if key != "result_sha256"}):
            raise ValueError("a different reviewed Evidence result already exists")
        bundle = _inside(Path(result["seminartext"]["canonical_evidence_path"]), root, "persisted Canonical Evidence")
        if _sha256(bundle) != result["seminartext"]["canonical_evidence_sha256"]:
            raise ValueError("persisted Canonical Evidence changed")
        return result | {"review_result_path": str(result_path)}
    # An interrupted attempt is retained for diagnosis but never published.
    # A new attempt cannot collide with, or consume, its partial artifacts.
    component_project = review_dir / ("seminartext-project-" + uuid.uuid4().hex)
    source_token = "source_" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:24]
    media = Path(request["media_path"]); transcript = Path(request["transcript_path"])
    target_media = component_project / "source" / "media" / ("original" + media.suffix.lower())
    target_media.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(media, target_media)
    (component_project / "sources.json").write_text(json.dumps({"schema_version": 1, "videos": [{
        "source_id": source_token, "order": 1, "type": "local", "file": target_media.relative_to(component_project).as_posix(),
        "title": source_id, "duration_seconds": max(item["end"] for item in _alignment(json.loads(Path(request["word_timeline_path"]).read_text()))["words"]),
    }], "documents": []}, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (component_project / "seminar.yaml").write_text("title: Integra reviewed source\nlanguage: ru\n", encoding="utf-8")
    component_text = component_project / "input" / "transcript.txt"; component_text.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(transcript, component_text)
    alignment_path = component_project / "input" / "alignment.json"
    alignment = _alignment(json.loads(Path(request["word_timeline_path"]).read_text(encoding="utf-8")))
    alignment_path.write_bytes(canonical_json(alignment) + b"\n")
    if _sha256(target_media) != request["media_sha256"] or _sha256(component_text) != request["transcript_sha256"] or content_sha256(alignment) != request["alignment_sha256"]:
        raise ValueError("reviewed artifact changed while copying; inspect the transcript again")
    promotion = _invoke(runtime, "promote-transcript", str(component_project), "--source-id", source_token,
                        "--text-file", str(component_text), "--state", "verified", "--reviewer", reviewer_id,
                        "--generation-method", "integra_human_confirmed_txt_review")
    alignment_result = _invoke(runtime, "align", str(component_project), "--source-id", source_token,
                               "--revision-id", promotion["revision_id"], "--media", str(target_media),
                               "--alignment-json", str(alignment_path))
    # The pinned component's cross-record validator is dependency-free and is
    # the runtime minimum.  JSON Schema validation is additionally performed
    # by CI where jsonschema is installed; the bundled app never pretends an
    # unavailable optional Python package is present.
    check = _invoke(runtime, "evidence-check", str(component_project), "--cross-record-only", "--json")
    if check.get("status") != "PASS":
        raise ValueError("SeminarText canonical evidence validation failed")
    bundle = component_project / "evidence" / "canonical_bundle.json"
    result = {"schema_version": "1.0", "artifact_type": "integra.transcript_review_result", "status": "EVIDENCE_CREATED",
              "decision": "HUMAN_CONFIRMED_WHOLE_TRANSCRIPT", "reviewer_id": reviewer_id, "decided_at": _now(),
              "review_request_sha256": request["request_sha256"], "seminartext": {"commit_sha": PINNED_COMMIT, "origin": origin,
              "transcript_revision_id": promotion["revision_id"], "alignment_run_id": alignment_result["alignment_run_id"],
              "canonical_evidence_path": str(bundle), "canonical_evidence_sha256": _sha256(bundle)}}
    result["result_sha256"] = content_sha256({key: value for key, value in result.items() if key != "result_sha256"})
    path = review_dir / "review_result.json"; temporary = path.with_suffix(".tmp")
    temporary.write_bytes(canonical_json(result) + b"\n"); os.replace(temporary, path)
    return result | {"review_result_path": str(path)}


def apply_human_transcript_review(project_dir: Path, *, source_id: str, **arguments: Any) -> dict[str, Any]:
    """Serialize confirmation for a source, including component execution."""
    root = Path(project_dir).resolve(strict=True)
    directory = _review_root(root, source_id)
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "apply.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("a transcript review is already running for this source") from error
        try:
            return _apply_human_transcript_review(root, source_id=source_id, **arguments)
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _validate_machine_assurance(bundle: Path) -> None:
    revisions = json.loads(bundle.read_text(encoding="utf-8")).get("transcript_revisions", [])
    if len(revisions) != 1 or revisions[0].get("authority") != "candidate":
        raise ValueError("machine Evidence must retain unverified candidate assurance")
    provenance = revisions[0].get("transcript_provenance", {})
    if (provenance.get("verification_state") != "machine_unverified"
            or provenance.get("origin") != "machine_generated" or provenance.get("reviewer") is not None
            or provenance.get("verification_ranges") != []):
        raise ValueError("machine Evidence must retain unverified candidate assurance")


def create_machine_evidence(project_dir: Path, *, source_id: str, media_path: str,
                            transcript_path: str, word_timeline_path: str) -> dict[str, Any]:
    """Import machine evidence through SeminarText PR-012 without a review claim.

    This creates a candidate transcript revision, never a human ReviewDecision
    or accepted knowledge. Human-confirmed revisions use the separate API above.
    """
    root = Path(project_dir).resolve(strict=True)
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source identifier is required")
    paths = {name: _inside(Path(value), root, name) for name, value in (
        ("media", media_path), ("transcript", transcript_path), ("word_timeline", word_timeline_path))}
    transcript_bytes = paths["transcript"].read_bytes()
    timeline_bytes = paths["word_timeline"].read_bytes()
    if not transcript_bytes.decode("utf-8").strip():
        raise ValueError("transcript is empty")
    alignment = _alignment(json.loads(timeline_bytes))
    identity = {"source_id": source_id, "component_commit": PINNED_COMMIT,
                "media_sha256": _sha256(paths["media"]),
                "transcript_sha256": hashlib.sha256(transcript_bytes).hexdigest(),
                "word_timeline_sha256": hashlib.sha256(timeline_bytes).hexdigest()}
    runtime, origin = _runtime_root()
    token = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:24]
    directory = root / "evidence" / "machine" / token
    for parent in reversed((directory, *directory.parents)):
        if parent == root or root not in parent.parents:
            continue
        if parent.is_symlink():
            raise ValueError("machine Evidence directory must not contain symlinks")
        parent.mkdir(exist_ok=True)
    target = directory / content_sha256(identity)
    if target.is_symlink():
        raise ValueError("machine Evidence target must not be a symlink")
    lock = os.open(directory / "create.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock, "a") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("machine Evidence creation is already running for this source") from error
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix=".machine-", dir=directory) as temporary:
                stage = Path(temporary)
                component = stage / ("source_" + token)
                media = component / "source" / ("original" + paths["media"].suffix.lower())
                media.parent.mkdir(parents=True)
                text = component / "input" / "transcript.txt"
                text.parent.mkdir()
                shutil.copyfile(paths["media"], media)
                text.write_bytes(transcript_bytes)
                alignment_path = component / "input" / "alignment.json"
                alignment_path.write_bytes(canonical_json(alignment) + b"\n")
                (component / "sources.json").write_bytes(canonical_json({"schema_version": 1,
                    "videos": [{"source_id": "source_" + token, "order": 1, "type": "local",
                        "file": media.relative_to(component).as_posix(), "title": source_id,
                        "duration_seconds": max(word["end"] for word in alignment["words"])}],
                    "documents": []}) + b"\n")
                (component / "seminar.yaml").write_text("title: Integra machine evidence\nlanguage: ru\n", encoding="utf-8")
                if (_sha256(media) != identity["media_sha256"] or _sha256(text) != identity["transcript_sha256"]
                        or any(_sha256(path) != identity[name + "_sha256"] for name, path in paths.items())):
                    raise ValueError("machine Evidence inputs changed while copying")
                promoted = _invoke(runtime, "promote-transcript", str(component), "--source-id", "source_" + token,
                    "--text-file", str(text), "--state", "review_required", "--verification-state", "machine_unverified",
                    "--generation-method", "integra_machine_transcript_import")
                aligned = _invoke(runtime, "align", str(component), "--source-id", "source_" + token,
                    "--revision-id", promoted["revision_id"], "--media", str(media), "--alignment-json", str(alignment_path))
                checked = _invoke(runtime, "evidence-check", str(component), "--cross-record-only", "--json")
                if checked.get("status") != "PASS":
                    raise ValueError("SeminarText machine Evidence validation failed")
                bundle = component / "evidence" / "canonical_bundle.json"
                _validate_machine_assurance(bundle)
                result = {"schema_version": "1.0", "artifact_type": "integra.machine_evidence_result",
                    "status": "EVIDENCE_CREATED", "decision": "MACHINE_EVIDENCE_UNVERIFIED",
                    "verification_state": "machine_unverified", "automatic_acceptance": False,
                    "reviewer_id": None, "input_identity": identity,
                    "seminartext": {"commit_sha": PINNED_COMMIT, "origin": origin,
                        "transcript_revision_id": promoted["revision_id"], "alignment_run_id": aligned["alignment_run_id"],
                        "canonical_evidence_path": str(target / bundle.relative_to(stage)),
                        "canonical_evidence_sha256": _sha256(bundle)}}
                result["result_sha256"] = content_sha256(result)
                (stage / "result.json").write_bytes(canonical_json(result) + b"\n")
                if any(_sha256(path) != identity[name + "_sha256"] for name, path in paths.items()):
                    raise ValueError("machine Evidence inputs changed during processing")
                os.rename(stage, target)
        result_path = _inside(target / "result.json", root, "machine Evidence result")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if (result.get("input_identity") != identity or result.get("result_sha256") != content_sha256(
                {key: value for key, value in result.items() if key != "result_sha256"})):
            raise ValueError("persisted machine Evidence result changed")
        # ``result.json`` is content-addressed evidence and retains the original
        # absolute location as part of its signed payload.  Resolve that stored
        # reference against the current project before applying the narrower
        # target containment check; never rewrite the historical result.
        bundle = resolve_persisted_project_path(root, result["seminartext"]["canonical_evidence_path"],
                                                "machine Evidence bundle")
        bundle = _inside(bundle, target, "machine Evidence bundle")
        if _sha256(bundle) != result["seminartext"]["canonical_evidence_sha256"]:
            raise ValueError("persisted machine Evidence bundle changed")
        _validate_machine_assurance(bundle)
        if any(_sha256(path) != identity[name + "_sha256"] for name, path in paths.items()):
            raise ValueError("machine Evidence inputs changed during processing")
        return result | {"evidence_result_path": str(result_path), "canonical_evidence_path": str(bundle)}


def prepare_topic_review_input(project_dir: Path, *, source_id: str, canonical_evidence_path: str,
                               topics_path: str) -> dict[str, Any]:
    """Bind real SeminarText topic proposals to canonical evidence for review.

    This is a lossless contract adapter, not a topic generator and not a review
    decision.  It refuses any source result that is not explicitly marked
    ``REVIEW_REQUIRED``.
    """
    root = Path(project_dir).resolve(strict=True)
    evidence_path = _inside(Path(canonical_evidence_path), root, "Canonical Evidence")
    topics_file = _inside(Path(topics_path), root, "SeminarText topic drafts")
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        topic_output = json.loads(topics_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("topic or Evidence artifact is invalid JSON") from error
    if evidence.get("artifact_type") != "seminartext.canonical_evidence":
        raise ValueError("Canonical Evidence contract is unavailable")
    if topic_output.get("component") != "seminartext" or not isinstance(topic_output.get("topics"), list):
        raise ValueError("SeminarText topic output is unavailable")
    sources = evidence.get("sources"); revisions = evidence.get("transcript_revisions"); words = evidence.get("words")
    benchmark_segments = evidence.get("benchmark_segments")
    if not all(isinstance(value, list) for value in (sources, revisions, words, benchmark_segments)):
        raise ValueError("Canonical Evidence has no source Word Timeline")
    # The pinned Evidence contract contains canonical IDs, not registry IDs.
    canonical_id = "source_source_" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:24]
    source = next((item for item in sources if isinstance(item, dict) and item.get("id") == canonical_id), None)
    if source is None:
        raise ValueError("Canonical Evidence is not bound to this Integra source")
    canonical_source_id = source.get("id")
    revision = next((item for item in revisions if isinstance(item, dict) and item.get("source_id") == canonical_source_id), None)
    if not isinstance(revision, dict) or not isinstance(revision.get("id"), str):
        raise ValueError("Canonical Evidence has no reviewed transcript revision")
    timeline = sorted((item for item in words if isinstance(item, dict) and item.get("source_id") == canonical_source_id
                       and item.get("transcript_revision_id") == revision["id"]), key=lambda item: item.get("sequence", -1))
    if not timeline:
        raise ValueError("Canonical Evidence has no reviewed Word Timeline")
    project = evidence.get("project") if isinstance(evidence.get("project"), dict) else {}
    if not isinstance(project.get("id"), str) or not isinstance(project.get("title"), str):
        raise ValueError("Canonical Evidence has an invalid project")
    token = hashlib.sha256((source_id + _sha256(topics_file)).encode("utf-8")).hexdigest()[:20]
    seminar_id = f"seminar_{token}"
    words_by_id = {item.get("id"): item for item in timeline if isinstance(item.get("id"), str)}
    evidence_items: list[dict[str, Any]] = []
    draft_topics: list[dict[str, Any]] = []
    boundary_mappings: list[dict[str, Any]] = []
    for sequence, proposal in enumerate(topic_output["topics"]):
        if not isinstance(proposal, dict) or proposal.get("semantic_status") != "REVIEW_REQUIRED":
            raise ValueError("every SeminarText topic must remain REVIEW_REQUIRED")
        title = proposal.get("title")
        summary = proposal.get("summary", "")
        start = proposal.get("start_seconds"); end = proposal.get("end_seconds")
        if not isinstance(title, str) or not title.strip() or not isinstance(summary, str) or not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
            raise ValueError("SeminarText topic has no valid title, summary, or time range")
        selected = [item for item in timeline if isinstance(item.get("start_seconds"), (int, float))
                    and isinstance(item.get("end_seconds"), (int, float))
                    and item["end_seconds"] > start and item["start_seconds"] < end]
        if not selected:
            raise ValueError("SeminarText topic cannot be bound to exact reviewed words")
        aligned_first, aligned_last = selected[0], selected[-1]
        selected_segments = sorted((segment for segment in benchmark_segments if isinstance(segment, dict)
                                    and segment.get("transcript_revision_id") == revision["id"]
                                    and segment.get("word_start_id") in words_by_id
                                    and segment.get("word_end_id") in words_by_id
                                    and words_by_id[segment["word_end_id"]].get("sequence", -1) >= aligned_first.get("sequence", -1)
                                    and words_by_id[segment["word_start_id"]].get("sequence", -1) <= aligned_last.get("sequence", -1)),
                                   key=lambda segment: segment.get("sequence", -1))
        if not selected_segments:
            raise ValueError("SeminarText topic cannot be mapped to a complete BenchmarkSegment")
        first, last = words_by_id[selected_segments[0]["word_start_id"]], words_by_id[selected_segments[-1]["word_end_id"]]
        if not isinstance(first.get("id"), str) or not isinstance(last.get("id"), str):
            raise ValueError("Canonical Evidence Word Timeline has invalid IDs")
        expected = first.get("sequence")
        if not isinstance(expected, int):
            raise ValueError("Canonical Evidence Word Timeline has invalid sequences")
        for segment in selected_segments:
            segment_first, segment_last = words_by_id[segment["word_start_id"]], words_by_id[segment["word_end_id"]]
            if segment_first.get("sequence") != expected or not isinstance(segment_last.get("sequence"), int):
                raise ValueError("BenchmarkSegment mapping is not a complete contiguous source span")
            expected = segment_last["sequence"] + 1
        if expected != last.get("sequence", -2) + 1:
            raise ValueError("BenchmarkSegment mapping has an invalid final boundary")
        evidence_id = f"evidence_topic_{token}_{sequence:04d}"
        evidence_items.append({"id": evidence_id, "claim": "Source passage selected for human topic review.",
                               "source_id": canonical_source_id, "transcript_revision_id": revision["id"],
                               "word_start_id": first["id"], "word_end_id": last["id"]})
        draft_topics.append({"id": f"topic_draft_{token}_{sequence:04d}", "seminar_id": seminar_id,
                             "source_id": canonical_source_id, "transcript_revision_id": revision["id"],
                             "topic_set_id": f"topic_set_{token}", "sequence": sequence,
                             "word_start_id": first["id"], "word_end_id": last["id"],
                             "proposed_title": title.strip(), "proposed_summary": summary.strip(),
                             "evidence_refs": [evidence_id], "semantic_origin": "machine_assisted",
                             "lifecycle_status": "REVIEW_REQUIRED"})
        boundary_mappings.append({
            "topic_draft_id": f"topic_draft_{token}_{sequence:04d}",
            "mapping": "COMPLETE_BENCHMARK_SEGMENTS",
            "machine_topic": {"index": sequence, "start_seconds": start, "end_seconds": end,
                              "start_segment_id": proposal.get("start_segment_id"),
                              "evidence_start_id": proposal.get("evidence_start_id"),
                              "evidence_end_id": proposal.get("evidence_end_id")},
            "aligned_overlap": {"word_start_id": aligned_first["id"], "word_end_id": aligned_last["id"],
                                "word_start_sequence": aligned_first["sequence"], "word_end_sequence": aligned_last["sequence"]},
            "review_span": {"benchmark_segment_ids": [segment.get("id") for segment in selected_segments],
                            "word_start_id": first["id"], "word_end_id": last["id"],
                            "word_start_sequence": first["sequence"], "word_end_sequence": last["sequence"]},
        })
    if not draft_topics:
        raise ValueError("SeminarText produced no topics for review")
    drafts = {"schema_version": "1.0.0", "artifact_type": "seminartext.topic_drafts",
              "artifact_id": f"topic_drafts_{token}", "project": {"id": project["id"], "title": project["title"]},
              "seminar": {"id": seminar_id, "title": project["title"]},
              "generator": {"id": "generator_integra_seminartext_topics", "version": "1.0",
                            "configuration_sha256": content_sha256({"topic_output_sha256": _sha256(topics_file),
                                                                      "canonical_evidence_sha256": _sha256(evidence_path)})},
              "evidence": evidence_items, "topics": draft_topics}
    drafts_sha = content_sha256(drafts)
    directory = _review_root(root, source_id) / "topic-drafts"; directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{drafts_sha}.json"
    if path.exists() and (path.is_symlink() or path.read_bytes() != canonical_json(drafts) + b"\n"):
        raise ValueError("topic review artifact collision")
    if not path.exists():
        temporary = path.with_suffix(".tmp"); temporary.write_bytes(canonical_json(drafts) + b"\n"); os.replace(temporary, path)
    return {"status": "REVIEW_REQUIRED", "semantic_authority": "MACHINE_OUTPUT_REQUIRES_HUMAN_DECISION",
            "topic_drafts_path": str(path), "topic_drafts_sha256": drafts_sha, "topic_count": len(draft_topics),
            "automatic_acceptance": False, "boundary_mappings": boundary_mappings}
