"""Test-only subprocess fixtures; the production SeminarText script still runs."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest


TRANSCRIPT = "Hello Integra, this is a complete test sentence."


def media_environment(root: Path):
    require_asr_runtime()
    ffmpeg = root / "ffmpeg"
    ffmpeg.write_text(f"#!{sys.executable}\n" + """import sys, shutil
args = sys.argv[1:]
source = args[args.index('-i') + 1]
output = args[-1].replace('%04d', '0000')
shutil.copyfile(source, output)
""")
    whisper = root / "whisper-cli"
    whisper.write_text(f"#!{sys.executable}\n" + f"""import sys
from pathlib import Path
args = sys.argv[1:]
prefix = args[args.index('-of') + 1]
Path(prefix + '.txt').write_text({TRANSCRIPT!r} + '\\n')
Path(prefix + '.srt').write_text('1\\n00:00:00,000 --> 00:00:01,250\\n' + {TRANSCRIPT!r} + '\\n')
""")
    for tool in (ffmpeg, whisper):
        tool.chmod(0o700)
    probe = root / "ffprobe"
    probe.write_text("#!/bin/sh\necho 1.25\n")
    probe.chmod(0o700)
    model = root / "model.bin"
    model.write_bytes(b"test-only model")
    return {"INTEGRA_FFMPEG": str(ffmpeg), "INTEGRA_WHISPER_CLI": str(whisper),
            "INTEGRA_WHISPER_MODEL": str(model)}


def require_asr_runtime():
    candidate = os.environ.get("INTEGRA_CANDIDATE_APP")
    if candidate:
        # Candidate-bound native probes execute the bundled bridge, not this
        # source worktree.  A clean source checkout is deliberately not a
        # prerequisite when the exact Candidate runtime is available.
        root = Path(candidate).resolve(strict=True) / "Contents/Resources/runtime/seminartext"
        manifest = Path(candidate).resolve(strict=True) / "Contents/Resources/candidate-manifest.json"
        try:
            identity = json.loads(manifest.read_text(encoding="utf-8"))["candidate_id"]
            expected = {
                "seminartext": "30d8c1bd6f5ca717391b168cba71228a030009feaec4eb443bb1e76dab230a6c",
                "SEMINARTEXT_VERSION": "e1d49c569ae09b2ede16e2d83820a3809b35eb6c44c13ba9b5330598d6b8f43c",
            }
            if not identity.startswith("candidate-v1-") or any(
                not (root / name).is_file()
                or hashlib.sha256((root / name).read_bytes()).hexdigest() != digest
                for name, digest in expected.items()
            ):
                raise ValueError("Candidate bundled SeminarText runtime differs from pinned bytes")
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise unittest.SkipTest(str(error)) from error
        require_subtitle_runtime()
        if not (Path.home() / "whisper-models/ggml-silero-v5.1.2.bin").is_file():
            raise unittest.SkipTest("requires pinned Silero VAD model for real SeminarText CLI")
        return
    from integra_core.seminartext_asr_runtime import _runtime, ASRError
    try:
        _runtime()
    except ASRError as error:
        raise unittest.SkipTest(str(error)) from error
    require_subtitle_runtime()
    if not (Path.home() / "whisper-models/ggml-silero-v5.1.2.bin").is_file():
        raise unittest.SkipTest("requires pinned Silero VAD model for real SeminarText CLI")


def require_subtitle_runtime():
    candidate = os.environ.get("INTEGRA_CANDIDATE_APP")
    if candidate:
        worker = (
            Path(candidate).resolve(strict=True)
            / "Contents/Resources/runtime/videotext/translation-worker"
        )
        expected = "22ba7bbfd827a1f2937f3757070b74b2e5d4d1200ebea954c48c1eaac1162d28"
        try:
            if not worker.is_file() or hashlib.sha256(worker.read_bytes()).hexdigest() != expected:
                raise ValueError("Candidate bundled VideoText runtime differs from pinned bytes")
        except (OSError, ValueError) as error:
            raise unittest.SkipTest(str(error)) from error
        return
    from integra_core.videotext_subtitles import preflight
    try:
        return preflight()
    except (ValueError, OSError) as error:
        raise unittest.SkipTest(str(error)) from error
