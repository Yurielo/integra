"""Candidate-bound controlled failure -> retry recovery sanity.

The alignment executable is intentionally a test fixture here.  This probe
checks retry/state/ASR-reuse semantics only; real WhisperX coverage is provided
by native_word_timeline_minimal_path_probe.py.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


app, root = (Path(value).resolve() for value in sys.argv[1:])
root.mkdir(parents=True, exist_ok=False)
source = root / "synthetic.wav"
source.write_bytes(b"isolated retry fixture, state semantics only")
before = hashlib.sha256(source.read_bytes()).hexdigest()
ffmpeg = root / "ffmpeg"
ffmpeg.write_text(f"#!{sys.executable}\nimport shutil,sys\na=sys.argv[1:]; shutil.copyfile(a[a.index('-i')+1], a[-1])\n")
whisper = root / "whisper-cli"
whisper.write_text(f"#!{sys.executable}\nfrom pathlib import Path\na=__import__('sys').argv; p=a[a.index('-of')+1]; text='Hello Integra, this is a complete test sentence.'; Path(p+'.txt').write_text(text+'\\n'); Path(p+'.srt').write_text('1\\n00:00:00,000 --> 00:00:01,000\\n'+text+'\\n')\n")
probe = root / "ffprobe"
probe.write_text("#!/bin/sh\necho 1.0\n")
model = root / "model.bin"; model.write_bytes(b"test-only-model")
alignment = root / "alignment-python"
attempts = root / "alignment-attempts.txt"
alignment.write_text(f"#!{sys.executable}\nimport json,sys\nfrom pathlib import Path\nif '--version' in sys.argv: print('Python 3.13.0'); raise SystemExit(0)\nif '-c' in sys.argv: print('READY'); raise SystemExit(0)\np=Path({str(attempts)!r}); n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n))\nif n == 1: print('deliberate test-only alignment failure',file=sys.stderr); raise SystemExit(23)\nout=Path(sys.argv[sys.argv.index('--output')+1]); out.write_text(json.dumps({{'capability':'word_timeline','words':[{{'text':'fixture','alignment_status':'ALIGNED'}}]}}))\n")
for tool in (ffmpeg, whisper, probe, alignment): tool.chmod(0o700)
environment = {key: value for key, value in os.environ.items() if not key.startswith("INTEGRA_")}
environment.update({
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "INTEGRA_APP_DATA_ROOT": str(root / "app-data"),
    "INTEGRA_NATIVE_SMOKE_DIR": str(root),
    "INTEGRA_NATIVE_RETRY_SMOKE": "1",
    "INTEGRA_FFMPEG": str(ffmpeg),
    "INTEGRA_WHISPER_CLI": str(whisper),
    "INTEGRA_FFPROBE": str(probe),
    "INTEGRA_WHISPER_MODEL": str(model),
    "INTEGRA_WORD_ALIGNMENT_PYTHON": str(alignment),
    "PYTHONDONTWRITEBYTECODE": "1",
})
try:
    subprocess.run([str(app / "Contents/MacOS/Integra"), "--ui-probe-source", str(source),
                    "--ui-probe-output", "word_timeline"], env=environment, check=True, timeout=300)
    failed = json.loads((root / "failed-run.json").read_bytes())
    completed = json.loads((root / "native-run.json").read_bytes())
    assert failed["state"] == "FAILED" and completed["state"] == "COMPLETED"
    assert failed["run_id"] != completed["run_id"]
    assert attempts.read_text() == "2"
    result = completed["source_results"][0]
    assert result["asr_reuse"]["state"] == "REUSED"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    evidence = next(Path(result["outputs"]["word_timeline"]).parent.glob("*.worker-evidence.json"))
    record = json.loads(evidence.read_bytes())
    print(json.dumps({"failed_run": failed["run_id"], "completed_run": completed["run_id"],
                      "candidate_id": record["candidate_id"], "bundle_digest": record["bundle_digest"],
                      "evidence": str(evidence)}, sort_keys=True))
finally:
    subprocess.run([sys.executable, str(app / "Contents/Resources/bridge.py"), "shutdown-active-runs"],
                   input="{}", text=True, capture_output=True, env=environment, check=True, timeout=30)
