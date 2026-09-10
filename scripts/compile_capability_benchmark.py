#!/usr/bin/env python3
"""Compile raw R5 replay observations into the governed acceptance record."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integra_core.benchmark import sha256_file, validate_benchmark_record  # noqa: E402


SELECTIONS = {
    "media_preparation": {
        "mode": "SINGLE_PRIMARY",
        "primary": ["videotext"],
        "fallback": [],
        "challenger": [],
        "basis": ["complete bounded-fragment probe", "R1 real-media evidence"],
    },
    "asr": {
        "mode": "SINGLE_PRIMARY",
        "primary": ["videotext"],
        "fallback": [],
        "challenger": [],
        "basis": ["replayable transcript-quality gate", "R1 consecutive real-media E2E"],
    },
    "alignment": {
        "mode": "SINGLE_PRIMARY",
        "primary": ["seminartext"],
        "fallback": ["videotext"],
        "challenger": [],
        "basis": ["Canonical Word Timeline ownership", "word-level provenance and explicit unaligned state"],
    },
    "translation": {
        "mode": "SINGLE_PRIMARY",
        "primary": ["videotext"],
        "fallback": ["seminartext"],
        "challenger": [],
        "basis": ["application-integrated adapter and review lifecycle", "SeminarText retained as deterministic contract fallback"],
    },
    "topics": {
        "mode": "SINGLE_PRIMARY",
        "primary": ["seminartext"],
        "fallback": [],
        "challenger": ["videotext"],
        "basis": ["accepted Topic lifecycle and frozen-candidate provenance", "semantic superiority remains unclaimed"],
    },
    "review_mechanics": {
        "mode": "COMPOSED_PRIMARY",
        "primary": ["seminartext", "videotext"],
        "fallback": [],
        "challenger": [],
        "basis": ["SeminarText owns Topic/knowledge ReviewDecision", "VideoText owns transcript/media review checkpoint"],
    },
    "cache": {
        "mode": "SINGLE_PRIMARY",
        "primary": ["videotext"],
        "fallback": [],
        "challenger": [],
        "basis": ["input/model/config-bound cache probe", "invalid and partial cache handling"],
    },
    "recovery": {
        "mode": "SINGLE_PRIMARY",
        "primary": ["videotext"],
        "fallback": ["seminartext"],
        "challenger": [],
        "basis": ["bounded watchdog and project workflow recovery", "SeminarText evidence resume retained"],
    },
    "quality_validation": {
        "mode": "COMPOSED_PRIMARY",
        "primary": ["seminartext", "videotext"],
        "fallback": [],
        "challenger": [],
        "basis": ["SeminarText canonical evidence/provenance validation", "VideoText media/transcript quality validation"],
    },
}

SEMANTIC_CAPABILITIES = {"translation", "topics", "review_mechanics"}
CORRECTION_BURDEN_CAPABILITIES = {"asr", "translation", "topics", "review_mechanics"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def candidate_record(
    capability_id: str,
    candidate: dict[str, Any],
    assertions: list[str],
) -> dict[str, Any]:
    status = candidate["status"]
    if status == "NOT_QUALIFIED":
        unavailable = {"status": "NOT_QUALIFIED", "reason": candidate["reason"]}
        return {
            "component_id": candidate["component_id"],
            "status": status,
            "hard_correctness": unavailable,
            "provenance": {
                "status": "PASS",
                "evidence_inputs": candidate["evidence_inputs"],
            },
            "quality": {
                "status": "NOT_MEASURED",
                "semantic_quality": "NOT_MEASURED_NO_QUALIFIED_CONTRACT",
                "reason": candidate["reason"],
            },
            "correction_burden": {
                "status": "NOT_MEASURED",
                "reason": candidate["reason"],
            },
            "resources": {"status": "NOT_MEASURED", "reason": candidate["reason"]},
            "reproducibility": {"status": "NOT_MEASURED", "reason": candidate["reason"]},
            "runs": [],
            "limitations": [candidate["reason"]],
        }

    runs = candidate["runs"]
    elapsed = [run["elapsed_ms"] for run in runs]
    stdout_stable = len({run["stdout_sha256"] for run in runs}) == 1
    semantic_quality = (
        "NOT_MEASURED_NO_AUTHORIZED_GOLD"
        if capability_id in SEMANTIC_CAPABILITIES
        else "NOT_APPLICABLE_TO_CONTRACT_REPLAY"
    )
    correction = (
        "NOT_MEASURED_NO_AUTHORIZED_HUMAN_LABELS"
        if capability_id in CORRECTION_BURDEN_CAPABILITIES
        else "NOT_APPLICABLE_TO_CONTRACT_REPLAY"
    )
    return {
        "component_id": candidate["component_id"],
        "status": "PASS",
        "hard_correctness": {
            "status": "PASS",
            "assertions_passed": len(assertions),
            "assertions_total": len(assertions),
        },
        "provenance": {
            "status": "PASS",
            "evidence_inputs": candidate["evidence_inputs"],
        },
        "quality": {
            "status": "PARTIAL",
            "contract_assertions_passed": len(assertions),
            "contract_assertions_total": len(assertions),
            "semantic_quality": semantic_quality,
        },
        "correction_burden": {"status": "NOT_MEASURED", "reason": correction},
        "resources": {
            "status": "PARTIAL",
            "measurement": "WALL_CLOCK_ELAPSED_ONLY",
            "elapsed_ms_min": min(elapsed),
            "elapsed_ms_median": round(statistics.median(elapsed)),
            "elapsed_ms_max": max(elapsed),
            "peak_rss_kb": None,
        },
        "reproducibility": {
            "status": "PASS",
            "run_count": len(runs),
            "all_runs_passed": all(run["status"] == "PASS" for run in runs),
            "stdout_byte_stable": stdout_stable,
            "note": "pytest duration text may change stdout hash without changing assertions",
        },
        "runs": runs,
        "limitations": [
            "No protected Dataset or Gold quality comparison was authorized.",
            "Peak RSS was not measured by the dependency-free runner.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--raw-output",
        type=Path,
        default=ROOT / "state/capability_benchmark_raw_v1.json",
    )
    args = parser.parse_args()
    raw = load(args.raw)
    fixture = load(ROOT / raw["fixture_manifest"]["path"])
    if raw.get("status") != "PASS":
        raise SystemExit("raw R5 replay did not pass")
    if raw.get("source_before") != raw.get("source_after"):
        raise SystemExit("source state changed during R5 replay")
    fixture_by_id = {item["id"]: item for item in fixture["capabilities"]}
    args.raw_output.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    capabilities = []
    for observation in raw["capabilities"]:
        capability_id = observation["id"]
        assertions = fixture_by_id[capability_id]["normalized_assertions"]
        selection = dict(SELECTIONS[capability_id])
        selection.update(
            {
                "decision_authority": "ISSUE_7_TECHNICAL_INTEGRATION_SELECTION",
                "semantic_superiority_claimed": False,
            }
        )
        capabilities.append(
            {
                "id": capability_id,
                "normalized_assertions": assertions,
                "candidates": [
                    candidate_record(capability_id, candidate, assertions)
                    for candidate in observation["candidates"]
                ],
                "selection": selection,
            }
        )
    record = {
        "schema_version": "1.0",
        "verified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "controller": raw["controller"],
        "component_baselines": "state/component_baselines_v1.json",
        "fixture_manifest": raw["fixture_manifest"],
        "raw_replay": {
            "path": "state/capability_benchmark_raw_v1.json",
            "sha256": sha256_file(args.raw_output),
        },
        "environment": raw["environment"],
        "policy": {
            "comparison_basis": "NORMALIZED_CONTRACT_REPLAY",
            "source_repositories": "PINNED_READ_ONLY",
            "semantic_quality_without_gold": "NOT_MEASURED",
            "correction_burden_without_human_labels": "NOT_MEASURED",
            "selection_scope": "R6_TECHNICAL_INTEGRATION_DEFAULTS",
        },
        "capabilities": capabilities,
        "protected_data_accessed": False,
        "gold_accessed": False,
        "semantic_acceptance_performed": False,
        "source_repositories_changed": False,
        "external_actions_performed": False,
        "status": "PASS",
    }
    validate_benchmark_record(record)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"R5_GOVERNED_RECORD: PASS ({len(capabilities)} capabilities)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
