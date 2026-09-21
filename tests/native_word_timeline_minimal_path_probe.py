"""Run the real packaged primary journey under the Finder launch contract.

This probe deliberately removes Homebrew PATH entries.  The production app must
resolve ffmpeg through its candidate-bound deterministic resolver while the real
SeminarText ASR and WhisperX Word Timeline workers execute.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


app, root, source = (Path(value).resolve() for value in sys.argv[1:])
root.mkdir(parents=True, exist_ok=False)
owned_source = root / source.name
shutil.copyfile(source, owned_source)
source_sha256 = hashlib.sha256(owned_source.read_bytes()).hexdigest()
environment = {key: value for key, value in os.environ.items() if not key.startswith("INTEGRA_")}
environment.update({
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "INTEGRA_APP_DATA_ROOT": str(root / "app-data"),
    "INTEGRA_NATIVE_SMOKE_DIR": str(root),
    "INTEGRA_NATIVE_RETRY_SMOKE": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
})
subprocess.run([
    str(app / "Contents/MacOS/Integra"), "--ui-probe-source", str(owned_source),
    "--ui-probe-output", "word_timeline",
], env=environment, check=True, timeout=1200)
run = json.loads((root / "native-run.json").read_bytes())
assert run["state"] == "COMPLETED", run
result = run["source_results"][0]
assert result["state"] == "COMPLETED", result
outputs = result["outputs"]
assert Path(outputs["transcript"]).is_file()
assert Path(outputs["subtitles"]).is_file()
timeline = Path(outputs["word_timeline"])
assert timeline.is_file() and timeline.stat().st_size > 0
evidence = next(timeline.parent.glob("*.worker-evidence.json"))
record = json.loads(evidence.read_bytes())
assert record["result"] == "PASS", record
assert record["details"]["runtime"]["ffmpeg"]["path"]
assert record["details"]["runtime"]["ffmpeg"]["sha256"]
assert record["details"]["runtime"]["ffmpeg"]["path_classification"]["uses_inherited_path"] is False
assert source_sha256 == hashlib.sha256(owned_source.read_bytes()).hexdigest()
print(json.dumps({
    "state": run["state"],
    "run_id": run["run_id"],
    "source_sha256": source_sha256,
    "candidate_id": record["candidate_id"],
    "bundle_digest": record["bundle_digest"],
    "word_timeline_evidence": str(evidence),
}, ensure_ascii=False, sort_keys=True))
