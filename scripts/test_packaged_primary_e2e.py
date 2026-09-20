#!/usr/bin/env python3
"""Bounded, headless primary acceptance gate through the bundled GUI bridge."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

CLI_SHA = "f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a"
COMMIT = "970bde598ddd649599295139986933e0e06cb9c0"


def run(argv, *, timeout, **kwargs):
    return subprocess.run(argv, timeout=timeout, check=True, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    app = args.app.resolve(strict=True)
    resources = app / "Contents" / "Resources"
    bridge = resources / "bridge.py"
    if not bridge.is_file(): raise SystemExit("candidate bridge is unavailable")
    args.work.mkdir(parents=True, exist_ok=True)
    media = args.work / "generated-russian-speech.mp4"
    aiff = args.work / "generated-russian-speech.aiff"
    run(["/usr/bin/say", "-v", "Milena", "-o", str(aiff),
         "Здравствуйте. Это проверка полного процесса распознавания речи, субтитров, временной шкалы слов и тем."], timeout=30)
    run(["/opt/homebrew/bin/ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(media)], timeout=60)
    env = {key: value for key, value in os.environ.items() if not key.startswith("INTEGRA_")}
    env.update(INTEGRA_APP_DATA_ROOT=str(args.work / "app-data"), PYTHONPATH=str(resources), PYTHONDONTWRITEBYTECODE="1")
    def call(operation, request):
        result = run(["/usr/bin/python3", str(bridge), operation], input=json.dumps(request), text=True, capture_output=True, env=env, timeout=30)
        value = json.loads(result.stdout)
        if not value.get("ok"): raise AssertionError(value)
        return value["result"]
    manifest = json.loads((resources / "runtime/seminartext/runtime.json").read_text())
    assert manifest["commit_sha"] == COMMIT and manifest["entrypoint_sha256"] == CLI_SHA
    sources = call("detect-sources", {"inputs": [str(media)]})
    caps = {item["id"]: item for item in call("capability-registry", {"sources": sources})}
    selected = ["transcript", "subtitles", "word_timeline", "topics"]
    assert all(caps[item]["runtime_available"] for item in selected), caps
    plan = call("build-plan", {"sources": sources, "selected_outputs": selected})
    started = call("execute-plan", {"name": "Packaged primary E2E", "plan": plan})
    project_id, run_id = started["project"]["project_id"], started["run"]["run_id"]
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        status = call("run-status", {"project_id": project_id, "run_id": run_id})
        if status["state"] not in {"QUEUED", "RUNNING"}: break
        time.sleep(1)
    else: raise TimeoutError("primary packaged job exceeded 300 seconds")
    assert status["state"] == "COMPLETED", status
    source = status["source_results"][0]; assert source["state"] == "COMPLETED", source
    outputs = source["outputs"]
    for key in ("transcript", "transcript_json", "subtitles", "word_timeline", "topics"):
        assert Path(outputs[key]).is_file(), (key, outputs)
    timeline, topics = json.loads(Path(outputs["word_timeline"]).read_text()), json.loads(Path(outputs["topics"]).read_text())
    assert timeline.get("capability") == "word_timeline" and timeline.get("words")
    assert topics.get("topics") and all(item.get("semantic_status") == "REVIEW_REQUIRED" for item in topics["topics"])
    navigation = call("media-navigation", {"project_id": project_id, "run_id": run_id, "source_id": source["source_id"]})
    assert navigation.get("segments")
    print(json.dumps({"state": "SUCCESS", "production_terminal_state": status["state"], "project_id": project_id, "run_id": run_id, "fixture_sha256": sources[0]["properties"]["content_sha256"], "outputs": outputs}, ensure_ascii=False))


if __name__ == "__main__": main()
