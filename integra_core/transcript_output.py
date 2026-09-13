"""Resolve historical transcript outputs without rewriting source artifacts."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def _owned(path, root):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("transcript path must be absolute")
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    current = path
    while not current.samefile(root):
        if current.is_symlink():
            raise ValueError("transcript path must not contain symlinks")
        current = current.parent
    if not path.is_file():
        raise ValueError("transcript file is unavailable")
    return resolved


def resolve_transcript_text(project_dir, source_id, transcript_path):
    """Return owned TXT, materializing only a content-addressed legacy projection."""
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("transcript source identity is required")
    root = Path(project_dir).resolve(strict=True)
    source = _owned(transcript_path, root)
    if source.suffix.lower() == ".txt":
        source.read_text(encoding="utf-8")
        return str(source)
    if source.suffix.lower() != ".json":
        raise ValueError("unsupported transcript format")
    original = source.read_bytes()
    record = json.loads(original)
    if (not isinstance(record, dict) or record.get("schema_version") != "1.0"
            or record.get("source_id") != source_id):
        raise ValueError("legacy transcript identity differs")
    segments = record.get("segments")
    if (not isinstance(segments, list) or not segments
            or any(not isinstance(item, dict) or not isinstance(item.get("text"), str) for item in segments)):
        raise ValueError("legacy transcript segments are invalid")
    payload = ("\n".join(item["text"] for item in segments) + "\n").encode("utf-8")
    directory = root / "transcript-text"
    if directory.is_symlink():
        raise ValueError("transcript projection directory is unsafe")
    directory.mkdir(exist_ok=True)
    target = directory / (hashlib.sha256(original).hexdigest() + ".txt")
    # Exclusive hard-link promotion never overwrites an edited file or symlink.
    with tempfile.TemporaryDirectory(prefix=".text-", dir=directory) as temporary:
        staged = Path(temporary) / "transcript.txt"
        staged.write_bytes(payload)
        try:
            os.link(staged, target)
        except FileExistsError:
            pass
    if _owned(target, root).read_bytes() != payload:
        raise ValueError("existing transcript text differs; no file was overwritten")
    return str(target)
