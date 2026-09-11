#!/usr/bin/env python3
"""Closed, read-only bridge for the bundled R12 reference workflow."""

import json
import sys
from pathlib import Path


def fail(message):
    print(json.dumps({"schema_version": "1.0", "ok": False, "error": message}, sort_keys=True))
    return 2


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"workflow", "obsidian-preview", "onedrive-preview", "deferred"}:
        return fail("unsupported bridge operation")
    resources = Path(__file__).resolve().parent
    workflow = json.loads((resources / "reference_workflow.json").read_text())
    operation = sys.argv[1]
    if operation == "workflow":
        result = {"schema_version": "1.0", "ok": True, "operation": operation, "workflow": workflow}
    elif operation == "deferred":
        result = {"schema_version": "1.0", "ok": True, "operation": operation,
                  "registry": json.loads((resources / "deferred_features.json").read_text())}
    else:
        target = "Obsidian managed Vault subtree" if operation == "obsidian-preview" else "filesystem-backed OneDrive target"
        result = {"schema_version": "1.0", "ok": True, "operation": operation,
                  "state": "DRY_RUN_REFERENCE_ONLY", "target": target,
                  "writes_performed": False, "external_actions_performed": False,
                  "cloud_verified": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
