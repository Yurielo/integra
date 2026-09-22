"""Packaged Finder-like proof of ordered local-source failure isolation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


app, root = (Path(value).resolve() for value in sys.argv[1:])
root.mkdir(parents=True, exist_ok=False)
for name in ("first.wav", "corrupt.mp3", "later.wav"):
    (root / name).write_bytes(("fixture-" + name).encode("utf-8"))
ffmpeg = root / "controlled-ffmpeg"
ffmpeg.write_text("#!/bin/sh\n"
                  "if [ \"$1\" = \"--version\" ]; then echo 'ffmpeg controlled'; exit 0; fi\n"
                  "previous=''\n"
                  "for arg in \"$@\"; do [ \"$previous\" = \"-i\" ] && source=$arg; previous=$arg; output=$arg; done\n"
                  "grep -q 'fixture-corrupt.mp3' \"$source\" && exit 23\n"
                  "cp \"$source\" \"$output\"\n")
ffmpeg.chmod(0o700)
bridge = app / "Contents/Resources/bridge.py"
environment = {key: value for key, value in os.environ.items() if not key.startswith("INTEGRA_")}
environment.update({"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "INTEGRA_APP_DATA_ROOT": str(root / "app-data"),
                    "INTEGRA_FFMPEG": str(ffmpeg), "PYTHONDONTWRITEBYTECODE": "1"})


def call(operation: str, request: dict) -> dict:
    completed = subprocess.run(["/usr/bin/python3", str(bridge), operation], input=json.dumps(request),
                               capture_output=True, text=True, env=environment, check=True, timeout=60)
    envelope = json.loads(completed.stdout)
    assert envelope["ok"], envelope
    return envelope["result"]


try:
    inputs = [str(root / name) for name in ("first.wav", "corrupt.mp3", "later.wav")]
    sources = call("detect-sources", {"inputs": inputs})
    plan = call("build-plan", {"sources": sources, "selected_outputs": ["enhance_audio"]})
    execution = call("execute-plan", {"plan": plan, "name": "Ordered local failure isolation"})
    project_id, run_id = execution["project"]["project_id"], execution["run"]["run_id"]
    deadline = time.monotonic() + 120
    while True:
        run = call("run-status", {"project_id": project_id, "run_id": run_id})
        if run["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
        assert time.monotonic() < deadline, run
        time.sleep(.1)
    assert run["state"] == "FAILED", run
    assert [item["source_id"] for item in run["source_results"]] == [item["source_id"] for item in sources]
    assert [item["state"] for item in run["source_results"]] == ["COMPLETED", "FAILED", "COMPLETED"]
    assert run["completed_sources"] == 2 and run["total_sources"] == 3
    assert run["source_results"][1]["outputs"] == {}
    assert "controlled-ffmpeg" in run["source_results"][1]["error"]
    for offset in (0, 2):
        output = Path(run["source_results"][offset]["outputs"]["enhanced_audio"])
        assert output.is_file() and output.read_bytes() == ("fixture-" + ("first.wav" if offset == 0 else "later.wav")).encode("utf-8")
    reopened = call("run-status", {"project_id": project_id, "run_id": run_id})
    assert reopened == run
    manifest = json.loads((app / "Contents/Resources/candidate-manifest.json").read_bytes())
    print(json.dumps({"state": "PASS", "candidate_id": manifest["candidate_id"],
                      "bundle_digest": manifest["bundle"]["digest"], "project_id": project_id, "run_id": run_id,
                      "source_states": [item["state"] for item in run["source_results"]],
                      "source_order": [item["display_name"] for item in run["source_results"]],
                      "run_sha256": hashlib.sha256(json.dumps(run, sort_keys=True).encode()).hexdigest()}, sort_keys=True))
finally:
    subprocess.run(["/usr/bin/python3", str(bridge), "shutdown-active-runs"], input="{}", capture_output=True,
                   text=True, env=environment, check=True, timeout=60)
