#!/usr/bin/env python3
"""Run the R5 normalized contract replay against pinned source checkouts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integra_core.benchmark import canonical_bytes, sha256_file  # noqa: E402


def git_value(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def verify_source(root: Path, baseline: dict[str, Any]) -> dict[str, str]:
    if git_value(root, "rev-parse", "HEAD") != baseline["commit_sha"]:
        raise SystemExit(f"{baseline['id']}: source HEAD differs from pinned baseline")
    if git_value(root, "rev-parse", "HEAD^{tree}") != baseline["tree_sha"]:
        raise SystemExit(f"{baseline['id']}: source tree differs from pinned baseline")
    if git_value(root, "status", "--porcelain", "--untracked-files=all"):
        raise SystemExit(f"{baseline['id']}: source checkout must be clean")
    return {
        "commit_sha": baseline["commit_sha"],
        "tree_sha": baseline["tree_sha"],
        "status": "CLEAN",
    }


def render_argv(argv: list[str], python_executable: Path) -> list[str]:
    return [str(python_executable) if token == "{python}" else token for token in argv]


def run_command(
    source_root: Path,
    output_root: Path,
    command: dict[str, Any],
    repetition: int,
    python_executable: Path,
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTEST_ADDOPTS"] = "-p no:cacheprovider"
    temporary = output_root / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    environment["TMPDIR"] = str(temporary)
    started = time.monotonic()
    completed = subprocess.run(
        render_argv(command["argv"], python_executable),
        cwd=source_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=command["timeout_seconds"],
        check=False,
    )
    elapsed_ms = round((time.monotonic() - started) * 1000)
    marker = command["success_marker"].encode("utf-8")
    passed = completed.returncode == 0 and marker in completed.stdout + completed.stderr
    return {
        "repetition": repetition,
        "command_id": command["id"],
        "exit_code": completed.returncode,
        "elapsed_ms": elapsed_ms,
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "status": "PASS" if passed else "FAIL",
    }


def input_evidence(source_root: Path, paths: list[str]) -> list[dict[str, str]]:
    evidence = []
    for relative in paths:
        path = (source_root / relative).resolve()
        if source_root.resolve() not in path.parents or not path.is_file():
            raise SystemExit(f"invalid benchmark evidence path: {relative}")
        evidence.append({"path": relative, "sha256": sha256_file(path)})
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seminartext-root", type=Path, required=True)
    parser.add_argument("--videotext-root", type=Path, required=True)
    parser.add_argument("--seminartext-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--resume-from", type=Path)
    args = parser.parse_args()
    if args.repetitions < 2:
        raise SystemExit("R5 requires at least two replay repetitions")
    if git_value(ROOT, "status", "--porcelain", "--untracked-files=all"):
        raise SystemExit("Integra checkout must be clean for an identity-bearing R5 run")

    fixture_path = ROOT / "tests/fixtures/capability_benchmark_v1/manifest.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    baselines = json.loads(
        (ROOT / "state/component_baselines_v1.json").read_text(encoding="utf-8")
    )
    baseline_by_id = {item["id"]: item for item in baselines["components"]}
    roots = {
        "seminartext": args.seminartext_root.resolve(),
        "videotext": args.videotext_root.resolve(),
    }
    source_before = {
        component_id: verify_source(roots[component_id], baseline)
        for component_id, baseline in baseline_by_id.items()
    }
    output = args.output.resolve()
    if any(output == root or root in output.parents for root in roots.values()):
        raise SystemExit("benchmark output must be outside pinned source checkouts")
    output.parent.mkdir(parents=True, exist_ok=True)
    work_root = output.parent / "benchmark-work"
    if any(work_root == root or root in work_root.parents for root in roots.values()):
        raise SystemExit("benchmark work directory must be outside pinned source checkouts")
    reusable: dict[tuple[str, str], dict[str, Any]] = {}
    if args.resume_from and args.resume_from.is_file():
        retained = json.loads(args.resume_from.read_text(encoding="utf-8"))
        for retained_capability in retained.get("capabilities", []):
            for retained_candidate in retained_capability.get("candidates", []):
                reusable[(retained_capability["id"], retained_candidate["component_id"])] = (
                    retained_candidate
                )

    observations = []
    for capability in fixture["capabilities"]:
        candidate_results = []
        for candidate in capability["candidates"]:
            component_id = candidate["component_id"]
            if candidate["qualification"] == "NOT_QUALIFIED":
                candidate_results.append(
                    {
                        "component_id": component_id,
                        "status": "NOT_QUALIFIED",
                        "reason": candidate["reason"],
                        "evidence_inputs": input_evidence(
                            roots[component_id], candidate["evidence_paths"]
                        ),
                        "runs": [],
                    }
                )
                continue
            evidence = input_evidence(roots[component_id], candidate["evidence_paths"])
            retained_candidate = reusable.get((capability["id"], component_id))
            expected_run_count = args.repetitions * len(candidate["commands"])
            if (
                retained_candidate
                and retained_candidate.get("status") == "PASS"
                and retained_candidate.get("evidence_inputs") == evidence
                and len(retained_candidate.get("runs", [])) == expected_run_count
                and all(
                    run.get("status") == "PASS"
                    for run in retained_candidate.get("runs", [])
                )
            ):
                candidate_results.append(retained_candidate)
                continue
            runs = []
            for repetition in range(1, args.repetitions + 1):
                for command in candidate["commands"]:
                    runs.append(
                        run_command(
                            roots[component_id],
                            work_root / component_id,
                            command,
                            repetition,
                            (
                                args.seminartext_python.absolute()
                                if component_id == "seminartext"
                                else Path(sys.executable)
                            ),
                        )
                    )
            status = "PASS" if all(run["status"] == "PASS" for run in runs) else "FAIL"
            candidate_results.append(
                {
                    "component_id": component_id,
                    "status": status,
                    "evidence_inputs": evidence,
                    "runs": runs,
                }
            )
            if status != "PASS":
                output.write_bytes(
                    canonical_bytes(
                        {
                            "capabilities": observations
                            + [{"id": capability["id"], "candidates": candidate_results}]
                        }
                    )
                )
                return 1
        observations.append({"id": capability["id"], "candidates": candidate_results})

    source_after = {
        component_id: verify_source(roots[component_id], baseline)
        for component_id, baseline in baseline_by_id.items()
    }
    result = {
        "schema_version": "1.0",
        "verified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "controller": {
            "repository": "Yurielo/integra",
            "commit_sha": git_value(ROOT, "rev-parse", "HEAD"),
            "tree_sha": git_value(ROOT, "rev-parse", "HEAD^{tree}"),
        },
        "environment": {
            "operating_system": platform.platform(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
        },
        "fixture_manifest": {
            "path": "tests/fixtures/capability_benchmark_v1/manifest.json",
            "sha256": sha256_file(fixture_path),
        },
        "source_before": source_before,
        "source_after": source_after,
        "capabilities": observations,
        "status": "PASS",
    }
    output.write_bytes(canonical_bytes(result))
    print(f"R5_CAPABILITY_BENCHMARK: PASS ({len(observations)} capabilities)")
    print(f"RESULT: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
