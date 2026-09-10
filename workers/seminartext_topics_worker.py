#!/usr/bin/env python3
"""Invoke the pinned SeminarText Topic Engine functions without altering it.

The pinned CLI currently raises after otherwise successful inference because its
QA report references a local variable that is not set. This adapter composes the
same boundary, label and materialization functions and records that entrypoint.
It never promotes a machine Topic beyond REVIEW_REQUIRED.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType


def load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("pinned_seminartext_topics", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load pinned Topic Engine: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_topics(module: ModuleType, srt: Path, model: str) -> dict:
    items = module.parse_srt(srt)
    windows = module.make_windows(items)
    rows: list[dict] = []
    window_reports: list[dict] = []
    for index, window in enumerate(windows, 1):
        boundaries = module.analyze_window_boundaries(window, detail="low", model=model)
        window_rows = []
        for offset, start_id in enumerate(boundaries):
            next_id = boundaries[offset + 1] if offset + 1 < len(boundaries) else None
            start = next(i for i, item in enumerate(window) if item["id"] == start_id)
            end = next(
                (i for i, item in enumerate(window) if item["id"] == next_id),
                len(window),
            )
            segment_range = window[start:end]
            result = module.run_ollama_topic_label(
                model,
                module.topic_range_prompt(segment_range),
                segment_range[0]["id"],
                segment_range[-1]["id"],
            )
            result["semantic_status"] = "REVIEW_REQUIRED"
            window_rows.append(result)
            rows.append(result)
        window_reports.append(
            {"window": index, "boundaries": boundaries, "rows": window_rows}
        )
    deduplicated: dict[int, dict] = {}
    for row in rows:
        deduplicated.setdefault(row["start_id"], row)
    candidates = [deduplicated[key] for key in sorted(deduplicated)]
    topics = module.make_topics(items, candidates)
    for topic in topics:
        topic["semantic_status"] = "REVIEW_REQUIRED"
    return {
        "schema_version": "1.0",
        "component": "seminartext",
        "component_entrypoint": "seminartext_topics module function composition",
        "model": model,
        "topics": topics,
        "windows": window_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gemma3:4b")
    args = parser.parse_args()
    module_path = args.checkout.resolve() / "seminartext_modules/seminartext_topics.py"
    if args.checkout.resolve() not in module_path.parents or not module_path.is_file():
        raise RuntimeError("pinned SeminarText Topic Engine entrypoint is missing")
    payload = run_topics(load_module(module_path), args.srt, args.model)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"output": str(args.output), "topic_count": len(payload["topics"])},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
