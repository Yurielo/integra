"""Deterministic, non-recursive local-source discovery for the Process picker."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .capabilities import detect_source


class FolderDiscoveryError(ValueError):
    """The selected folder cannot truthfully yield a source selection."""


_ZOOM_IGNORED_DIRECTORIES = frozenset({
    "audio record", "audio records", "audio_record", "audio_records",
    "separate audio", "separate_audio", "individual audio", "individual_audio",
    "participants", "participant audio", "participant_audio", "chat",
    "transcripts", "transcript",
})
_S07_AUDIO_SUFFIXES = frozenset({".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"})
_S07_VIDEO_SUFFIXES = frozenset({".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"})
_S07_MEDIA_SUFFIXES = _S07_AUDIO_SUFFIXES | _S07_VIDEO_SUFFIXES


def _accessible_directory(folder_value: str) -> Path:
    if not isinstance(folder_value, str) or not folder_value.strip():
        raise FolderDiscoveryError("folder is required")
    folder = Path(folder_value).expanduser()
    if folder.is_symlink() or not folder.is_dir():
        raise FolderDiscoveryError("choose an accessible local folder")
    try:
        return folder.resolve(strict=True)
    except OSError as error:
        raise FolderDiscoveryError("cannot read the selected folder") from error


def discover_folder_sources(folder_value: str) -> dict[str, Any]:
    """Return directly contained, supported regular files in stable order.

    This deliberately does not recurse. Nested directories, including Zoom
    layouts, are a separate product outcome. Hidden and non-regular entries
    are never candidates, and equal content identities are deduplicated.
    """
    folder = _accessible_directory(folder_value)
    try:
        entries = sorted(folder.iterdir(), key=lambda item: (item.name.casefold(), item.name))
    except OSError as error:
        raise FolderDiscoveryError("cannot read the selected folder") from error

    sources: list[dict[str, Any]] = []
    ignored: list[dict[str, str]] = []
    source_ids: set[str] = set()
    for entry in entries:
        if entry.name.startswith("."):
            ignored.append({"name": entry.name, "reason": "HIDDEN"})
            continue
        if entry.is_symlink() or not entry.is_file():
            ignored.append({"name": entry.name, "reason": "NOT_REGULAR_FILE"})
            continue
        if not os.access(entry, os.R_OK):
            ignored.append({"name": entry.name, "reason": "UNREADABLE"})
            continue
        try:
            source = detect_source(str(entry))
        except (OSError, ValueError):
            ignored.append({"name": entry.name, "reason": "UNSUPPORTED"})
            continue
        if source["source_id"] in source_ids:
            ignored.append({"name": entry.name, "reason": "DUPLICATE_CONTENT"})
            continue
        source_ids.add(source["source_id"])
        source["folder_discovery"] = {
            "folder_path": str(folder), "folder_name": folder.name,
            "recursive": False, "ordering": "filename_casefold_ascending",
            "ordinal": len(sources) + 1,
        }
        sources.append(source)
    return {
        "schema_version": "1.0", "folder": {"path": str(folder), "name": folder.name},
        "recursive": False, "ordering": "filename_casefold_ascending",
        "sources": sources, "ignored": ignored,
    }


def discover_zoom_folder_sources(folder_value: str) -> dict[str, Any]:
    """Apply the pinned S07 Zoom recording selection contract.

    One recording enters the Process plan for every eligible media directory:
    ``audio_only.m4a`` wins, otherwise the largest audio wins, otherwise the
    largest video wins. The normal source detector remains the final admission
    gate, so unsupported, unreadable, or symlinked files cannot enter a plan.
    """
    folder = _accessible_directory(folder_value)
    candidates: list[tuple[Path, list[Path]]] = []
    ignored: list[dict[str, str]] = []
    try:
        for root, names, filenames in os.walk(folder, followlinks=False):
            names[:] = sorted(
                [name for name in names if not name.startswith(".")
                 and name.casefold() not in _ZOOM_IGNORED_DIRECTORIES],
                key=lambda name: (name.casefold(), name),
            )
            directory = Path(root)
            if any(part.casefold() in _ZOOM_IGNORED_DIRECTORIES for part in directory.parts):
                continue
            files = []
            for name in filenames:
                if name.startswith("."):
                    ignored.append({"name": str((directory / name).relative_to(folder)), "reason": "HIDDEN"})
                    continue
                path = directory / name
                if path.is_symlink() or not path.is_file():
                    ignored.append({"name": str(path.relative_to(folder)), "reason": "NOT_REGULAR_FILE"})
                    continue
                if not os.access(path, os.R_OK):
                    ignored.append({"name": str(path.relative_to(folder)), "reason": "UNREADABLE"})
                    continue
                try:
                    source = detect_source(str(path))
                except (OSError, ValueError):
                    ignored.append({"name": str(path.relative_to(folder)), "reason": "UNSUPPORTED"})
                    continue
                if source["kind"] == "MEDIA" and path.suffix.casefold() in _S07_MEDIA_SUFFIXES:
                    files.append(path)
            if files:
                candidates.append((directory, files))
    except OSError as error:
        raise FolderDiscoveryError("cannot read the selected Zoom folder") from error

    sources: list[dict[str, Any]] = []
    for directory, files in sorted(candidates, key=lambda item: str(item[0]).casefold()):
        available: list[tuple[Path, dict[str, Any], int]] = []
        for path in files:
            try:
                available.append((path, detect_source(str(path)), path.stat().st_size))
            except (OSError, ValueError):
                ignored.append({"name": str(path.relative_to(folder)), "reason": "UNREADABLE"})
        if not available:
            continue
        audio_only = [item for item in available if item[0].name.casefold() == "audio_only.m4a"]
        audios = [item for item in available if item[0].suffix.casefold() in _S07_AUDIO_SUFFIXES]
        videos = [item for item in available if item[0].suffix.casefold() in _S07_VIDEO_SUFFIXES]
        selected, source, _ = max(
            audio_only or audios or videos,
            key=lambda item: (item[2], item[0].name.casefold(), item[0].name),
        )
        for alternative in files:
            if alternative != selected:
                ignored.append({"name": str(alternative.relative_to(folder)), "reason": "SECONDARY_REPRESENTATION"})
        source["zoom_discovery"] = {
            "folder_path": str(folder), "folder_name": folder.name,
            "recognition": "ZOOM_RECORDING_FOLDER_S07", "recursive": True,
            "ordering": "recording_directory_path_casefold_ascending",
            "recording_directory": str(directory.relative_to(folder)) or ".",
            "ordinal": len(sources) + 1,
        }
        sources.append(source)
    return {
        "schema_version": "1.0", "folder": {"path": str(folder), "name": folder.name},
        "recognition": "ZOOM_RECORDING_FOLDER_S07", "recursive": True,
        "ordering": "recording_directory_path_casefold_ascending",
        "sources": sources, "ignored": ignored,
    }
