#!/usr/bin/env python3
"""Seed the two-fragment synthetic K2 fixture for one packaged GUI E2E run.

This is test-only input in the live owned GUI workspace. It creates no review
decision and does not read or modify the canonical demo, Candidate, CURRENT,
or Process Board.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from k2_qa_fixture import PROJECT_UUID, encoded, prepare
from qa_source_copy import _directory, write_receipt


PURPOSE = "issue227-k2-gui-e2e"


def main() -> int:
    workspace = Path(os.environ.get("INTEGRA_OWNED_WORKSPACE", ""))
    project = prepare(workspace, purpose=PURPOSE)
    descriptor = _directory(workspace)
    try:
        metadata = os.fstat(descriptor)
        payload = {"artifact_type": "integra.k2_gui_fixture", "qa_only": True,
                   "semantic_product_acceptance": False,
                   "project_id": "urn:integra:project:" + PROJECT_UUID,
                   "project": str(project), "reviewed": False}
        write_receipt(workspace / "issue227-k2-gui-fixture.json", encoded(payload),
                      expected_parent=(metadata.st_dev, metadata.st_ino))
    finally:
        os.close(descriptor)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
