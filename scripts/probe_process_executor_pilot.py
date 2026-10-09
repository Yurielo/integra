#!/usr/bin/env python3
"""Execute the isolated pilot from one existing Candidate, without a build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_execution_guard import require_execution_path

CURRENT_ID = "candidate-v1-65bf72d1262146c9137aca433b51ae3974d98bc4c8ed37042db13b46e0318a1d"


def size(root):
    return sum(path.stat().st_size for path in root.rglob("*")
               if path.is_file() and not path.is_symlink()
               and "__pycache__" not in path.parts and path.suffix != ".pyc")


def runtime_inventory(resources):
    runtime = resources / "runtime"
    sizes = {path.name: size(path) for path in sorted(runtime.iterdir()) if path.is_dir()}
    binaries = {}
    for path in runtime.rglob("*"):
        if (path.is_file() and not path.is_symlink()
                and (path.suffix in {".so", ".dylib"} or path.name in {"translation-worker", "visionocr"})):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            binaries.setdefault(digest, []).append(str(path.relative_to(resources)))
    return {"component_logical_bytes": sizes,
            "duplicate_binary_groups": {key: paths for key, paths in binaries.items() if len(paths) > 1},
            "binary_files_inspected": sum(len(paths) for paths in binaries.values()),
            "method": "sha256 of regular .so/.dylib and named provider executables; not dynamic-loader proof",
            "pilot_additional_worker_count": 0}


def verify_source(root, identity):
    for field, revision in (("commit_sha", "HEAD"), ("tree_sha", "HEAD^{tree}")):
        actual = subprocess.run(["git", "-C", str(root), "rev-parse", revision],
                                capture_output=True, text=True, check=True).stdout.strip()
        if actual != identity[field]:
            raise SystemExit("Source repository does not match Candidate: " + field)
    if subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                      capture_output=True, check=True).stdout:
        raise SystemExit("Source checkout must remain clean for proof")


def verify_baseline(baseline, active):
    if (baseline["candidate_id"] != CURRENT_ID
            or baseline["bundle"]["digest"] != active["candidate"]["bundle_digest"]
            or baseline["identity_sha256"] != active["candidate"]["identity_sha256"]):
        raise SystemExit("Comparison bundle is not exact CURRENT")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-app", type=Path)
    args = parser.parse_args()
    app = args.app.resolve(strict=True)
    require_execution_path(app)
    require_execution_path(args.output)
    resources = app / "Contents/Resources"
    sys.path.insert(0, str(resources))
    from integra_core.candidate_identity import validate_bundle, sha256_file
    from integra_core.process_executor_pilot import execute, CAPABILITY
    from integra_core import videotext_subtitles
    import integra_core.process_executor_pilot as implementation
    if Path(implementation.__file__).resolve().parent != resources / "integra_core":
        raise SystemExit("Pilot must be imported from exact Candidate")
    manifest = validate_bundle(app)
    if manifest["identity"]["source"]["dirty"]:
        raise SystemExit("Candidate source must be clean")
    source_identity = manifest["identity"]["source"]
    verify_source(args.source_root, source_identity)
    args.output.mkdir(parents=False, exist_ok=False)
    root = args.output.resolve()
    source = root / "synthetic-transcript.srt"
    original = ("00:00:00,125 --> 00:00:02,750\r\nПервый фрагмент.\r\nSecond line\r\n\r\n"
                "00:05:00,000 --> 00:05:01,250\r\nВторой фрагмент.\r\n").encode()
    source.write_bytes(original)
    request = {"schema_version": "1.0", "capability_id": CAPABILITY,
               "project_id": "pilot-project", "run_id": "pilot-run",
               "source": {"source_id": "synthetic-source", "revision": "1"},
               "input": {"artifact_id": "synthetic-transcript", "format": "srt",
                         "sha256": hashlib.sha256(original).hexdigest()},
               "options": {"media_duration_ms": 301250}}
    expected = ("1\n00:00:00,125 --> 00:00:02,750\nПервый фрагмент.\nSecond line\n\n"
                "2\n00:05:00,000 --> 00:05:01,250\nВторой фрагмент.\n").encode()
    runs = [execute(request, source, resources=resources) for _ in range(2)]
    for run in runs:
        if run["result"]["status"] != "COMPLETED":
            raise SystemExit(json.dumps(run["result"], ensure_ascii=False))
        if (Path(run["attempt_path"]) / "published/transcript.srt").read_bytes() != expected:
            raise SystemExit("Independent expected bytes differ")
    if (runs[0]["attempt_path"] == runs[1]["attempt_path"]
            or runs[0]["result"]["request_sha256"] != runs[1]["result"]["request_sha256"]):
        raise SystemExit("Attempt/request identity differs")
    os.environ["INTEGRA_VIDEOTEXT_SUBTITLE_WORKER"] = str(resources / "runtime/videotext/translation-worker")
    videotext_subtitles.normalize(source, root / "existing-adapter.srt")
    if (root / "existing-adapter.srt").read_bytes() != expected or source.read_bytes() != original:
        raise SystemExit("Differential parity or input preservation failed")
    failure = execute({**request, "options": {"media_duration_ms": 301249}}, source, resources=resources)
    if failure["result"]["status"] != "FAILED" or failure["result"]["artifacts"]:
        raise SystemExit("Strict bound did not fail without artifacts")
    current_path = args.source_root / "state/current_product_baseline_v2.json"
    current = json.loads(current_path.read_bytes())
    active = next(item for item in current["records"] if item["baseline_id"] == current["current_id"])
    canonical_routes = ["integra_core/user_media.py", "integra_core/asr_reuse.py",
        "integra_core/application_runtime.py", "integra_core/capabilities.py",
        "integra_core/seminartext_asr_runtime.py", "integra_core/seminartext_runtime.py",
        "integra_core/seminartext_topic_review_runtime.py", "integra_core/word_timeline_runtime.py",
        "integra_core/videotext_subtitles.py", "integra_core/videotext_runtime.py",
        "integra_core/shutdown_runtime.py", "macos/IntegraApp.swift", "macos/Resources/bridge.py",
        "scripts/build_macos_app.sh", "scripts/build_videotext_worker.sh"]
    unchanged = {}
    for relative in canonical_routes:
        previous = subprocess.run(["git", "-C", str(args.source_root), "show",
            active["main"]["commit_sha"] + ":" + relative], capture_output=True, check=True).stdout
        present = subprocess.run(["git", "-C", str(args.source_root), "show",
            source_identity["commit_sha"] + ":" + relative], capture_output=True, check=True).stdout
        if previous != present:
            raise SystemExit("Canonical route changed: " + relative)
        unchanged[relative] = hashlib.sha256(present).hexdigest()
    baseline_size = None
    if args.baseline_app:
        baseline = validate_bundle(args.baseline_app.resolve(strict=True))
        verify_baseline(baseline, active)
        baseline_size = size(args.baseline_app)
    measured = size(app)
    current_manifest = json.loads((args.source_root / "docs/evidence/PROCESS_V1_TOPIC_REVIEW_REOPEN_CANDIDATE_MANIFEST.json").read_bytes())
    if current_manifest["candidate_id"] != CURRENT_ID or active["candidate"]["candidate_id"] != CURRENT_ID:
        raise SystemExit("Exact CURRENT identity changed")
    report = {"schema_version": "1.0", "candidate_id": manifest["candidate_id"],
        "manifest_identity_sha256": manifest["identity_sha256"], "bundle_digest": manifest["bundle"]["digest"],
        "product_source": {key: manifest["identity"]["source"][key] for key in ("commit_sha", "tree_sha")},
        "capability_id": CAPABILITY, "mode": "ISOLATED_SYNTHETIC_NOT_AUTHORITATIVE",
        "real_provider_runs": runs, "strict_duration_failure": failure,
        "independent_expected_bytes_sha256": hashlib.sha256(expected).hexdigest(),
        "differential_existing_adapter": "PASS", "canonical_route_hashes_unchanged": unchanged,
        "current_record_sha256": sha256_file(current_path), "current_candidate_id": CURRENT_ID,
        "candidate_logical_bytes_excluding_bytecode": measured,
        "runtime_inventory": runtime_inventory(resources),
        "component_identity_matches_current": {
            key: value == current_manifest["identity"]["components"].get(key)
            for key, value in manifest["identity"]["components"].items()},
        "execution_identity_differences_from_current": {
            key: {"current": current_manifest["identity"]["execution"].get(key), "candidate": value}
            for key, value in manifest["identity"]["execution"].items()
            if value != current_manifest["identity"]["execution"].get(key)},
        "current_logical_bytes_excluding_bytecode": baseline_size,
        "delta_vs_current_bytes": measured - baseline_size if baseline_size is not None else None,
        "size_comparison": "PASS" if baseline_size is not None else "BLOCKED_MISSING_CURRENT_BUNDLE",
        "semantic_acceptance": False, "routing_switched": False, "models_executed": False}
    validate_bundle(app)
    (root / "pilot-evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"candidate_id": report["candidate_id"], "pilot": "PASS",
                      "size_comparison": report["size_comparison"], "evidence": str(root / "pilot-evidence.json")}))


if __name__ == "__main__":
    main()
