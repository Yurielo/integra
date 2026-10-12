#!/usr/bin/env python3
"""Materialize one verified retained Candidate into an owned QA execution copy.

Retained archive bytes are evidence, never an executable test location.  This
helper verifies their immutable identity before copying them only into the
live, disposable workspace created by ``temp_workspace_lifecycle``.  The
supervisor owns deletion of that workspace after the caller finishes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat

from archive_execution_guard import require_execution_path
from candidate_archive import verify_archive
from qa_source_copy import _directory, _regular, read_verified_file, write_receipt
from temp_workspace_lifecycle import MARKER, SCHEMA, _process_is_live


PURPOSE = "issue227-k2-gui-e2e"


def _workspace() -> tuple[Path, tuple[int, int]]:
    value = os.environ.get("INTEGRA_OWNED_WORKSPACE")
    if not value:
        raise ValueError("Candidate execution copy requires an owned workspace")
    root = Path(value).resolve(strict=True)
    if root.parent != Path("/private/tmp") or not root.name.startswith("integra-owned-" + PURPOSE + "-"):
        raise ValueError("Candidate execution copy requires the exact governed QA workspace")
    descriptor = _directory(root)
    try:
        metadata = os.fstat(descriptor)
        identity = (metadata.st_dev, metadata.st_ino)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise ValueError("Candidate execution workspace ownership is not exclusive")
        marker_fd, record = _regular(descriptor, MARKER)
        os.close(marker_fd)
        marker = json.loads(read_verified_file(root, MARKER, record, expected_root=identity))
        required = {"schema_version", "artifact_type", "root", "purpose", "created_at", "run_id",
                    "expected_bytes", "reserve_bytes", "owner", "child", "state", "events"}
        if (not isinstance(marker, dict) or set(marker) != required
                or marker.get("schema_version") != SCHEMA
                or marker.get("artifact_type") != "integra.disposable_workspace"
                or marker.get("root") != str(root) or marker.get("purpose") != PURPOSE
                or not _process_is_live(marker.get("owner"))):
            raise ValueError("Candidate execution workspace marker is not live and exact")
        return root, identity
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--bundle-digest", required=True)
    parser.add_argument("--manifest-digest", required=True)
    args = parser.parse_args()
    root, identity = _workspace()
    expected = {"candidate_id": args.candidate_id, "bundle_digest": args.bundle_digest,
                "manifest_digest": args.manifest_digest}
    receipt = verify_archive(args.archive, expected)
    source = Path(receipt["archive_path"]) / "Integra.app"
    destination = root / "execution" / "Integra.app"
    if destination.exists() or destination.parent.exists():
        raise ValueError("owned execution destination must be absent before materialization")
    # The verified archive admits regular files/directories only; a new copy
    # keeps its immutable identity while never making retained bytes executable.
    destination.parent.mkdir(mode=0o700)
    shutil.copytree(source, destination, symlinks=False, copy_function=shutil.copy2)
    require_execution_path(destination)
    embedded = destination / "Contents/Resources/candidate-manifest.json"
    copied = json.loads(embedded.read_text(encoding="utf-8"))
    if (copied.get("candidate_id") != args.candidate_id
            or copied.get("bundle", {}).get("digest") != args.bundle_digest):
        raise ValueError("execution copy identity differs from verified archive")
    target = root / "candidate-execution-copy.json"
    payload = {"artifact_type": "integra.candidate_execution_copy", "qa_only": True,
               "archive": receipt["archive_path"], "execution_app": str(destination),
               "candidate": expected, "archive_inventory_sha256": receipt["inventory_sha256"]}
    write_receipt(target, (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(),
                  expected_parent=identity)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
