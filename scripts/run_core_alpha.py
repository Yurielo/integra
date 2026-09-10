#!/usr/bin/env python3
"""Run the deterministic R6 Core Alpha contract replay on one local video."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integra_core.core_alpha import CoreAlphaPipeline, ReplayStageWorker  # noqa: E402


def git_value(*arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument(
        "--replay-fixture",
        type=Path,
        default=ROOT / "tests/fixtures/core_alpha_v1/worker_outputs.json",
    )
    parser.add_argument("--resume-checkpoint", type=Path)
    args = parser.parse_args()

    controller = {
        "component_id": "integra_control_plane",
        "repository": "Yurielo/integra",
        "commit_sha": git_value("rev-parse", "HEAD"),
        "tree_sha": git_value("rev-parse", "HEAD^{tree}"),
        "version": "0.1.0-alpha",
        "contracts": ["worker_protocol_v1", "core_alpha_manifest_v1"],
        "runtime": {
            "kind": "python",
            "version": platform.python_version(),
            "architecture": platform.machine(),
        },
    }
    pipeline = CoreAlphaPipeline(
        repository_root=ROOT,
        store_root=args.store,
        controller_identity=controller,
        worker=ReplayStageWorker.from_path(args.replay_fixture),
    )
    result = pipeline.run(args.source, resume_checkpoint=args.resume_checkpoint)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "SUCCEEDED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
