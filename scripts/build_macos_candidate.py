#!/usr/bin/env python3
"""Build, validate, optionally retain, then remove one owned candidate workspace."""
from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from temp_workspace_lifecycle import (  # noqa: E402
    DEFAULT_EXPECTED_BYTES, DEFAULT_RESERVE_BYTES, _process_start_token, _record, _terminate_group,
    cleanup_workspace, create_workspace,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purpose", default="candidate")
    parser.add_argument("--base")
    parser.add_argument("--expected-bytes", type=int, default=DEFAULT_EXPECTED_BYTES)
    parser.add_argument("--reserve-bytes", type=int, default=DEFAULT_RESERVE_BYTES)
    parser.add_argument("--timeout-seconds", type=float, default=3600)
    parser.add_argument("--archive-root", type=Path)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("timeout must be positive")

    workspace, marker = create_workspace(purpose=args.purpose, base=args.base,
                                         expected_bytes=args.expected_bytes,
                                         reserve_bytes=args.reserve_bytes)
    child = None
    interrupted = {"signal": None}

    def cancel(signum: int, _frame: object) -> None:
        interrupted["signal"] = signal.Signals(signum).name
        if child is not None:
            child.terminate()
            _terminate_group(child.pid)
        raise KeyboardInterrupt

    previous = {item: signal.getsignal(item) for item in (signal.SIGINT, signal.SIGTERM)}
    signal.signal(signal.SIGINT, cancel)
    signal.signal(signal.SIGTERM, cancel)
    outcome = 1
    try:
        output = workspace / "candidate"
        command = [str(ROOT / "scripts" / "build_macos_app.sh"), str(output)]
        # The low-level builder's path output is diagnostic here. The wrapper
        # itself owns the machine-readable result contract.
        child = subprocess.Popen(command, cwd=workspace, start_new_session=True, stdout=sys.stderr)
        marker = _record(workspace, marker, "BUILD_STARTED", state="RUNNING", child={
            "pid": child.pid, "start_token": _process_start_token(child.pid), "process_group": child.pid,
        })
        try:
            code = child.wait(timeout=args.timeout_seconds)
        except subprocess.TimeoutExpired:
            child.terminate()
            _terminate_group(child.pid)
            _record(workspace, marker, "BUILD_TIMEOUT", state="TIMED_OUT", timeout_seconds=args.timeout_seconds)
            outcome = 124
        else:
            if code != 0:
                _record(workspace, marker, "BUILD_FAILED", state="FAILED", exit_code=code)
                print(f"INTEGRA_CANDIDATE_LIFECYCLE: build failed with exit code {code}", file=sys.stderr)
                outcome = code
            else:
                app = output / "Integra.app"
                # Hashing a 2+ GiB bundle is deliberately I/O-bound. Under the
                # supported concurrent-build scenario it can exceed two minutes, so
                # the bound is generous but finite rather than a false timeout.
                subprocess.run([sys.executable, str(ROOT / "scripts" / "candidate_manifest.py"), "validate", str(app)], check=True, timeout=900)
                result = {"workspace": str(workspace), "app": str(app), "retained_archive": None}
                if args.archive_root is not None:
                    completed = subprocess.run([sys.executable, str(ROOT / "scripts" / "candidate_archive.py"), "create",
                                                "--app", str(app), "--archive-root", str(args.archive_root)],
                                               check=True, capture_output=True, text=True, timeout=1800)
                    result["retained_archive"] = json.loads(completed.stdout)
                _record(workspace, marker, "BUILD_VALIDATED", state="VALIDATED")
                print(json.dumps(result, sort_keys=True))
                outcome = 0
    except KeyboardInterrupt:
        _record(workspace, marker, "BUILD_CANCELLED", state="CANCELLED", signal=interrupted["signal"])
        outcome = 128
    finally:
        for item, handler in previous.items():
            signal.signal(item, handler)
        if workspace.exists():
            try:
                cleanup_workspace(workspace, reason="CANDIDATE_BUILD_FINISHED", allow_live_owner=True)
            except (OSError, ValueError) as error:
                print(f"INTEGRA_CANDIDATE_LIFECYCLE: cleanup failed: {error}", file=sys.stderr)
                # A successful candidate must not conceal a leaked disposable
                # workspace, even though the marker permits later safe reaping.
                outcome = 1
    return outcome


if __name__ == "__main__":
    raise SystemExit(main())
