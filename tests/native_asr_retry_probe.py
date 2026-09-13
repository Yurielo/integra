"""Native retry acceptance; synthetic ASR/alignment executables, NOT quality QA.

The pinned SeminarText pipeline, cache, bridge and actual native buttons run.
A test alignment executable fails once after ASR, then returns a fixture.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.asr_tools import media_environment

app, root = [Path(value).resolve() for value in sys.argv[1:]]
root.mkdir(parents=True, exist_ok=False)
source = root / "synthetic.wav"
source.write_bytes(b"isolated retry fixture, not real speech")
before = hashlib.sha256(source.read_bytes()).hexdigest()
overrides = media_environment(root)
counter = root / "recognizer-count.txt"
whisper = Path(overrides["INTEGRA_WHISPER_CLI"])
original = whisper.read_text()
first, rest = original.split("\n", 1)
whisper.write_text(first + "\nfrom pathlib import Path\n" +
                   f"counter=Path({str(counter)!r})\ncounter.write_text(str(int(counter.read_text())+1) if counter.exists() else '1')\n" + rest)
alignment = root / "alignment-python"
attempts = root / "alignment-attempts.txt"
alignment.write_text(f"#!{sys.executable}\n" + f"""import json, sys
from pathlib import Path
if '--version' in sys.argv:
    print('Python 3.13.0'); sys.exit(0)
if '-c' in sys.argv:
    print('READY'); sys.exit(0)
attempts=Path({str(attempts)!r})
count=int(attempts.read_text())+1 if attempts.exists() else 1
attempts.write_text(str(count))
if count==1:
    print('Deliberate test-only alignment failure', file=sys.stderr); sys.exit(23)
output=Path(sys.argv[sys.argv.index('--output')+1])
output.write_text(json.dumps({{'capability':'word_timeline','words':[{{'text':'fixture','alignment_status':'ALIGNED'}}]}}))
""")
alignment.chmod(0o700)
environment = {key: value for key, value in os.environ.items() if not key.startswith("INTEGRA_")}
environment.update(overrides)
environment.update(INTEGRA_APP_DATA_ROOT=str(root / "app-data"), INTEGRA_NATIVE_SMOKE_DIR=str(root),
                   INTEGRA_NATIVE_RETRY_SMOKE="1", INTEGRA_WORD_ALIGNMENT_PYTHON=str(alignment),
                   PYTHONDONTWRITEBYTECODE="1")
try:
    subprocess.run([str(app / "Contents/MacOS/Integra"), "--ui-probe-source", str(source),
                    "--ui-probe-output", "word_timeline"], env=environment, check=True, timeout=200)
    failed = json.loads((root / "failed-run.json").read_bytes())
    completed = json.loads((root / "native-run.json").read_bytes())
    assert failed["state"] == "FAILED" and completed["state"] == "COMPLETED", (failed, completed)
    assert failed["run_id"] != completed["run_id"]
    assert counter.read_text() == "1", "native retry repeated ASR"
    assert attempts.read_text() == "2", "failed downstream stage was not retried"
    result = completed["source_results"][0]
    assert result["asr_reuse"]["state"] == "REUSED", result
    assert Path(result["outputs"]["transcript"]).read_text().strip()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    for name in ("plan.png", "before-retry.png", "results.png"):
        assert (root / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    print("INTEGRA_NATIVE_VERIFIED_ASR_RETRY: PASS")
finally:
    # Clean only nonce/birth-verified workers belonging to this isolated root.
    subprocess.run([sys.executable, str(app / "Contents/Resources/bridge.py"), "shutdown-active-runs"],
                   input="{}", text=True, capture_output=True, env=environment, check=True, timeout=30)
