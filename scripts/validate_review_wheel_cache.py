#!/usr/bin/env python3
"""Fail-closed validation of the governed offline review wheel cache."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REQ_LINE = re.compile(r"^([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:([0-9a-f]{64})$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def requirements(path: Path) -> dict[str, dict[str, str]]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = REQ_LINE.fullmatch(line)
        if not match:
            raise ValueError(f"requirements line is not exact and hash-locked: {line}")
        name, version, digest = match.groups()
        key = name.lower().replace("_", "-")
        if key in result:
            raise ValueError(f"duplicate requirement: {name}")
        result[key] = {"name": name, "version": version, "sha256": digest}
    if not result:
        raise ValueError("review runtime requirements are empty")
    return result


def validate(cache: Path, requirements_path: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0" or manifest.get("artifact_type") != "integra.review_runtime_wheel_cache":
        raise ValueError("review wheel cache manifest schema is unsupported")
    if manifest["requirements"]["path"] != "scripts/review-runtime-requirements.txt":
        raise ValueError("review requirements path is not canonical")
    if manifest["requirements"]["sha256"] != sha256(requirements_path):
        raise ValueError("review requirements bytes differ from manifest")
    expected = requirements(requirements_path)
    actual = {}
    for wheel in sorted(cache.iterdir()):
        if not wheel.is_file() or wheel.is_symlink():
            raise ValueError(f"cache contains a non-regular entry: {wheel.name}")
        match = re.match(r"^([A-Za-z0-9_.-]+)-([0-9][A-Za-z0-9_.+-]*)-[^-]+-[^-]+-[^-]+\.whl$", wheel.name)
        if not match:
            raise ValueError(f"cache contains a non-wheel or unsupported filename: {wheel.name}")
        key = match.group(1).lower().replace("_", "-")
        if key in actual:
            raise ValueError(f"cache contains duplicate wheel family: {key}")
        actual[key] = {"name": key, "version": match.group(2), "filename": wheel.name, "sha256": sha256(wheel)}
    if set(actual) != set(expected):
        raise ValueError(f"cache package set differs: expected {sorted(expected)}, actual {sorted(actual)}")
    for key, wanted in expected.items():
        found = actual[key]
        if found["version"] != wanted["version"] or found["sha256"] != wanted["sha256"]:
            raise ValueError(f"cache hash/version differs for {key}")
    if sorted(manifest.get("wheels", []), key=lambda item: item["name"]) != sorted(actual.values(), key=lambda item: item["name"]):
        raise ValueError("manifest wheel inventory differs from cache bytes")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cache", type=Path)
    parser.add_argument("--requirements", type=Path, default=ROOT / "scripts/review-runtime-requirements.txt")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    value = validate(args.cache, args.requirements, args.manifest)
    print(json.dumps({"state": "PASS", "artifact_type": value["artifact_type"], "wheel_count": len(value["wheels"])}, sort_keys=True))


if __name__ == "__main__":
    main()
