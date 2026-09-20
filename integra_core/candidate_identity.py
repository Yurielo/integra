"""Immutable build-candidate and candidate-bound evidence contracts.

This module deliberately records runtime identity only.  It is not a release
or product-acceptance mechanism; WP2/WP3 own diagnostic and E2E conclusions.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA_VERSION = "1.0"
EVIDENCE_SCHEMA_VERSION = "1.0"
MANIFEST_NAME = "candidate-manifest.json"
_CANDIDATE_ID = re.compile(r"^candidate-v1-[0-9a-f]{64}$")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def tree_sha256(root: Path, *, exclude: set[str] | None = None) -> str:
    """Hash regular bundle files by stable relative path and file digest."""
    excluded = exclude or set()
    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"candidate tree must not contain a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in excluded or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        entries.append({"path": relative, "sha256": sha256_file(path)})
    return sha256_bytes(canonical_bytes(entries))


def candidate_id(identity: dict[str, Any]) -> str:
    return "candidate-v1-" + sha256_bytes(canonical_bytes(identity))


def manifest_path(resources_or_app: Path) -> Path:
    root = resources_or_app
    if root.name == "Integra.app":
        root = root / "Contents" / "Resources"
    return root / MANIFEST_NAME


def load_manifest(resources_or_app: Path) -> dict[str, Any]:
    path = manifest_path(resources_or_app)
    if path.is_symlink() or not path.is_file():
        raise ValueError("candidate manifest is unavailable")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("candidate manifest is invalid JSON") from error
    validate_manifest(value)
    return value


def validate_manifest(value: dict[str, Any]) -> None:
    if not isinstance(value, dict) or value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("candidate manifest schema is unsupported")
    identity = value.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("candidate manifest identity is missing")
    expected = candidate_id(identity)
    if value.get("candidate_id") != expected or not _CANDIDATE_ID.fullmatch(expected):
        raise ValueError("candidate manifest ID does not bind its identity")
    if value.get("identity_sha256") != expected.removeprefix("candidate-v1-"):
        raise ValueError("candidate manifest identity digest is invalid")
    bundle = value.get("bundle")
    if not isinstance(bundle, dict) or bundle.get("digest_algorithm") != "sha256-tree-excluding-candidate-manifest":
        raise ValueError("candidate manifest bundle digest contract is invalid")
    if not isinstance(bundle.get("digest"), str) or not re.fullmatch(r"[0-9a-f]{64}", bundle["digest"]):
        raise ValueError("candidate manifest bundle digest is invalid")


def validate_bundle(app: Path) -> dict[str, Any]:
    """Validate the embedded manifest against the built bundle's bytes."""
    resources = app / "Contents" / "Resources"
    manifest = load_manifest(resources)
    actual_digest = tree_sha256(app, exclude={"Contents/Resources/" + MANIFEST_NAME})
    if manifest["bundle"]["digest"] != actual_digest:
        raise ValueError("candidate manifest bundle digest differs from the app")
    components = manifest["identity"].get("components", {})
    seminar = resources / "runtime" / "seminartext"
    runtime = json.loads((seminar / "runtime.json").read_text(encoding="utf-8"))
    if runtime.get("commit_sha") != components.get("seminartext", {}).get("commit_sha"):
        raise ValueError("candidate SeminarText identity differs from runtime")
    if runtime.get("entrypoint_sha256") != sha256_file(seminar / "seminartext"):
        raise ValueError("candidate SeminarText CLI differs from runtime manifest")
    video = resources / "runtime" / "videotext"
    video_runtime = json.loads((video / "runtime.json").read_text(encoding="utf-8"))
    if video_runtime.get("worker_sha256") != sha256_file(video / "translation-worker"):
        raise ValueError("candidate VideoText worker differs from runtime manifest")
    book = resources / "runtime" / "booktext"
    book_runtime = json.loads((book / "runtime.json").read_text(encoding="utf-8"))
    if book_runtime.get("entrypoint_sha256") != sha256_file(book / "booktext.py"):
        raise ValueError("candidate BookText entrypoint differs from runtime manifest")
    word = json.loads((resources / "runtime" / "word-alignment" / "runtime.json").read_text(encoding="utf-8"))
    word_root = resources / "runtime" / "word-alignment"
    if word.get("weights_sha256") != sha256_file(word_root / "model" / "pytorch_model.bin"):
        raise ValueError("candidate Word Alignment weights differ from runtime manifest")
    execution = manifest["identity"].get("execution", {})
    if execution.get("word_alignment", {}).get("site_packages_tree_sha256") != tree_sha256(word_root / "site-packages"):
        raise ValueError("candidate Word Alignment packages differ from manifest")
    for key in ("gui_python", "word_alignment_python"):
        executable = execution.get(key, {})
        path = Path(str(executable.get("path", "")))
        if not path.is_file() or sha256_file(path) != executable.get("sha256"):
            raise ValueError(f"candidate {key} differs from manifest")
    return manifest


def sanitized_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    """Keep execution-relevant values while avoiding credentials and full PATH."""
    source = environment or os.environ
    keys = ("PYTHONPATH", "HF_HUB_OFFLINE", "INTEGRA_CANDIDATE_ID", "INTEGRA_RUN_ID", "INTEGRA_STAGE_ID")
    return {key: source[key] for key in keys if key in source}


def write_evidence(path: Path, *, candidate: dict[str, Any] | None, gate_name: str,
                   result: str, timestamp: str, artifact_locations: list[str],
                   details: dict[str, Any]) -> dict[str, Any]:
    """Persist a bounded candidate-bound gate record for later WP2/WP3 gates."""
    if result not in {"PASS", "FAIL", "BLOCKED"}:
        raise ValueError("candidate evidence result is invalid")
    if not gate_name or len(gate_name) > 128:
        raise ValueError("candidate evidence gate name is invalid")
    value: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "artifact_type": "integra.candidate_evidence",
        "candidate_id": candidate["candidate_id"] if candidate else "SOURCE_UNBOUND",
        "manifest_identity_sha256": candidate["identity_sha256"] if candidate else None,
        "bundle_digest": candidate["bundle"]["digest"] if candidate else None,
        "gate_name": gate_name,
        "timestamp": timestamp,
        "result": result,
        "artifact_locations": artifact_locations,
        "details": details,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_bytes(canonical_bytes(value) + b"\n")
    os.replace(temporary, path)
    return value
