"""Resolve historical transcript outputs without rewriting source artifacts."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def _owned(path, root, label="transcript"):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    root = Path(root).resolve(strict=True)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ValueError(f"{label} must be owned by this Integra project") from error
    current = path
    while True:
        if current.is_symlink():
            raise ValueError(f"{label} path must not contain symlinks")
        if current.samefile(root):
            break
        current = current.parent
    if not path.is_file():
        raise ValueError(f"{label} file is unavailable")
    return resolved


def resolve_persisted_project_path(project_dir, persisted_path, label):
    """Resolve a stored project artifact after a project-root relocation.

    A persisted path is accepted directly only when it is currently owned.  A
    legacy absolute path may be rebased only through its unique lexical
    ``projects/<this-project-uuid>`` anchor; relative paths, traversal, paths
    for another project, symlinks, and external paths stay fail-closed.
    """
    root = Path(project_dir).resolve(strict=True)
    path = Path(persisted_path) if isinstance(persisted_path, str) else None
    if path is None or not path.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    if ".." in path.parts:
        raise ValueError(f"{label} path must not contain traversal")
    try:
        return _owned(path, root, label)
    except ValueError as direct_error:
        # A path already lexically under the current root is never a legacy
        # reference. Preserve its strict containment/symlink failure instead
        # of attempting a relocation fallback.
        try:
            path.relative_to(root)
        except ValueError:
            pass
        else:
            raise direct_error
        parts = path.parts
        anchors = [index for index in range(len(parts) - 1)
                   if parts[index] == "projects" and parts[index + 1] == root.name]
        if len(anchors) != 1 or anchors[0] + 2 >= len(parts):
            raise ValueError(f"{label} must be owned by this Integra project")
        return _owned(root.joinpath(*parts[anchors[0] + 2:]), root, label)


def resolve_transcript_text(project_dir, source_id, transcript_path):
    """Return owned TXT, materializing only a content-addressed legacy projection."""
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("transcript source identity is required")
    root = Path(project_dir).resolve(strict=True)
    source = resolve_persisted_project_path(root, transcript_path, "transcript")
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
