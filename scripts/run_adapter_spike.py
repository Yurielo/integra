#!/usr/bin/env python3
"""Run one bounded read-only R4 capability through the R3 local contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integra_core.adapter import CapabilitySpec, LocalComponentAdapter  # noqa: E402
from integra_core.identity import derive_imported_id  # noqa: E402
from integra_core.protocol import PROTOCOL_VERSION, canonical_json, content_sha256  # noqa: E402


COMPONENTS = {
    "seminartext": {
        "capability": "seminartext.canonical_evidence_validate",
        "input": "tests/fixtures/canonical_evidence_v1/valid_bundle.json",
        "input_kind": "canonical_evidence",
        "input_schema": "canonical_evidence_v1",
        "command": (
            sys.executable,
            "schemas/validate_canonical_evidence_v1.py",
            "{input0}",
        ),
        "success_marker": ": VALID",
        "runtime_kind": "python",
    },
    "videotext": {
        "capability": "videotext.project_schema_probe",
        "input": "Tests/Fixtures/Baseline/legacy_manifest_v3.json",
        "input_kind": "legacy_project_manifest",
        "input_schema": "project_schema_v3",
        "command": ("bash", "scripts/test_project_schema.sh"),
        "success_marker": "PROJECT_SCHEMA_PROBE_PASS",
        "runtime_kind": "swift",
    },
}


def git_value(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def runtime_version(kind: str) -> str:
    if kind == "python":
        return platform.python_version()
    result = subprocess.run(
        ["swiftc", "--version"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.stdout.splitlines()[0].strip()


def make_message(
    controller: dict,
    message_type: str,
    correlation_id: str,
    discriminator: str,
    payload: dict,
) -> dict:
    fingerprint = content_sha256(
        {
            "correlation_id": correlation_id,
            "discriminator": discriminator,
            "payload": payload,
        }
    )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "message_id": derive_imported_id("message", "integra", discriminator, fingerprint),
        "correlation_id": correlation_id,
        "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "type": message_type,
        "payload": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=sorted(COMPONENTS), required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timeout-ms", type=int, default=300000)
    args = parser.parse_args()

    if git_value(ROOT, "status", "--porcelain", "--untracked-files=all"):
        raise SystemExit("Integra checkout must be clean for an identity-bearing R4 run")
    manifest = json.loads(
        (ROOT / "state" / "component_baselines_v1.json").read_text(encoding="utf-8")
    )
    baseline = next(item for item in manifest["components"] if item["id"] == args.component)
    configuration = COMPONENTS[args.component]
    identity = {
        "component_id": baseline["id"],
        "repository": baseline["repository"],
        "commit_sha": baseline["commit_sha"],
        "tree_sha": baseline["tree_sha"],
        "version": baseline["version"],
        "contracts": [item["id"] for item in baseline["supported_contracts"]],
        "runtime": {
            "kind": configuration["runtime_kind"],
            "version": runtime_version(configuration["runtime_kind"]),
            "architecture": platform.machine(),
        },
    }
    controller = {
        "component_id": "integra_control_plane",
        "repository": "Yurielo/integra",
        "commit_sha": git_value(ROOT, "rev-parse", "HEAD"),
        "tree_sha": git_value(ROOT, "rev-parse", "HEAD^{tree}"),
        "version": "0.1.0",
        "contracts": ["worker_protocol_v1", "adapter_probe_report_v1"],
        "runtime": {
            "kind": "python",
            "version": platform.python_version(),
            "architecture": platform.machine(),
        },
    }
    capability = CapabilitySpec(
        id=configuration["capability"],
        version="1.0",
        input_schema_ids=(configuration["input_schema"],),
        output_schema_ids=("adapter_probe_report_v1",),
        supports_resume=False,
        command=configuration["command"],
        success_stdout_marker=configuration["success_marker"],
    )
    adapter = LocalComponentAdapter(
        identity=identity,
        source_root=args.source_root,
        output_root=args.output_root,
        capabilities=(capability,),
    )
    adapter.verify_source()

    source_root = args.source_root.resolve()
    input_path = (source_root / configuration["input"]).resolve()
    if source_root not in input_path.parents or not input_path.is_file():
        raise SystemExit("R4 input must be a regular file inside the pinned source checkout")
    input_bytes = input_path.read_bytes()
    input_hash = hashlib.sha256(input_bytes).hexdigest()
    operation_id = derive_imported_id(
        "operation", args.component, capability.id, input_hash
    )
    correlation_id = derive_imported_id(
        "session", args.component, "r4-adapter-spike", input_hash
    )
    handshake = make_message(
        controller,
        "HANDSHAKE_REQUEST",
        correlation_id,
        "handshake-request",
        {
            "supported_protocol_versions": [PROTOCOL_VERSION],
            "requested_capabilities": [capability.id],
            "controller": controller,
        },
    )
    handshake_response = adapter.handshake(handshake)
    artifact = {
        "artifact_id": derive_imported_id(
            "artifact", args.component, configuration["input"], input_hash
        ),
        "kind": configuration["input_kind"],
        "schema_id": configuration["input_schema"],
        "schema_version": "1.0",
        "content_sha256": input_hash,
        "size_bytes": len(input_bytes),
        "storage_scope": "SOURCE_READ_ONLY",
        "relative_path": configuration["input"],
        "origin": identity,
        "provenance": {"parent_artifact_ids": [], "operation_id": operation_id},
    }
    job_payload = {
        "job_id": derive_imported_id("job", args.component, capability.id, input_hash),
        "operation_id": operation_id,
        "idempotency_key": content_sha256(
            {
                "component": args.component,
                "capability": capability.id,
                "input_hash": input_hash,
            }
        ),
        "capability": capability.id,
        "timeout_ms": args.timeout_ms,
        "inputs": [artifact],
    }
    job = make_message(
        controller, "JOB_REQUEST", correlation_id, "job-request", job_payload
    )
    events = adapter.invoke(job)
    for message in (handshake, handshake_response, job, *events):
        print(canonical_json(message).decode("utf-8"))
    return 0 if events[-1]["type"] == "RESULT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
