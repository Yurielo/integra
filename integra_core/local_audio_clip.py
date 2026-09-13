"""Preserve existing audio-only clipping alongside VideoText video ownership."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .videotext_media_runtime import cut, digest


def cut_media_compatible(source: Path, target: Path, start: float, end: float) -> dict:
    # Inspect streams, not filename suffixes: MP4 can also contain audio only.
    from .user_media import ffmpeg_preflight
    ffmpeg = ffmpeg_preflight()["ffmpeg"]
    probe = Path(ffmpeg).parent / "ffprobe"
    if not probe.is_file():
        found = shutil.which("ffprobe")
        if not found: raise ValueError("ffprobe is unavailable")
        probe = Path(found)
    info = subprocess.run([str(probe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)],
                          capture_output=True, text=True, check=True, timeout=30)
    streams = json.loads(info.stdout).get("streams", [])
    if any(item.get("codec_type") == "video" for item in streams):
        return cut(source, target, start, end)
    if not any(item.get("codec_type") == "audio" for item in streams):
        raise ValueError("source has no media streams")
    if target.exists() or target.is_symlink(): raise FileExistsError("clip already exists")
    original = digest(source)
    with tempfile.TemporaryDirectory(prefix=".audio-clip-", dir=target.parent) as temporary:
        staged = Path(temporary) / "clip.mp4"
        subprocess.run([ffmpeg, "-nostdin", "-i", str(source), "-ss", str(start), "-t", str(end-start),
                        "-map", "0:a:0", "-vn", "-c:a", "aac", str(staged)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=7200)
        measured = subprocess.run([str(probe), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(staged)],
                                 capture_output=True, text=True, check=True, timeout=30)
        duration = float(json.loads(measured.stdout)["format"]["duration"])
        if abs(duration - (end-start)) > .25 or digest(source) != original:
            raise ValueError("audio clip validation failed")
        os.link(staged, target)
    return {"schema_version": "1.0", "component": "integra.legacy_audio_clip", "source_sha256": original,
            "output_sha256": digest(target), "duration_seconds": duration, "start_seconds": start, "end_seconds": end}
