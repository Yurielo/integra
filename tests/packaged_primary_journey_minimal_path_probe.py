"""Full packaged bridge journey under a Finder-like minimal environment."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


app, root, source = (Path(value).resolve() for value in sys.argv[1:])
root.mkdir(parents=True, exist_ok=False)
bridge = app / "Contents/Resources/bridge.py"
environment = {key: value for key, value in os.environ.items() if not key.startswith("INTEGRA_")}
environment.update({
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "INTEGRA_APP_DATA_ROOT": str(root / "app-data"),
    "PYTHONDONTWRITEBYTECODE": "1",
})


def call(operation: str, request: dict | None = None) -> dict:
    result = subprocess.run(["/usr/bin/python3", str(bridge), operation],
                            input=json.dumps(request or {}), capture_output=True, text=True,
                            env=environment, check=True, timeout=60)
    envelope = json.loads(result.stdout)
    assert envelope["ok"], envelope
    return envelope["result"]


try:
    detected = call("detect-sources", {"inputs": [str(source)]})
    plan = call("build-plan", {"sources": detected,
                                "selected_outputs": ["transcript", "subtitles", "word_timeline", "topics"]})
    execution = call("execute-plan", {"plan": plan, "name": source.name})
    project_id = execution["project"]["project_id"]
    run_id = execution["run"]["run_id"]
    deadline = time.monotonic() + 1800
    while True:
        run = call("run-status", {"project_id": project_id, "run_id": run_id})
        if run["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
        if time.monotonic() > deadline:
            raise AssertionError(f"packaged journey timed out: {run}")
        time.sleep(1)
    assert run["state"] == "COMPLETED", run
    result = run["source_results"][0]
    assert result["state"] == "COMPLETED", result
    outputs = result["outputs"]
    for key in ("transcript", "subtitles", "word_timeline", "topics"):
        assert Path(outputs[key]).is_file() and Path(outputs[key]).stat().st_size > 0, key
    navigation = call("media-navigation", {"project_id": project_id, "run_id": run_id,
                                            "source_id": result["source_id"]})
    assert navigation["segments"], navigation
    timeline = Path(outputs["word_timeline"])
    evidence = next(timeline.parent.glob("*.worker-evidence.json"))
    record = json.loads(evidence.read_bytes())
    assert record["result"] == "PASS", record
    ffmpeg = record["details"]["runtime"]["ffmpeg"]
    assert ffmpeg["sha256"] and ffmpeg["path_classification"]["uses_inherited_path"] is False
    print(json.dumps({
        "state": run["state"], "project_id": project_id, "run_id": run_id,
        "source_id": result["source_id"], "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "candidate_id": record["candidate_id"], "bundle_digest": record["bundle_digest"],
        "word_timeline_evidence": str(evidence), "navigation_segments": len(navigation["segments"]),
        "topic_output": outputs["topics"],
    }, ensure_ascii=False, sort_keys=True))
finally:
    subprocess.run(["/usr/bin/python3", str(bridge), "shutdown-active-runs"], input="{}",
                   capture_output=True, text=True, env=environment, check=True, timeout=60)
