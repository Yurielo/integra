"""Sustained native AppKit -> bridge -> real VideoText acceptance probe.

Invoked by test_macos_app.sh on its fresh bundle. Synthetic input only.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

app, root = map(lambda value: Path(value).resolve(), sys.argv[1:])
root.mkdir(parents=True, exist_ok=False)
source = root / "synthetic.mp4"
subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                "testsrc2=size=320x240:rate=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)], check=True, timeout=30)
before = hashlib.sha256(source.read_bytes()).hexdigest()
environment = {key: value for key, value in os.environ.items() if not key.startswith("INTEGRA_")}
environment.update(INTEGRA_APP_DATA_ROOT=str(root / "app-data"), INTEGRA_NATIVE_SMOKE_DIR=str(root), PYTHONDONTWRITEBYTECODE="1")
subprocess.run([str(app / "Contents/MacOS/Integra"), "--ui-probe-source", str(source),
                "--ui-probe-output", "speed_video,audio_analysis"], env=environment, check=True, timeout=200)
run = json.loads((root / "native-run.json").read_bytes())
assert run["state"] == "COMPLETED", run
outputs = run["source_results"][0]["outputs"]
assert "transcript" not in outputs, "media-only selection must not run ASR"
for key in ("speed_video", "audio_analysis", "speed_video_record", "audio_analysis_record"):
    assert Path(outputs[key]).is_file() and Path(outputs[key]).stat().st_size > 0, key
speed = json.loads(Path(outputs["speed_video_record"]).read_bytes())
assert abs(speed["duration_seconds"] - 1.6) < .25, speed
assert "integratedLoudnessLUFS" in json.loads(Path(outputs["audio_analysis"]).read_bytes())
assert hashlib.sha256(source.read_bytes()).hexdigest() == before
for name in ("plan.png", "results.png"):
    assert (root / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), name
print("INTEGRA_NATIVE_REAL_VIDEOTEXT_WORKFLOW: PASS")
