#!/usr/bin/env python3
"""Open the exact retained K2 Candidate in a supervised, disposable QA workspace.

Owner command: python3 -B scripts/launch_k2_owner_test.py
The command remains active until Integra exits; lifecycle cleanup then removes
only the workspace it created. No prompt, TTY, Enter key, or archive execution
is involved.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path[:0] = [str(ROOT), str(SCRIPTS)]

from integra_core.candidate_identity import MANIFEST_NAME, tree_sha256, validate_manifest  # noqa: E402
import candidate_archive  # noqa: E402
import k2_qa_fixture  # noqa: E402
import prepare_candidate_execution_copy as execution_copy  # noqa: E402
import temp_workspace_lifecycle as lifecycle  # noqa: E402


CANDIDATE_ID = "candidate-v1-0f69e617c0841f27afe2238a28d6c25ae5a80ce0fedf01cf0c114638de575032"
BUNDLE_DIGEST = "3d4d33a983455572157b06460c3faaef5afd0b977a0e3d2717101588a25718e5"
MANIFEST_DIGEST = "3aed49cda900a6af0d0e8abcae4f3db114d988ad9bf16c62c53ba6671d06cbfe"
IDENTITY = {"candidate_id": CANDIDATE_ID, "bundle_digest": BUNDLE_DIGEST,
            "manifest_digest": MANIFEST_DIGEST}
PURPOSE = "issue227-k2-gui-e2e"
ARCHIVE = (Path.home() / "Library/Application Support/Integra/Build Archive" /
           CANDIDATE_ID / BUNDLE_DIGEST)
EMBEDDED = "Contents/Resources/" + MANIFEST_NAME


def verify_app_identity(app: Path) -> dict:
    """Rehash a disposable app and require the exact immutable Candidate tuple."""
    app = app.resolve(strict=True)
    raw = (app / EMBEDDED).read_bytes()
    manifest = json.loads(raw)
    validate_manifest(manifest)
    actual = {"candidate_id": manifest["candidate_id"],
              "bundle_digest": manifest["bundle"]["digest"],
              "manifest_digest": hashlib.sha256(raw).hexdigest()}
    if actual != IDENTITY:
        raise ValueError("execution app does not match the accepted Owner Test Candidate")
    if tree_sha256(app, exclude={EMBEDDED}) != BUNDLE_DIGEST:
        raise ValueError("execution app bytes differ from the Candidate bundle digest")
    return actual


def launch_application(executable: Path, workspace: Path, environment: dict[str, str],
                       log_path: Path, *, startup_seconds: float = 2.0) -> int:
    """Run the native GUI as a supervised child and wait for the actual app exit."""
    executable = executable.resolve(strict=True)
    workspace = workspace.resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("Candidate GUI executable is missing or not executable")
    if not log_path.resolve().is_relative_to(workspace):
        raise ValueError("GUI log must remain inside the owned workspace")

    child = None
    with log_path.open("xb") as log:
        try:
            # Directly executing the app's GUI binary preserves the isolated
            # environment and keeps it in the lifecycle-owned process group.
            # This avoids LaunchServices detaching the app from workspace cleanup.
            child = subprocess.Popen([str(executable)], cwd=workspace, env=environment,
                                     stdin=subprocess.DEVNULL, stdout=log,
                                     stderr=subprocess.STDOUT, close_fds=True)
            deadline = time.monotonic() + startup_seconds
            while time.monotonic() < deadline:
                status = child.poll()
                if status is not None:
                    raise RuntimeError(f"Integra exited before the Owner Test began (exit {status})")
                time.sleep(min(.1, max(0, deadline - time.monotonic())))
            print(f"OWNER_TEST_APP_RUNNING: pid={child.pid}; close Integra after the GUI test.", flush=True)
            print("The disposable QA workspace remains alive until Integra exits.", flush=True)
            return_code = child.wait()
        finally:
            if child is not None and child.poll() is None:
                # Cancellation closes the managed GUI process before the
                # lifecycle supervisor is allowed to remove its workspace.
                child.send_signal(signal.SIGTERM)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=10)
    if return_code != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"Integra exited with {return_code}; app log tail:\n{tail}")
    return return_code


def _write_setup_evidence(workspace: Path, result: dict, archive_receipt: dict) -> None:
    payload = {"artifact_type": "integra.issue_227.owner_test_setup",
               "candidate": IDENTITY, "archive_status": archive_receipt["status"],
               "archive_inventory_sha256": archive_receipt["inventory_sha256"],
               "fixture": result, "semantic_product_acceptance": False}
    target = workspace / "owner-test-setup.json"
    with target.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    os.chmod(target, 0o600)


def _prepare_session() -> tuple[Path, dict, Path, dict, dict[str, str]]:
    if sys.platform != "darwin":
        raise RuntimeError("the Owner Test launcher requires macOS")
    workspace, _ = execution_copy._workspace()
    archive_receipt = candidate_archive.verify_archive(ARCHIVE, IDENTITY)
    print("OWNER_TEST_CANDIDATE_ARCHIVE: COMPLETE", flush=True)

    environment = os.environ.copy()
    environment["INTEGRA_OWNED_WORKSPACE"] = str(workspace)
    environment["INTEGRA_APP_DATA_ROOT"] = str(workspace)
    environment["TMPDIR"] = str(workspace / "tmp")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for key in ("INTEGRA_SEMINARTEXT_CHECKOUT", "INTEGRA_KNOWLEDGE_ADMISSION_CHECKOUT", "PYTHONPATH"):
        environment.pop(key, None)
    if not (workspace / "tmp").is_dir():
        raise ValueError("supervised lifecycle workspace lacks its private temporary directory")

    helper = SCRIPTS / "prepare_candidate_execution_copy.py"
    subprocess.run([sys.executable, "-B", str(helper), "--archive", str(ARCHIVE),
                    "--candidate-id", CANDIDATE_ID, "--bundle-digest", BUNDLE_DIGEST,
                    "--manifest-digest", MANIFEST_DIGEST], cwd=ROOT, env=environment,
                   stdin=subprocess.DEVNULL, check=True)
    app = workspace / "execution/Integra.app"
    verify_app_identity(app)

    project = k2_qa_fixture.prepare(workspace, purpose=PURPOSE)
    resources = app / "Contents/Resources"

    def bridge(operation: str, request: dict) -> dict:
        reply = subprocess.run(["/usr/bin/python3", "-B", str(resources / "bridge.py"), operation],
            input=json.dumps(request), capture_output=True, text=True, env=environment,
            check=False, timeout=180)
        if reply.returncode != 0:
            raise ValueError(f"packaged fixture setup failed at {operation}: exit={reply.returncode}; "
                             f"stdout={reply.stdout[-2000:]!r}; stderr={reply.stderr[-4000:]!r}")
        value = json.loads(reply.stdout)
        if value.get("ok") is not True:
            raise ValueError(f"packaged fixture setup failed at {operation}: {value}")
        return value["result"]

    fixture_result = k2_qa_fixture.exercise(bridge)
    if (fixture_result.get("reviewed_units") != 2 or fixture_result.get("concepts") != 2
            or fixture_result.get("relations") != 1 or fixture_result.get("qa_only") is not True
            or fixture_result.get("semantic_product_acceptance") is not False
            or fixture_result.get("k2_applied") is not False):
        raise ValueError("packaged fixture did not prove 2 reviewed units, 2 Concepts, 1 Relation")
    if not project.is_relative_to(workspace) or not (project / "QA_ONLY.json").is_file():
        raise ValueError("synthetic GUI fixture is not inside the owned workspace")
    _write_setup_evidence(workspace, fixture_result, archive_receipt)
    print("OWNER_TEST_FIXTURE: 2 synthetic reviewed units; 2 Concepts; 1 Relation; no K2 apply performed.", flush=True)

    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != "app.integra.ready" or info.get("CFBundleExecutable") != "Integra":
        raise ValueError("Candidate bundle identity/executable is not the expected Integra app")
    executable = app / "Contents/MacOS/Integra"
    if not executable.is_relative_to(app) or not executable.is_file():
        raise ValueError("Candidate GUI executable is not contained in the execution app")

    app_environment = environment.copy()
    app_environment["INTEGRA_APP_DATA_ROOT"] = str(workspace)
    app_environment["INTEGRA_CANDIDATE_APP"] = str(app)
    return workspace, archive_receipt, app, fixture_result, app_environment


def _verify_final_identity(workspace: Path, archive_receipt: dict, app: Path) -> None:
    copied_identity = verify_app_identity(app)
    final_archive = candidate_archive.verify_archive(ARCHIVE, IDENTITY)
    if copied_identity != IDENTITY or final_archive["inventory_sha256"] != archive_receipt["inventory_sha256"]:
        raise ValueError("Candidate or retained archive identity changed during the Owner Test")
    print("OWNER_TEST_CANDIDATE_UNCHANGED: YES", flush=True)
    print("OWNER_TEST_ARCHIVE_REVERIFIED: COMPLETE", flush=True)


def _worker() -> int:
    workspace, archive_receipt, app, _fixture_result, app_environment = _prepare_session()
    executable = app / "Contents/MacOS/Integra"
    launch_application(executable, workspace, app_environment, workspace / "Integra-owner-test.log")
    _verify_final_identity(workspace, archive_receipt, app)
    return 0

def _verify_launch() -> int:
    workspace, archive_receipt, app, fixture_result, app_environment = _prepare_session()
    executable = app / "Contents/MacOS/Integra"
    probe = workspace / "launch-observation.txt"
    app_environment["INTEGRA_LAUNCH_PROBE"] = str(probe)
    result = subprocess.run([str(executable)], cwd=workspace, env=app_environment,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=45, check=False)
    observed = probe.read_text(encoding="utf-8").strip() if probe.is_file() else ""
    expected_prefix = "LAUNCHED visible=true workflow=source-first title=Integra"
    if result.returncode != 0 or not observed.startswith(expected_prefix):
        raise RuntimeError("packaged GUI launch was not observable: " +
                           f"exit={result.returncode}, marker={observed!r}, stderr={result.stderr[-2000:]}")
    setup = json.loads((workspace / "owner-test-setup.json").read_text(encoding="utf-8"))
    if setup["fixture"].get("reviewed_units") != 2 or fixture_result.get("relations") != 1:
        raise ValueError("launch probe was not bound to the required K2 fixture")
    print("OWNER_TEST_NATIVE_GUI_LAUNCH: PASS", flush=True)
    print("OWNER_TEST_LAUNCH_OBSERVATION: " + observed, flush=True)
    _verify_final_identity(workspace, archive_receipt, app)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["--_worker"], ["--_verify-launch"]):
        return _worker() if args == ["--_worker"] else _verify_launch()
    if args not in ([], ["--verify-launch"]):
        print("Owner Test launcher accepts no user options.", file=sys.stderr)
        return 2
    if sys.platform != "darwin":
        print("OWNER_TEST_LAUNCH: FAIL: run this command on the reference Mac.", file=sys.stderr)
        return 2
    worker_argument = "--_verify-launch" if args == ["--verify-launch"] else "--_worker"
    command = [sys.executable, "-B", str(SCRIPTS / "temp_workspace_lifecycle.py"), "run",
               "--purpose", PURPOSE, "--expected-bytes", str(lifecycle.DEFAULT_EXPECTED_BYTES),
               "--reserve-bytes", str(lifecycle.DEFAULT_RESERVE_BYTES), "--wait-for-child-exit",
               "--", sys.executable, "-B", str(Path(__file__).resolve()), worker_argument]
    try:
        return subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, check=False).returncode
    except (OSError, subprocess.SubprocessError) as error:
        print(f"OWNER_TEST_LAUNCH: FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"OWNER_TEST_LAUNCH: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
