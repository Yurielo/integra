"""Issue #233: bounded, no-follow materialization of the generated demo for QA.

This development-only tool never executes copied binaries or Candidate code.
Only the four literal historical links below are admissible; this is not a
general symlink resolver. A receipt is returned only after source and copy QA.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat


class QACopyError(ValueError):
    pass


@dataclass(frozen=True)
class LinkSpec:
    relative: str
    raw_target: str
    terminal: str
    chain: tuple[tuple[str, str], ...] = ()


_BIN = "artifacts/2b08196f-c7f8-43e0-bbb2-e312a654555a/seminartext-asr/bin/"
_PY = "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/bin/"
HISTORICAL_LINKS = (
    LinkSpec(_BIN + "ffmpeg", "/opt/homebrew/Cellar/ffmpeg/8.1.2_1/bin/ffmpeg",
             "/opt/homebrew/Cellar/ffmpeg/8.1.2_1/bin/ffmpeg"),
    LinkSpec(_BIN + "ffprobe", "/opt/homebrew/Cellar/ffmpeg/8.1.2_1/bin/ffprobe",
             "/opt/homebrew/Cellar/ffmpeg/8.1.2_1/bin/ffprobe"),
    LinkSpec(_BIN + "python3", "/Library/Developer/CommandLineTools/usr/bin/python3",
             _PY + "python3.9", (
                 ("/Library/Developer/CommandLineTools/usr/bin/python3",
                  "../../Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"),
                 (_PY + "python3", "python3.9"))),
    LinkSpec(_BIN + "whisper-cli", "/opt/homebrew/Cellar/whisper-cpp/1.9.2/bin/whisper-cli",
             "/opt/homebrew/Cellar/whisper-cpp/1.9.2/bin/whisper-cli"),
)
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


def _absolute(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise QACopyError("absolute, non-traversing path required")
    return path


def _directories(root_fd: int, parts: tuple[str, ...]) -> int:
    fd = os.dup(root_fd)
    try:
        for part in parts:
            if part in {"", ".", ".."} or "/" in part:
                raise QACopyError("unsafe path component")
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _directory(path: Path) -> int:
    path = _absolute(path)
    root = os.open("/", _DIRECTORY_FLAGS)
    try:
        return _directories(root, path.parts[1:])
    finally:
        os.close(root)


def _contains_inode(ancestor: int, child: int) -> bool:
    """Detect real containment, including case aliases on macOS volumes."""
    expected = os.fstat(ancestor)
    cursor = os.dup(child)
    try:
        for _ in range(1024):
            current = os.fstat(cursor)
            identity = (current.st_dev, current.st_ino)
            if identity == (expected.st_dev, expected.st_ino):
                return True
            parent = os.open("..", _DIRECTORY_FLAGS, dir_fd=cursor)
            metadata = os.fstat(parent)
            if (metadata.st_dev, metadata.st_ino) == identity:
                os.close(parent)
                return False
            os.close(cursor)
            cursor = parent
        raise QACopyError("directory ancestry exceeds bound")
    finally:
        os.close(cursor)


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_nlink,
            metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)


def _hash(fd: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _regular(parent: int, name: str) -> tuple[int, dict]:
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise QACopyError("regular non-hardlinked file required")
    fd = os.open(name, _FILE_FLAGS, dir_fd=parent)
    try:
        if _identity(os.fstat(fd)) != _identity(before):
            raise QACopyError("file identity changed while opening")
        digest, size = _hash(fd)
        if _identity(os.fstat(fd)) != _identity(before) or size != before.st_size:
            raise QACopyError("file changed while hashing")
        return fd, {"identity": _identity(before), "sha256": digest, "size": size}
    except BaseException:
        os.close(fd)
        raise


def _literal_link(parent: int, name: str, expected: str) -> tuple[int, ...]:
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISLNK(before.st_mode) or os.readlink(name, dir_fd=parent) != expected:
        raise QACopyError("historical symlink text/type mismatch")
    if _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != _identity(before):
        raise QACopyError("symlink changed while inspecting")
    return _identity(before)


def _target(spec: LinkSpec) -> tuple[int, dict]:
    chain = []
    current = spec.raw_target
    for path_text, expected in spec.chain:
        if current != path_text:
            raise QACopyError("target chain does not match literal allowlist")
        path = _absolute(Path(path_text))
        parent = _directory(path.parent)
        try:
            identity = _literal_link(parent, path.name, expected)
        finally:
            os.close(parent)
        chain.append({"path": path_text, "raw_target": expected, "identity": identity})
        current = os.path.normpath(os.path.join(str(path.parent), expected))
    if current != spec.terminal:
        raise QACopyError("target escapes exact allowlisted terminal")
    terminal = _absolute(Path(spec.terminal))
    parent = _directory(terminal.parent)
    try:
        fd, record = _regular(parent, terminal.name)
    finally:
        os.close(parent)
    record.update(terminal=spec.terminal, chain=chain)
    return fd, record


def snapshot(root: Path, specs: tuple[LinkSpec, ...] = HISTORICAL_LINKS) -> dict:
    """No-follow inventory; original raw link identities and target hashes included."""
    allowed = {spec.relative: spec for spec in specs}
    if len(allowed) != len(specs):
        raise QACopyError("duplicate link specification")
    files, directories, links = {}, {}, {}
    fd = _directory(root)
    root_identity = _identity(os.fstat(fd))

    def visit(parent: int, prefix: tuple[str, ...]) -> None:
        for name in sorted(os.listdir(parent)):
            parts = (*prefix, name)
            relative = "/".join(parts)
            metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                child = _directories(parent, (name,))
                try:
                    if _identity(os.fstat(child)) != _identity(metadata):
                        raise QACopyError("directory changed while opening")
                    directories[relative] = _identity(metadata)
                    visit(child, parts)
                    if _identity(os.fstat(child)) != _identity(metadata):
                        raise QACopyError("directory changed during inventory")
                finally:
                    os.close(child)
            elif stat.S_ISLNK(metadata.st_mode):
                if relative not in allowed:
                    raise QACopyError("unlisted source symlink: " + relative)
                spec = allowed[relative]
                identity = _literal_link(parent, name, spec.raw_target)
                target_fd, target = _target(spec)
                os.close(target_fd)
                links[relative] = {"raw_target": spec.raw_target,
                                   "source_link_identity": identity, **target}
            elif stat.S_ISREG(metadata.st_mode):
                file_fd, record = _regular(parent, name)
                os.close(file_fd)
                files[relative] = record
            else:
                raise QACopyError("unsafe source entry: " + relative)

    try:
        visit(fd, ())
        if set(links) != set(allowed):
            raise QACopyError("exact historical link set missing or replaced")
        if _identity(os.fstat(fd)) != root_identity:
            raise QACopyError("source root changed during inventory")
        return {"root": root_identity, "directories": directories, "files": files, "links": links}
    finally:
        os.close(fd)


def _copy_fd(source: int, target_parent: int, name: str, expected: dict) -> None:
    if _identity(os.fstat(source)) != expected["identity"]:
        raise QACopyError("source changed after preflight")
    output = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=target_parent)
    try:
        os.lseek(source, 0, os.SEEK_SET)
        digest, size = hashlib.sha256(), 0
        while chunk := os.read(source, 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(output, view)
                if written <= 0:
                    raise QACopyError("incomplete QA copy write")
                view = view[written:]
        os.fsync(output)
        if (digest.hexdigest(), size) != (expected["sha256"], expected["size"]):
            raise QACopyError("source bytes changed after preflight")
        if _identity(os.fstat(source)) != expected["identity"]:
            raise QACopyError("source identity changed during copy")
        # Keep executable intent only; never carry setuid/group/other permissions.
        os.fchmod(output, 0o700 if expected["identity"][2] & 0o111 else 0o600)
    finally:
        os.close(output)


def prepare_copy(source: Path, destination: Path, *, expected_parent: tuple[int, int] | None = None) -> dict:
    """Create a fresh QA project; caller must not use partial output on failure."""
    source, destination = _absolute(source), _absolute(destination)
    if source == destination or source in destination.parents or destination in source.parents:
        raise QACopyError("source/destination overlap")
    destination_parent = _directory(destination.parent)
    source_fd = None
    destination_fd = None
    try:
        parent_metadata = os.fstat(destination_parent)
        if expected_parent is not None and (parent_metadata.st_dev, parent_metadata.st_ino) != expected_parent:
            raise QACopyError("QA workspace parent changed before copy")
        source_fd = _directory(source)
        if _contains_inode(source_fd, destination_parent):
            raise QACopyError("destination is physically contained in source")
        # Reject existing files, directories and dangling links, before copying.
        try:
            os.stat(destination.name, dir_fd=destination_parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise QACopyError("QA destination already exists")
        before = snapshot(source)
        if _identity(os.fstat(source_fd)) != before["root"]:
            raise QACopyError("source root changed after preflight")
        os.mkdir(destination.name, 0o700, dir_fd=destination_parent)
        destination_fd = _directories(destination_parent, (destination.name,))
        for relative in sorted(before["directories"], key=lambda value: (value.count("/"), value)):
            parts = tuple(relative.split("/"))
            parent = _directories(destination_fd, parts[:-1])
            try:
                os.mkdir(parts[-1], 0o700, dir_fd=parent)
            finally:
                os.close(parent)
        specs = {spec.relative: spec for spec in HISTORICAL_LINKS}
        for relative, expected in sorted({**before["files"], **before["links"]}.items()):
            parts = tuple(relative.split("/"))
            parent = _directories(destination_fd, parts[:-1])
            input_fd = None
            try:
                if relative in specs:
                    source_parent = _directories(source_fd, parts[:-1])
                    try:
                        link_identity = _literal_link(source_parent, parts[-1], specs[relative].raw_target)
                    finally:
                        os.close(source_parent)
                    if link_identity != expected["source_link_identity"]:
                        raise QACopyError("source link changed after preflight")
                    input_fd, target = _target(specs[relative])
                    if target != {key: expected[key] for key in target}:
                        raise QACopyError("allowlisted target changed after preflight")
                else:
                    input_parent = _directories(source_fd, parts[:-1])
                    try:
                        input_fd, actual = _regular(input_parent, parts[-1])
                    finally:
                        os.close(input_parent)
                    if actual != expected:
                        raise QACopyError("source file changed after preflight")
                _copy_fd(input_fd, parent, parts[-1], expected)
            finally:
                if input_fd is not None:
                    os.close(input_fd)
                os.close(parent)
        if snapshot(source) != before:
            raise QACopyError("original project/target changed during QA preparation")
        copied = snapshot(destination, ())
        wanted = {path: (record["sha256"], record["size"])
                  for path, record in {**before["files"], **before["links"]}.items()}
        actual = {path: (record["sha256"], record["size"])
                  for path, record in copied["files"].items()}
        if actual != wanted or set(copied["directories"]) != set(before["directories"]):
            raise QACopyError("QA copy bytes/layout mismatch")
        return {"original_unchanged": True, "no_symlinks": True,
                "source": str(source), "destination": str(destination),
                "files_copied": len(actual), "materialized_links": before["links"],
                "original_inventory": before, "qa_only": True,
                "candidate_executed": False, "semantic_acceptance": False}
    finally:
        for fd in (source_fd, destination_fd, destination_parent):
            if fd is not None:
                os.close(fd)


def read_verified_file(root: Path, relative: str, expected: dict,
                       *, expected_root: tuple[int, int] | None = None) -> bytes:
    """Read an inventoried regular file without following path-component links."""
    root_fd = _directory(root)
    parent = None
    fd = None
    try:
        metadata = os.fstat(root_fd)
        if expected_root is not None and (metadata.st_dev, metadata.st_ino) != expected_root:
            raise QACopyError("read root changed after preflight")
        parts = tuple(relative.split("/"))
        parent = _directories(root_fd, parts[:-1])
        fd, actual = _regular(parent, parts[-1])
        if actual != expected:
            raise QACopyError("identity file changed after preflight")
        os.lseek(fd, 0, os.SEEK_SET)
        chunks = []
        while chunk := os.read(fd, 1024 * 1024):
            chunks.append(chunk)
        result = b"".join(chunks)
        if hashlib.sha256(result).hexdigest() != expected["sha256"] or _identity(os.fstat(fd)) != expected["identity"]:
            raise QACopyError("identity file changed while reading")
        return result
    finally:
        for descriptor in (fd, parent, root_fd):
            if descriptor is not None:
                os.close(descriptor)


def write_receipt(path: Path, payload: bytes, *, expected_parent: tuple[int, int] | None = None) -> None:
    """Exclusive no-follow receipt in an existing safely opened directory."""
    path = _absolute(path)
    parent = _directory(path.parent)
    fd = None
    try:
        metadata = os.fstat(parent)
        if expected_parent is not None and (metadata.st_dev, metadata.st_ino) != expected_parent:
            raise QACopyError("receipt workspace changed before publication")
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise QACopyError("incomplete receipt write")
            view = view[written:]
        os.fsync(fd)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)
