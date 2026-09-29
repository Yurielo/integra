"""Deterministic, non-recursive local-source discovery for the Process picker."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .capabilities import detect_source


class FolderDiscoveryError(ValueError):
    """The selected folder cannot truthfully yield a source selection."""


def discover_folder_sources(folder_value: str) -> dict[str, Any]:
    """Return directly contained, supported regular files in stable order.

    This deliberately does not recurse. Nested directories, including Zoom
    layouts, are a separate product outcome. Hidden and non-regular entries
    are never candidates, and equal content identities are deduplicated.
    """
    if not isinstance(folder_value, str) or not folder_value.strip():
        raise FolderDiscoveryError("folder is required")
    folder = Path(folder_value).expanduser()
    if folder.is_symlink() or not folder.is_dir():
        raise FolderDiscoveryError("choose an accessible local folder")
    try:
        folder = folder.resolve(strict=True)
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
