"""Current-main recovery contract regressions for Issue #161."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import uuid
import unittest

from integra_core import shutdown_runtime as shutdown


class RecoveryContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "projects" / "project"
        (self.project / "runs").mkdir(parents=True)
        (self.project / "jobs.json").write_text(json.dumps({"jobs": []}))

    def run_record(self, state="RUNNING"):
        run_id = "urn:integra:run:11111111-1111-4111-8111-111111111111"
        (self.project / "runs" / "11111111-1111-4111-8111-111111111111.json").write_text(
            json.dumps({
                "schema_version": "1.0",
                "run_id": run_id,
                "state": state,
                "current_stage": "transcript",
                "source_results": [{"source_id": "source", "state": "COMPLETED",
                                    "outputs": {"transcript": "preserve-me"}}],
                "created_at": "2026-09-22T00:00:00Z",
            })
        )
        return run_id

    def test_stale_running_is_reconciled_without_erasing_completed_upstream(self):
        run_id = self.run_record()
        (self.project / "jobs.json").write_text(json.dumps({"jobs": [{"run_id": run_id, "state": "RUNNING"}]}))
        changed = shutdown.reconcile_stale_runs(self.root)
        self.assertEqual(changed, 1)
        record = json.loads(next((self.project / "runs").glob("*.json")).read_bytes())
        self.assertEqual(record["state"], "FAILED")
        self.assertEqual(record["recovery"]["classification"], "STALE_RUNNING_RECONCILED")
        self.assertEqual(record["source_results"][0]["outputs"]["transcript"], "preserve-me")
        self.assertEqual(json.loads((self.project / "jobs.json").read_bytes())["jobs"][0]["state"], "FAILED")

    def test_cancelled_marker_reconciles_as_cancelled(self):
        run_id = self.run_record()
        run_path = next((self.project / "runs").glob("*.json"))
        run_path.with_suffix(".cancel").touch()
        shutdown.reconcile_stale_runs(self.root)
        record = json.loads(run_path.read_bytes())
        self.assertEqual(record["state"], "CANCELLED")
        self.assertEqual(record["recovery"]["classification"], "CANCELLED_AFTER_INTERRUPTION")

    def test_bounded_plan_timeout_is_enforced(self):
        with self.assertRaises(shutdown.RunTimedOut):
            shutdown.run_with_timeout(lambda: time.sleep(0.2), 0.01)

    def test_bridge_recent_runs_reconciles_stale_state_on_startup(self):
        """The GUI-facing recent-runs path must not surface stale RUNNING."""
        import importlib.util
        bridge_path = Path(__file__).parents[1] / "macos/Resources/bridge.py"
        spec = importlib.util.spec_from_file_location("integra_issue161_bridge", bridge_path)
        bridge = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(bridge)
        project_id = str(uuid.uuid4())
        project_dir = self.root / "projects" / project_id
        (project_dir / "runs").mkdir(parents=True)
        (project_dir / "project.json").write_text(json.dumps({
            "schema_version": "1.0", "project_id": f"urn:integra:project:{project_id}",
            "name": "startup reconciliation", "created_at": "2026-09-22T00:00:00Z",
        }))
        (project_dir / "jobs.json").write_text(json.dumps({"jobs": []}))
        run_id = f"urn:integra:run:{uuid.uuid4()}"
        run_path = project_dir / "runs" / run_id.removeprefix("urn:integra:run:")
        run_path = run_path.with_suffix(".json")
        run_path.write_text(json.dumps({
            "schema_version": "1.0", "run_id": run_id, "state": "RUNNING",
            "current_stage": "transcript", "source_results": [],
            "created_at": "2026-09-22T00:00:00Z",
        }))
        recent = bridge._recent_runs(self.root)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["run"]["state"], "FAILED")
        self.assertEqual(recent[0]["run"]["recovery"]["classification"], "STALE_RUNNING_RECONCILED")


if __name__ == "__main__":
    unittest.main()
