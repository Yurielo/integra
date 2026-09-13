"""Test-only subprocess fixtures; the production SeminarText script still runs."""
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
    from integra_core.seminartext_asr_runtime import _runtime, ASRError
    try:
        _runtime()
    except ASRError as error:
        raise unittest.SkipTest(str(error)) from error
    require_subtitle_runtime()
    if not (Path.home() / "whisper-models/ggml-silero-v5.1.2.bin").is_file():
        raise unittest.SkipTest("requires pinned Silero VAD model for real SeminarText CLI")


def require_subtitle_runtime():
    from integra_core.videotext_subtitles import preflight
    try:
        return preflight()
    except (ValueError, OSError) as error:
        raise unittest.SkipTest(str(error)) from error
