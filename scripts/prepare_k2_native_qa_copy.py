"""Prepare ONLY the isolated generated-demo QA copy (Issue #233).

Does not execute Candidate code, record semantic choices, or resume K2 QA.
The existing #227 native QA sequence is a separately authorized caller.
"""
import argparse
import json
import os
from pathlib import Path
import stat
from qa_source_copy import prepare_copy, snapshot, read_verified_file, write_receipt, _directory, _regular, _directories
from temp_workspace_lifecycle import MARKER, SCHEMA, _process_is_live

PROJECT_UUID = "c0b7a120-c257-4514-b077-7b6a6fce0c15"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    value = os.environ.get("INTEGRA_OWNED_WORKSPACE")
    if not value:
        raise ValueError("run only through the governed issue233-qa-copy workspace lifecycle")
    workspace = Path(value)
    if workspace.parent != Path("/private/tmp") or not workspace.name.startswith("integra-owned-issue233-qa-copy-"):
        raise ValueError("QA output must be the exact disposable /private/tmp lifecycle workspace, not product/archive data")
    descriptor = _directory(workspace)
    try:
        metadata = os.fstat(descriptor)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise ValueError("QA workspace must be exclusively current-user owned")
        workspace_identity = (metadata.st_dev, metadata.st_ino)
        marker_fd, marker_record = _regular(descriptor, MARKER)
        os.close(marker_fd)
        marker = json.loads(read_verified_file(workspace, MARKER, marker_record,
                                              expected_root=workspace_identity))
        required = {"schema_version", "artifact_type", "root", "purpose", "created_at", "run_id",
                    "expected_bytes", "reserve_bytes", "owner", "child", "state", "events"}
        if (not isinstance(marker, dict) or set(marker) != required
                or marker["schema_version"] != SCHEMA
                or marker["artifact_type"] != "integra.disposable_workspace"
                or marker["root"] != str(workspace)
                or marker["purpose"] != "issue233-qa-copy"
                or not isinstance(marker["owner"], dict)
                or not _process_is_live(marker["owner"])):
            raise ValueError("QA workspace ownership/purpose is not live and exact")
        projects = workspace / "projects"
        os.mkdir("projects", 0o700, dir_fd=descriptor)
        projects_fd = _directories(descriptor, ("projects",))
        try:
            project_metadata = os.fstat(projects_fd)
            projects_identity = (project_metadata.st_dev, project_metadata.st_ino)
        finally:
            os.close(projects_fd)
    finally:
        os.close(descriptor)
    destination = projects / PROJECT_UUID
    receipt = workspace / "qa-copy.json"
    original = Path.home() / "Library/Application Support/Integra/projects" / PROJECT_UUID
    # Inventory before reading identity: reject arbitrary links, including project.json.
    initial = snapshot(original)
    project = json.loads(read_verified_file(original, "project.json", initial["files"]["project.json"]))
    if project.get("name") != "generated-russian-speech.mp4" or project.get("project_id") != "urn:integra:project:" + PROJECT_UUID:
        raise ValueError("only the known generated speech demo is permitted")
    result = prepare_copy(original, destination, expected_parent=projects_identity)
    if result["original_inventory"] != initial:
        raise ValueError("original changed since identity validation")
    # Never overwrite an existing receipt; partial copies are not accepted evidence.
    write_receipt(receipt, (json.dumps(result, ensure_ascii=False, indent=2,
                                          sort_keys=True) + "\n").encode("utf-8"),
                  expected_parent=workspace_identity)
    # Supervisor removes the owned disposable workspace; stdout preserves evidence.
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
