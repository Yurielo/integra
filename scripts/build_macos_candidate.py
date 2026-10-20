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
KNOWLEDGE_ADMISSION_ENV = "INTEGRA_KNOWLEDGE_ADMISSION_CHECKOUT"
KNOWLEDGE_ADMISSION_COMMIT = "a39de3143e78e25be8ecce242a5fe812c9af137c"


def _is_clean_pinned_source(path: Path, expected_commit: str) -> bool:
    """Return whether a Git runtime input is both exact-pinned and clean."""
    revision = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=False, capture_output=True, text=True,
    ).stdout.strip()
    if revision != expected_commit:
        return False
    dirty = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
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


def _knowledge_admission_checkout() -> Path:
    """Locate the separately pinned SeminarText-owned K2 contract source."""
    source_repository = Path.home() / "Documents" / "seminartext"
    for worktree in _registered_component_worktrees(source_repository):
        if _is_clean_pinned_source(worktree, KNOWLEDGE_ADMISSION_COMMIT):
            return worktree
    raise ValueError("pinned Knowledge admission source is unavailable")


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
    # This separately accepted capability is not part of the Process runtime
    # pin.  Its own preflight rechecks commit, tree and every bound file;
    # supplying a clean exact worktree only makes that existing contract
    # available inside the disposable Candidate workspace.
    os.environ.setdefault(KNOWLEDGE_ADMISSION_ENV, str(_knowledge_admission_checkout()))


def _build_inside_workspace(archive_root: Path | None, expected_bytes: int = DEFAULT_EXPECTED_BYTES,
                            *, native_tests: bool = False, package_tests: bool = False,
                            engineering_gui: bool = False) -> int:
    root = archive_root or (Path.home() / 'Library/Application Support/Integra/Build Archive')
    with candidate_retention.reserved_build(root, expected_bytes, archive_copy=archive_root is not None):
        if package_tests:
            workspace = Path(os.environ['INTEGRA_OWNED_WORKSPACE']).resolve(strict=True)
            output = workspace / 'candidate'
            try:
                completed = subprocess.run([str(ROOT / 'scripts/package_ready_app.sh'), str(output)],
                                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                                           capture_output=True, text=True, check=True)
            except subprocess.CalledProcessError as error:
                raise RuntimeError('engineering GUI package failed: '
                                   f'stdout={error.stdout[-4000:]!r}; stderr={error.stderr[-4000:]!r}') from error
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
        if engineering_gui:
            # Production-shaped native QA uses normal admission but is never
            # archived or published as an Owner Candidate.
            workspace = Path(os.environ['INTEGRA_OWNED_WORKSPACE']).resolve(strict=True)
            if not workspace.name.startswith('integra-owned-issue227-k2-gui-e2e-'):
                raise ValueError('engineering GUI QA requires the exact issue227 owned workspace')
            output = workspace / 'candidate'
            try:
                completed = subprocess.run([str(ROOT / 'scripts/package_ready_app.sh'), str(output)],
                                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                                           capture_output=True, text=True, check=True)
            except subprocess.CalledProcessError as error:
                raise RuntimeError('engineering GUI package failed: '
                                   f'stdout={error.stdout[-4000:]!r}; stderr={error.stderr[-4000:]!r}') from error
            app = Path(completed.stdout.strip().splitlines()[-1]).resolve(strict=True)
            subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/prepare_k2_gui_fixture.py')],
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), check=True)
            print(json.dumps({'validation': 'ENGINEERING_GUI_READY', 'app': str(app),
                              'workspace': str(workspace), 'retained_archive': None,
                              'candidate_identity_claimed': False}), flush=True)
            environment = dict(os.environ, INTEGRA_APP_DATA_ROOT=str(workspace),
                               PYTHONDONTWRITEBYTECODE='1')
            return subprocess.run([str(app / 'Contents/MacOS/Integra'), '--integra-data-root', str(workspace)], cwd=workspace,
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
    parser.add_argument("--engineering-gui", action="store_true",
                        help="launch a disposable admitted package for native engineering QA")
    parser.add_argument("--inside-owned-workspace", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("timeout must be positive")
    if sum((args.native_tests, args.package_tests, args.engineering_gui)) > 1:
        parser.error('choose one native validation mode')
    if (args.native_tests or args.package_tests or args.engineering_gui) and args.archive_root is not None:
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
                                       native_tests=args.native_tests, package_tests=args.package_tests,
                                       engineering_gui=args.engineering_gui)
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
    if args.engineering_gui:
        child.append('--engineering-gui')
        # The fixture itself verifies this exact purpose in the ownership
        # marker.  It distinguishes the live, disposable GUI test workspace
        # from every Candidate or generic test workspace.
        args.purpose = 'issue227-k2-gui-e2e'
    args.argv = child
    # ``run_owned`` supports a bounded batch child and an interactive child.
    # Only the disposable native GUI harness is interactive; package/native
    # checks retain the normal timeout contract.
    args.wait_for_child_exit = bool(args.engineering_gui)
    return run_owned(args)


if __name__ == "__main__":
    raise SystemExit(main())
