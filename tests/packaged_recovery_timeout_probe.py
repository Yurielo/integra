"""Candidate-bound timeout/retry proof with test-only media executables.

This exercises the packaged bridge's real owned-worker lifecycle.  It does not
exercise recognition quality or alter a production runtime.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.asr_tools import TRANSCRIPT, media_environment


def alive(pid: int) -> bool:
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="],
                            capture_output=True, text=True, timeout=5)
    return bool(result.stdout.strip()) and not result.stdout.strip().startswith("Z")


def main() -> None:
    app, root = (Path(value).resolve() for value in sys.argv[1:])
    root.mkdir(parents=True, exist_ok=False)
    bridge = app / "Contents/Resources/bridge.py"
    upstream = root / "upstream.wav"
    timed_out = root / "timeout.wav"
    upstream.write_bytes(b"completed upstream lifecycle fixture, not recognition input")
    timed_out.write_bytes(b"isolated timeout lifecycle fixture, not recognition input")
    overrides = media_environment(root)
    mode = root / "recognizer-mode"
    child_marker = root / "owned-child.pid"
    calls = root / "recognizer-calls"
    mode.write_text("timeout", encoding="utf-8")
    Path(overrides["INTEGRA_WHISPER_CLI"]).write_text(
        f"#!{sys.executable}\n"
        "import os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        f"mode=Path({str(mode)!r}).read_text().strip()\n"
        f"calls=Path({str(calls)!r})\n"
        "call=int(calls.read_text()) + 1 if calls.exists() else 1\n"
        "calls.write_text(str(call))\n"
        "if mode == 'timeout' and call == 2:\n"
        f"  child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], start_new_session=True)\n"
        f"  Path({str(child_marker)!r}).write_text(str(child.pid))\n"
        "  time.sleep(120)\n"
        "prefix=sys.argv[sys.argv.index('-of') + 1]\n"
        f"Path(prefix + '.txt').write_text({TRANSCRIPT!r} + '\\n')\n"
        f"Path(prefix + '.srt').write_text('1\\n00:00:00,000 --> 00:00:01,250\\n' + {TRANSCRIPT!r} + '\\n')\n",
        encoding="utf-8",
    )
    Path(overrides["INTEGRA_WHISPER_CLI"]).chmod(0o700)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("INTEGRA_")}
    environment.update(overrides)
    environment.update(
        INTEGRA_APP_DATA_ROOT=str(root / "app-data"),
        INTEGRA_PLAN_TIMEOUT_SECONDS="2",
        PYTHONDONTWRITEBYTECODE="1",
    )

    def call(operation: str, request: dict | None = None) -> dict:
        result = subprocess.run([sys.executable, str(bridge), operation],
                                input=json.dumps(request or {}), text=True,
                                capture_output=True, env=environment, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return json.loads(result.stdout)["result"]

    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                                 start_new_session=True)
    child = None
    try:
        sources = call("detect-sources", {"inputs": [str(upstream), str(timed_out)]})
        plan = call("build-plan", {"sources": sources, "selected_outputs": ["transcript"]})
        first = call("execute-plan", {"plan": plan, "name": "Candidate timeout fixture"})
        request = {"project_id": first["project"]["project_id"], "run_id": first["run"]["run_id"]}
        deadline = time.monotonic() + 30
        status = call("run-status", request)
        while status["state"] in {"QUEUED", "RUNNING"} and time.monotonic() < deadline:
            time.sleep(0.05)
            status = call("run-status", request)
        assert status["state"] == "FAILED", status
        assert child_marker.is_file(), "timeout fixture never reached owned recognizer"
        child = int(child_marker.read_text(encoding="utf-8"))
        child_alive = alive(child)
        timeout_result = status["source_results"][1]
        assert "exceeded bounded timeout" in timeout_result.get("error", ""), timeout_result
        upstream_result = status["source_results"][0]
        upstream_outputs = [Path(value) for value in upstream_result["outputs"].values()]
        upstream_preserved = (upstream_result["state"] == "COMPLETED" and bool(upstream_outputs)
                              and all(path.is_file() and path.read_bytes() for path in upstream_outputs))
        timeout_evidence = {
            "timeout_run_id": request["run_id"],
            "timeout_state": status["state"],
            "timeout_classification": "PROCESS_TIMEOUT",
            "timeout_error": timeout_result["error"],
            "source_states": [item["state"] for item in status["source_results"]],
            "owned_child_cleaned_by_product": not child_alive,
            "unrelated_alive_after_timeout": unrelated.poll() is None,
            "upstream_artifacts_preserved": upstream_preserved,
            "same_app_data_root": True,
        }
        (root / "timeout-evidence.json").write_text(
            json.dumps(timeout_evidence, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        assert not child_alive, "timeout left an owned recognizer child alive"
        assert unrelated.poll() is None, "timeout cleanup killed an unrelated process"
        assert upstream_preserved, "timeout cleanup damaged completed upstream artifacts"

        mode.write_text("success", encoding="utf-8")
        retried = call("retry-run", request)
        retry_request = {"project_id": first["project"]["project_id"], "run_id": retried["run_id"]}
        deadline = time.monotonic() + 30
        completed = call("run-status", retry_request)
        while completed["state"] in {"QUEUED", "RUNNING"} and time.monotonic() < deadline:
            time.sleep(0.05)
            completed = call("run-status", retry_request)
        assert completed["state"] == "COMPLETED", completed
        evidence = timeout_evidence | {
            "retry_run_id": retry_request["run_id"],
            "retry_state": completed["state"],
            "owned_child_cleaned": True,
        }
        (root / "timeout-evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        print("INTEGRA_PACKAGED_TIMEOUT_AND_RETRY: PASS", flush=True)
    finally:
        # Test fixtures own these exact PIDs; this cleanup never broadens the
        # product ownership contract asserted above.
        if child is not None and alive(child):
            os.kill(child, signal.SIGKILL)
        if unrelated.poll() is None:
            unrelated.kill()
            unrelated.wait(timeout=5)


if __name__ == "__main__":
    main()
