#!/usr/bin/env python3
"""Build disposable engineering packages; publish only explicit Owner Candidates."""
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


PINNED_COMPONENT_COMMITS = {
    "INTEGRA_SEMINARTEXT_BUILD_CHECKOUT": "13644d262776aacdf36221b9a9fc7ebd0a7c0737",
    "INTEGRA_VIDEOTEXT_BUILD_CHECKOUT": "2e098d1705b6815628bee1e023f4742718eabf02",
    "INTEGRA_BOOKTEXT_BUILD_CHECKOUT": "46396649214275eb18054b670a842bace02d02e1",
}


def _is_clean_pinned_source(path: Path, expected_commit: str) -> bool:
    """Return whether a Git runtime input is both exact-pinned and clean."""
    revision = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=False, capture_output=True, text=True,
    ).stdout.strip()
    if revision != expected_commit:
        return False
    dirty = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain", "--", "Sources"],
        check=False, capture_output=True, text=True,
    ).stdout.strip()
    return not dirty


def _registered_component_worktrees(path: Path) -> list[Path]:
    """Return locally registered worktrees for a component checkout."""
    listing = subprocess.run(
        ["git", "-C", str(path), "worktree", "list", "--porcelain"],
        check=False, capture_output=True, text=True,
    )
    if getattr(listing, "returncode", 0):
        return []
    return [Path(line.removeprefix("worktree ")).resolve()
            for line in listing.stdout.splitlines() if line.startswith("worktree ")]


def _pinned_runtime_paths() -> dict[str, Path]:
    """Find the local worktrees that own each pinned build input.

    A full Candidate is deliberately built inside a disposable owned
    workspace.  Runtime components are ignored local build inputs, so they
    are not copied into that workspace.  Resolve each from a registered local
    worktree and let ``build_macos_app.sh`` verify every declared pin and
    digest before packaging.  Never fall back to an unverified path.
    """
    candidates = [ROOT]
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "worktree", "list", "--porcelain"],
        check=True, capture_output=True, text=True,
    )
    candidates.extend(
        Path(line.removeprefix("worktree ")).resolve()
        for line in listing.stdout.splitlines() if line.startswith("worktree ")
    )
    required = {
        "INTEGRA_SEMINARTEXT_BUILD_CHECKOUT": ".runtime-components/seminartext-pinned",
        "INTEGRA_VIDEOTEXT_BUILD_CHECKOUT": ".runtime-components/videotext-pinned",
        "INTEGRA_BOOKTEXT_BUILD_CHECKOUT": ".runtime-components/booktext-pinned",
        "INTEGRA_REVIEW_WHEELS": ".runtime-components/review-wheels",
        "INTEGRA_WORD_ALIGNMENT_SITE_PACKAGES": ".runtime-word-alignment/lib/python3.13/site-packages",
    }
    resolved: dict[str, Path] = {}
    for name, relative in required.items():
        for candidate in candidates:
            path = candidate / relative
            if not path.is_dir():
                continue
            expected_commit = PINNED_COMPONENT_COMMITS.get(name)
            inputs = [path]
            if expected_commit:
                # The primary pinned checkout is intentionally allowed to be
                # used for interactive component development.  For a governed
                # Integra build, locate a clean registered worktree at the
                # same declared pin instead of consuming its uncommitted
                # source bytes.
                inputs.extend(_registered_component_worktrees(path))
            for input_path in inputs:
                if expected_commit:
                    # A matching commit is not enough for a packaged runtime
                    # input.  A dirty source tree would silently package bytes
                    # which are neither the declared pin nor reviewable from
                    # its provenance.  Prefer another registered clean
                    # worktree and fail closed when no such input exists.
                    if not _is_clean_pinned_source(input_path, expected_commit):
                        continue
                resolved[name] = input_path
                break
            if name in resolved:
                break
        else:
            raise ValueError(f"pinned local build input is unavailable: {relative}")
    return resolved


def _bind_pinned_runtime_environment() -> None:
    """Bind owned-workspace builds to verified local pinned runtime inputs.

    Explicit operator-provided paths retain precedence.  The packaging script
    independently checks the pinned commits and hashes, so this binding only
    supplies a location; it cannot relax runtime identity verification.
    """
    for name, value in _pinned_runtime_paths().items():
        os.environ.setdefault(name, str(value))


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
                    "candidate_manifest": json.loads((app / "Contents/Resources/candidate-manifest.json").read_text()),
                    "lifecycle": "ENGINEERING_QA_BUILD"}
    if archive_root is not None:
        completed = subprocess.run([sys.executable, str(ROOT / "scripts" / "candidate_archive.py"), "create",
                                    "--app", str(app), "--archive-root", str(archive_root),
                                    "--lifecycle-status", candidate_retention.PRE_OWNER],
                                   check=True, capture_output=True, text=True, timeout=1800)
        result["retained_archive"] = json.loads(completed.stdout)
        result["lifecycle"] = candidate_retention.PRE_OWNER
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
    parser.add_argument("--publish-owner-candidate", action="store_true",
                        help="publish an immutable Candidate for Candidate-bound pre-owner validation")
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
    if args.archive_root is not None and not args.publish_owner_candidate:
        parser.error("archive publication requires --publish-owner-candidate; use a disposable engineering build before Candidate-bound validation")
    if args.publish_owner_candidate and args.archive_root is None:
        parser.error("--publish-owner-candidate requires --archive-root")
    if args.expected_bytes < DEFAULT_EXPECTED_BYTES or args.reserve_bytes < DEFAULT_RESERVE_BYTES:
        parser.error("full Candidate builds require at least the documented expected bytes and hard disk reserve")
    # Bind ignored local runtime inputs before creating the owned workspace so
    # its supervised child inherits only verified source locations.
    _bind_pinned_runtime_environment()
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
        child.extend(["--archive-root", str(args.archive_root.resolve()), "--publish-owner-candidate"])
    if args.native_tests:
        child.append("--native-tests")
    if args.package_tests:
        child.append('--package-tests')
    args.argv = child
    return run_owned(args)


if __name__ == "__main__":
    raise SystemExit(main())
