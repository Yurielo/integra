#!/usr/bin/env python3
"""Build, validate, optionally archive, then remove one owned Candidate."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from temp_workspace_lifecycle import (  # noqa: E402
    DEFAULT_EXPECTED_BYTES, DEFAULT_RESERVE_BYTES, run_owned,
)
import candidate_retention  # noqa: E402


def _build_inside_workspace(archive_root: Path | None, expected_bytes: int = DEFAULT_EXPECTED_BYTES,
                            *, native_tests: bool = False, package_tests: bool = False) -> int:
    root = archive_root or (Path.home() / 'Library/Application Support/Integra/Build Archive')
    with candidate_retention.reserved_build(root, expected_bytes, archive_copy=archive_root is not None):
        if package_tests:
            workspace = Path(os.environ['INTEGRA_OWNED_WORKSPACE']).resolve(strict=True)
            output = workspace / 'candidate'
            completed = subprocess.run([str(ROOT / 'scripts/package_ready_app.sh'), str(output)],
                                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                                       capture_output=True, text=True, check=True)
            print(json.dumps({'validation': 'READY_APP_PACKAGE_TEST_PASS',
                              'app': completed.stdout.strip().splitlines()[-1],
                              'retained_archive': None, 'candidate_identity_claimed': False}), flush=True)
            return 0
        if native_tests:
            # Tests use the same reservation and supervisor as Candidate builds.
            # Suppress Python import caches in the bytes under inspection.
            environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            return subprocess.run([str(ROOT / "scripts/test_macos_app.sh"), "--owned-workspace"],
                                  env=environment, check=True).returncode
        return _execute_build_inside_workspace(archive_root)


def _execute_build_inside_workspace(archive_root: Path | None) -> int:
    """Execute as the supervised child, never as an unowned top-level build."""
    workspace_name = os.environ.get("INTEGRA_OWNED_WORKSPACE")
    if not workspace_name:
        raise ValueError("candidate build requires an owned workspace")
    workspace = Path(workspace_name).resolve(strict=True)
    if not (workspace / ".integra-owned-workspace.json").is_file():
        raise ValueError("candidate workspace ownership marker is missing")
    app = workspace / "candidate" / "Integra.app"
    subprocess.run([str(ROOT / "scripts" / "build_macos_app.sh"), str(app.parent)], check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "candidate_manifest.py"),
                    "validate", str(app)], check=True, timeout=900)
    result: dict = {"workspace": str(workspace), "app": str(app), "retained_archive": None,
                    "candidate_manifest": json.loads((app / "Contents/Resources/candidate-manifest.json").read_text())}
    if archive_root is not None:
        completed = subprocess.run([sys.executable, str(ROOT / "scripts" / "candidate_archive.py"), "create",
                                    "--app", str(app), "--archive-root", str(archive_root)],
                                   check=True, capture_output=True, text=True, timeout=1800)
        result["retained_archive"] = json.loads(completed.stdout)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purpose", default="candidate")
    parser.add_argument("--base")
    parser.add_argument("--expected-bytes", type=int, default=DEFAULT_EXPECTED_BYTES)
    parser.add_argument("--reserve-bytes", type=int, default=DEFAULT_RESERVE_BYTES)
    parser.add_argument("--timeout-seconds", type=float, default=3600)
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument("--native-tests", action="store_true", help="run native tests under the same build admission")
    parser.add_argument("--package-tests", action="store_true", help="verify a disposable READY_APP package under admission")
    parser.add_argument("--inside-owned-workspace", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("timeout must be positive")
    if args.native_tests and args.package_tests:
        parser.error('choose one native validation mode')
    if (args.native_tests or args.package_tests) and args.archive_root is not None:
        parser.error("native test workspaces are disposable; archive publication is a separate Candidate operation")
    if args.expected_bytes < DEFAULT_EXPECTED_BYTES or args.reserve_bytes < DEFAULT_RESERVE_BYTES:
        parser.error("full Candidate builds require at least the documented expected bytes and hard disk reserve")
    if args.inside_owned_workspace:
        return _build_inside_workspace(args.archive_root, args.expected_bytes,
                                       native_tests=args.native_tests, package_tests=args.package_tests)
    try:
        root = args.archive_root or (Path.home() / "Library/Application Support/Integra/Build Archive")
        candidate_retention.build_preflight(root, args.expected_bytes, archive_copy=args.archive_root is not None)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    child = [sys.executable, str(Path(__file__).resolve()), "--inside-owned-workspace",
             "--expected-bytes", str(args.expected_bytes), "--reserve-bytes", str(args.reserve_bytes)]
    if args.archive_root is not None:
        child.extend(["--archive-root", str(args.archive_root.resolve())])
    if args.native_tests:
        child.append("--native-tests")
    if args.package_tests:
        child.append('--package-tests')
    args.argv = child
    return run_owned(args)


if __name__ == "__main__":
    raise SystemExit(main())
