"""Sustained native operations-screen acceptance with isolated owned processes.

The real bundled bridge/pinned CLI runs against test-only media executables.
The recognizer deliberately sleeps: this verifies UI/lifecycle, not ASR quality.
No private media, account access, or external publication is involved.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.asr_tools import media_environment


def alive(pid):
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="],
                            capture_output=True, text=True, timeout=5)
    state = result.stdout.strip()
    return bool(state) and not state.startswith("Z")


def main():
    app, root = map(lambda value: Path(value).resolve(), sys.argv[1:])
    root.mkdir(parents=True, exist_ok=False)
    bridge = app / "Contents/Resources/bridge.py"
    binary = app / "Contents/MacOS/Integra"
    source = root / "synthetic.wav"
    source.write_bytes(b"isolated operations lifecycle fixture, not recognition input")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    overrides = media_environment(root)
    child_marker = root / "owned-child.pid"
    recognizer_calls = root / "recognizer-calls.txt"
    child_code = ("import os, signal, time; from pathlib import Path; "
                  "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                  f"Path({str(child_marker)!r}).write_text(str(os.getpid())); time.sleep(120)")
    Path(overrides["INTEGRA_WHISPER_CLI"]).write_text(
        f"#!{sys.executable}\nimport subprocess, sys, time\nfrom pathlib import Path\n"
        f"with Path({str(recognizer_calls)!r}).open('a') as calls: calls.write('started\\n')\n"
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}], start_new_session=True)\n"
        "time.sleep(120)\n")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("INTEGRA_")}
    environment.update(overrides)
    environment.update(INTEGRA_APP_DATA_ROOT=str(root / "app-data"), PYTHONDONTWRITEBYTECODE="1")

    def call(operation, request=None):
        result = subprocess.run([sys.executable, str(bridge), operation], input=json.dumps(request or {}),
                                capture_output=True, text=True, env=environment, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return json.loads(result.stdout)["result"]

    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(180)"], start_new_session=True)
    run_created = False
    try:
        sources = call("detect-sources", {"inputs": [str(source)]})
        plan = call("build-plan", {"sources": sources, "selected_outputs": ["transcript"]})
        execution = call("execute-plan", {"plan": plan, "name": "Native operations fixture"})
        run_created = True
        request = {"project_id": execution["project"]["project_id"], "run_id": execution["run"]["run_id"]}
        deadline = time.monotonic() + 30
        while not child_marker.is_file() and time.monotonic() < deadline:
            time.sleep(.05)
        assert child_marker.is_file(), "actual owned recognizer child did not start"
        child = int(child_marker.read_text())
        assert alive(child), "owned child was not active before native operations probe"
        assert call("run-status", request)["state"] == "RUNNING", "fixture is not genuinely processing"
        environment["INTEGRA_NATIVE_OPERATIONS_PROBE"] = str(root)
        subprocess.run([str(binary)], env=environment, check=True, timeout=60)

        evidence = json.loads((root / "ops-probe.json").read_bytes())
        assert type(evidence.get("unchanged_view_checks")) is int and evidence["unchanged_view_checks"] >= 2, evidence
        assert evidence.get("navigation_preserved") is True, evidence
        assert evidence.get("cancelled") is True and evidence.get("terminal_state") == "CANCELLED", evidence
        image = (root / "operations.png").read_bytes()
        assert image.startswith(b"\x89PNG\r\n\x1a\n") and len(image) > 100, "operations screenshot is missing or invalid"
        result = call("run-status", request)
        assert result["state"] == "CANCELLED", result
        assert not alive(child), "Cancel left its owned child running"
        assert unrelated.poll() is None, "Cancel affected an unrelated process"
        assert recognizer_calls.read_text().splitlines() == ["started"], "unexpected extra recognizer launch"
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash, "source bytes changed"
        print("INTEGRA_NATIVE_STABLE_OPERATIONS_AND_REAL_CANCEL: PASS", flush=True)
    finally:
        try:
            if run_created:
                # Let the production service verify birth identity and ownership;
                # never terminate a process by a stale PID file or by name.
                call("shutdown-active-runs")
        finally:
            if unrelated.poll() is None:
                unrelated.terminate()
            unrelated.wait(timeout=5)


if __name__ == "__main__":
    main()
