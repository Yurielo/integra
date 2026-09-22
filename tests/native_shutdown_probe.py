"""Native shutdown acceptance on isolated, harmless process fixtures.

This tests lifecycle, NOT recognition quality: the test recognizer deliberately
starts a sleeping child that ignores SIGTERM. No private files are processed.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.asr_tools import media_environment

app, root = map(lambda value: Path(value).resolve(), sys.argv[1:])
root.mkdir(parents=True, exist_ok=False)
bridge = app / "Contents/Resources/bridge.py"
binary = app / "Contents/MacOS/Integra"


def alive(pid):
    value = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True).stdout.strip()
    return bool(value) and not value.startswith("Z")


def call(environment, operation, request=None):
    result = subprocess.run([sys.executable, str(bridge), operation], input=json.dumps(request or {}),
                            capture_output=True, text=True, env=environment, timeout=30)
    if result.returncode: raise RuntimeError(result.stdout + result.stderr)
    return json.loads(result.stdout)["result"]


def environment_for(folder):
    result = {key: value for key, value in os.environ.items() if not key.startswith("INTEGRA_")}
    return result | {"INTEGRA_APP_DATA_ROOT": str(folder / "app-data"), "PYTHONDONTWRITEBYTECODE": "1"}


unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(180)"], start_new_session=True)
owned_environments = []
try:
    for mode in ("CLOSE", "QUIT"):
        folder = root / mode.lower(); folder.mkdir()
        source = folder / "synthetic.wav"; source.write_bytes(b"isolated lifecycle fixture, not ASR input")
        overrides = media_environment(folder)
        child_marker = folder / "child.pid"
        child_code = ("import os, signal, time; from pathlib import Path; "
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                      f"Path({str(child_marker)!r}).write_text(str(os.getpid())); time.sleep(45)")
        Path(overrides["INTEGRA_WHISPER_CLI"]).write_text(
            f"#!{sys.executable}\nimport subprocess, sys, time\n"
            f"subprocess.Popen([sys.executable, '-c', {child_code!r}])\ntime.sleep(45)\n")
        environment = environment_for(folder) | overrides
        sources = call(environment, "detect-sources", {"inputs": [str(source)]})
        plan = call(environment, "build-plan", {"sources": sources, "selected_outputs": ["transcript"]})
        execution = call(environment, "execute-plan", {"plan": plan, "name": "Native shutdown fixture"})
        owned_environments.append(dict(environment))
        request = {"project_id": execution["project"]["project_id"], "run_id": execution["run"]["run_id"]}
        deadline = time.monotonic() + 30
        while not child_marker.exists() and time.monotonic() < deadline: time.sleep(.05)
        assert child_marker.exists(), "owned child did not start"
        child = int(child_marker.read_text()); assert alive(child)
        marker = folder / "terminated.txt"
        environment["INTEGRA_" + mode + "_PROBE"] = str(marker)
        subprocess.run([str(binary)], env=environment, check=True, timeout=40)
        assert marker.is_file(), "native application did not acknowledge termination"
        assert not alive(child), "native exit left its owned child running"
        result = call(environment, "run-status", request)
        assert result["state"] == "CANCELLED", result
        assert unrelated.poll() is None, "shutdown affected an unrelated process"
        assert source.read_bytes() == b"isolated lifecycle fixture, not ASR input"
        print(f"INTEGRA_NATIVE_{mode}_ACTIVE_RUN: PASS", flush=True)

    folder = root / "ambiguous"; folder.mkdir()
    environment = environment_for(folder)
    project = call(environment, "create-project", {"name": "Ambiguous process fixture"})
    run_id = "urn:integra:run:" + str(uuid.uuid4())
    runs = Path(environment["INTEGRA_APP_DATA_ROOT"]) / "projects" / project["project_id"].split(":")[-1] / "runs"
    runs.mkdir()
    run_path = runs / (run_id.split(":")[-1] + ".json")
    original = {"run_id": run_id, "state": "RUNNING", "worker_pid": unrelated.pid, "created_at": "2026-09-13T00:00:00Z",
                "source_results": [], "completed_sources": 0, "total_sources": 1}
    run_path.write_text(json.dumps(original))
    failure = folder / "failure.txt"; terminated = folder / "terminated.txt"
    environment.update(INTEGRA_QUIT_PROBE=str(terminated), INTEGRA_SHUTDOWN_FAILURE_PROBE=str(failure))
    native = subprocess.Popen([str(binary)], env=environment)
    try:
        deadline = time.monotonic() + 30
        while not (failure.exists() or terminated.exists()) and time.monotonic() < deadline and native.poll() is None: time.sleep(.05)
        assert unrelated.poll() is None, "ambiguous PID was signalled"
        reconciled = json.loads(run_path.read_text())
        assert reconciled["state"] == "FAILED", reconciled
        assert reconciled["recovery"]["classification"] == "STALE_RUNNING_RECONCILED", reconciled
        assert terminated.exists() and not failure.exists(), "stale run was not safely reconciled before native quit"
        print("INTEGRA_NATIVE_STALE_RUNNING_RECONCILED: PASS", flush=True)
    finally:
        # Only this test-owned UI process is terminated after the failure check.
        native.terminate(); native.wait(timeout=5)
finally:
    cleanup_errors = []
    try:
        for environment in owned_environments:
            # Service verifies recorded nonce/start identity; never kill by name
            # or trust the test's persisted PID alone, even during failure cleanup.
            try:
                call(environment, "shutdown-active-runs")
            except Exception as error:
                cleanup_errors.append(str(error))
    finally:
        unrelated.terminate(); unrelated.wait(timeout=5)
    if cleanup_errors:
        raise RuntimeError("Test cleanup failed: " + "; ".join(cleanup_errors))
