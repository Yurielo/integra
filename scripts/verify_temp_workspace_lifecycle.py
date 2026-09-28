#!/usr/bin/env python3
"""Run bounded real-build evidence for the disposable Integra workspace contract.

It is deliberately opt-in: no retained archive or installed application is
modified. All temporary component checkouts and candidates are inside one
marker-owned root and disappear at the end of the command.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from temp_workspace_lifecycle import (DEFAULT_EXPECTED_BYTES, _terminate_group, cleanup_workspace,
                                      create_workspace, reap_stale)  # noqa: E402

SEMINARTEXT_COMMIT = "13644d262776aacdf36221b9a9fc7ebd0a7c0737"
VIDEOTEXT_COMMIT = "2e098d1705b6815628bee1e023f4742718eabf02"
BOOKTEXT_COMMIT = "46396649214275eb18054b670a842bace02d02e1"


def disk(path: Path) -> dict:
    usage = shutil.disk_usage(path)
    return {"free_bytes": usage.free, "used_bytes": usage.used}


def command(argv: list[str], *, cwd: Path, environment: dict[str, str], timeout: float) -> subprocess.CompletedProcess:
    """Run a bounded evidence command in an isolated process group."""
    process = subprocess.Popen(argv, cwd=cwd, env=environment, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        _terminate_group(process.pid, grace_seconds=1)
        stdout, stderr = process.communicate()
        raise RuntimeError(f"command timed out after {timeout}s: {' '.join(argv)}\n{stderr or stdout}")
    completed = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}): {completed.stderr or completed.stdout}")
    return completed


def owned_roots(base: Path, *, exclude: Path) -> list[str]:
    """Report unretained child workspaces, never the evidence owner itself."""
    return sorted(str(path) for path in base.glob("integra-owned-*") if path.is_dir() and path != exclude)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seminartext-source", type=Path, required=True)
    parser.add_argument("--videotext-source", type=Path, required=True)
    parser.add_argument("--booktext-source", type=Path, required=True)
    parser.add_argument("--alignment-app", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=Path("/private/tmp"))
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    before = disk(args.base)
    workspace, marker = create_workspace(purpose="lifecycle-evidence", base=args.base,
                                         expected_bytes=512 * 1024 * 1024,
                                         reserve_bytes=2 * 1024 * 1024 * 1024)
    evidence: dict = {"schema_version": "1.0", "issue": 205, "before": before, "scenarios": []}
    try:
        components = workspace / "components"
        for name, source, commit in (("seminartext", args.seminartext_source, SEMINARTEXT_COMMIT),
                                     ("videotext", args.videotext_source, VIDEOTEXT_COMMIT),
                                     ("booktext", args.booktext_source, BOOKTEXT_COMMIT)):
            target = components / name
            command(["git", "clone", "--shared", str(source.resolve()), str(target)], cwd=workspace,
                    environment=os.environ.copy(), timeout=120)
            command(["git", "checkout", "--detach", commit], cwd=target, environment=os.environ.copy(), timeout=60)
        wheels = workspace / "review-wheels"
        command(["/opt/homebrew/opt/python@3.14/bin/python3.14", "-m", "pip", "download",
                 "--disable-pip-version-check", "--require-hashes", "--only-binary=:all:", "-r",
                 str(ROOT / "scripts/review-runtime-requirements.txt"), "--dest", str(wheels)],
                cwd=workspace, environment=os.environ.copy(), timeout=180)
        environment = os.environ | {
            "INTEGRA_SEMINARTEXT_BUILD_CHECKOUT": str(components / "seminartext"),
            "INTEGRA_VIDEOTEXT_BUILD_CHECKOUT": str(components / "videotext"),
            "INTEGRA_BOOKTEXT_BUILD_CHECKOUT": str(components / "booktext"),
            "INTEGRA_WORD_ALIGNMENT_SITE_PACKAGES": str(args.alignment_app.resolve() / "Contents/Resources/runtime/word-alignment/site-packages"),
            "INTEGRA_WORD_ALIGNMENT_MODEL_DIR": str(args.alignment_app.resolve() / "Contents/Resources/runtime/word-alignment/model"),
            "INTEGRA_REVIEW_WHEELS": str(wheels),
        }
        build = [sys.executable, str(ROOT / "scripts/build_macos_candidate.py"), "--base", str(args.base),
                 "--expected-bytes", str(DEFAULT_EXPECTED_BYTES), "--timeout-seconds", "1800"]
        for purpose in ("issue205-sequential-one", "issue205-sequential-two"):
            started = disk(args.base)
            completed = command([*build, "--purpose", purpose], cwd=workspace, environment=environment, timeout=1900)
            evidence["scenarios"].append({"id": purpose, "result": json.loads(completed.stdout.strip().splitlines()[-1]),
                                          "before": started, "after": disk(args.base),
                                          "remaining_owned_roots": owned_roots(args.base, exclude=workspace)})

        started = disk(args.base)
        concurrent: list[subprocess.Popen] = []
        try:
            for purpose in ("issue205-concurrent-one", "issue205-concurrent-two"):
                concurrent.append(subprocess.Popen([*build, "--purpose", purpose], cwd=workspace, env=environment,
                                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                                   start_new_session=True))
            payloads = []
            for process in concurrent:
                try:
                    stdout, stderr = process.communicate(timeout=1900)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    _terminate_group(process.pid, grace_seconds=1)
                    stdout, stderr = process.communicate()
                    raise RuntimeError(f"concurrent candidate timed out: {stderr or stdout}")
                if process.returncode:
                    raise RuntimeError(f"concurrent candidate failed ({process.returncode}): {stderr}")
                payloads.append(json.loads(stdout.strip().splitlines()[-1]))
        finally:
            for process in concurrent:
                if process.poll() is None:
                    process.terminate()
                    _terminate_group(process.pid, grace_seconds=1)
                    process.communicate()
        evidence["scenarios"].append({"id": "concurrent-full-candidates", "result": payloads,
                                      "before": started, "after": disk(args.base),
                                      "remaining_owned_roots": owned_roots(args.base, exclude=workspace)})

        for identifier, timeout in (("artificial-failure", 5), ("artificial-timeout", .1)):
            argv = [sys.executable, str(ROOT / "scripts/temp_workspace_lifecycle.py"), "run", "--base", str(args.base),
                    "--purpose", f"issue205-{identifier}", "--expected-bytes", "1", "--reserve-bytes", "0",
                    "--timeout-seconds", str(timeout), "--", sys.executable, "-c",
                    "raise SystemExit(7)" if identifier == "artificial-failure" else "import time; time.sleep(30)"]
            completed = subprocess.run(argv, cwd=workspace, env=environment, text=True, capture_output=True, timeout=15)
            evidence["scenarios"].append({"id": identifier, "exit_code": completed.returncode,
                                          "remaining_owned_roots": owned_roots(args.base, exclude=workspace)})

        live, _ = create_workspace(purpose="issue205-live-reap", base=args.base, expected_bytes=1, reserve_bytes=0)
        stale = command([sys.executable, str(ROOT / "scripts/temp_workspace_lifecycle.py"), "create", "--base", str(args.base),
                         "--purpose", "issue205-stale-reap", "--expected-bytes", "1", "--reserve-bytes", "0"],
                        cwd=workspace, environment=environment, timeout=10)
        stale_root = stale.stdout.strip()
        reaped = reap_stale(base=args.base)
        live_preserved = live.exists()
        pre_cleanup = owned_roots(args.base, exclude=workspace)
        cleanup_workspace(live, reason="EVIDENCE_LIVE_PROTECTION_COMPLETE", allow_live_owner=True)
        evidence["scenarios"].append({"id": "stale-reap-and-live-protection", "stale_root": stale_root,
                                      "reap": reaped, "live_root_preserved": live_preserved,
                                      "live_root_visible_before_explicit_cleanup": pre_cleanup,
                                      "remaining_owned_roots": owned_roots(args.base, exclude=workspace)})

        release = subprocess.run([sys.executable, str(ROOT / "scripts/temp_workspace_lifecycle.py"), "run", "--base", str(args.base),
                                  "--purpose", "issue205-release-path", "--expected-bytes", str(DEFAULT_EXPECTED_BYTES),
                                  "--timeout-seconds", "1800", "--", "/bin/sh", "-c",
                                  f"{ROOT}/scripts/package_ready_app.sh \"$INTEGRA_OWNED_WORKSPACE/release\""],
                                 cwd=workspace, env=environment, text=True, capture_output=True, timeout=1900)
        if release.returncode:
            raise RuntimeError(f"release path failed ({release.returncode}): {release.stderr}")
        evidence["scenarios"].append({"id": "release-path", "exit_code": release.returncode,
                                      "remaining_owned_roots": owned_roots(args.base, exclude=workspace)})
        evidence["after"] = disk(args.base)
        evidence["status"] = "PASS" if all(not item["remaining_owned_roots"] for item in evidence["scenarios"]) else "FAIL"
        args.evidence.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(evidence, sort_keys=True))
        return 0 if evidence["status"] == "PASS" else 1
    finally:
        if workspace.exists():
            cleanup_workspace(workspace, reason="EVIDENCE_FINISHED", allow_live_owner=True)


if __name__ == "__main__":
    raise SystemExit(main())
