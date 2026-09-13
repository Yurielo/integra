"""Harmless owned-process cancellation; no models, private files or network."""
import json
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from integra_core import shutdown_runtime as shutdown
from integra_core.application_runtime import read_run


class ShutdownRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "runs").mkdir()
        self.run_id = f"urn:integra:run:{uuid.uuid4()}"
        self.path = self.root / "runs" / (self.run_id.split(":")[-1] + ".json")
        self.path.write_text(json.dumps({"run_id": self.run_id, "state": "RUNNING", "source_results": []}))
        (self.root / "jobs.json").write_text(json.dumps({"jobs": [
            {"run_id": self.run_id, "state": "RUNNING"},
            {"run_id": "other-run", "state": "RUNNING"},
        ]}))

    def worker(self, code="import time; time.sleep(30)"):
        nonce = uuid.uuid4().hex
        process = subprocess.Popen([sys.executable, "-c", code, "--integra-run-owner", nonce],
                                   start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def cleanup():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        self.addCleanup(cleanup)
        shutdown.register_worker(self.path, process.pid, nonce)
        return process

    def test_cancel_waits_for_worker_and_preserves_other_jobs_and_input(self):
        worker = self.worker()
        source = self.root / "source.txt"; source.write_text("untouched source")
        result = shutdown.cancel_run(self.root, self.run_id)
        self.assertEqual(result["state"], "CANCELLED")
        self.assertIsNotNone(worker.poll())
        self.assertEqual(source.read_text(), "untouched source")
        jobs = json.loads((self.root / "jobs.json").read_bytes())["jobs"]
        self.assertEqual([item["state"] for item in jobs], ["CANCELLED", "RUNNING"])

    def test_legacy_pid_is_not_authority_to_signal_unrelated_process(self):
        worker = self.worker()
        shutdown.ownership_path(self.path).unlink()
        record = json.loads(self.path.read_bytes()); record["worker_pid"] = worker.pid
        self.path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "no verified worker identity"):
            shutdown.cancel_run(self.root, self.run_id)
        self.assertIsNone(worker.poll())
        self.assertEqual(read_run(self.root, self.run_id)["state"], "RUNNING")

    def test_reused_pid_identity_fails_without_signalling(self):
        worker = self.worker()
        owner_path = shutdown.ownership_path(self.path)
        owner = json.loads(owner_path.read_bytes()); owner["process"]["started"] = "other process start"
        owner_path.write_text(json.dumps(owner))
        with self.assertRaisesRegex(ValueError, "identity changed"), patch.object(os, "kill") as kill:
            shutdown.cancel_run(self.root, self.run_id)
        kill.assert_not_called()
        self.assertIsNone(worker.poll())

    def test_timeout_never_claims_confirmed_cancellation(self):
        worker = self.worker()
        with patch.object(shutdown, "_signal_owned"), self.assertRaisesRegex(ValueError, "not confirmed"):
            shutdown.cancel_run(self.root, self.run_id, timeout=.05)
        self.assertIsNone(worker.poll())
        self.assertEqual(read_run(self.root, self.run_id)["state"], "RUNNING")
        self.assertTrue(shutdown.cancellation_path(self.path).is_file())

    def test_completed_race_preserves_completed_artifact_record(self):
        worker = self.worker()
        original = shutdown._signal_owned
        def finish_then_signal(identity, sig):
            self.path.write_text(json.dumps({"run_id": self.run_id, "state": "COMPLETED",
                                            "source_results": [{"outputs": {"text": "retained"}}]}))
            original(identity, sig)
        with patch.object(shutdown, "_signal_owned", side_effect=finish_then_signal):
            result = shutdown.cancel_run(self.root, self.run_id)
        self.assertIsNotNone(worker.poll())
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual(result["source_results"][0]["outputs"]["text"], "retained")

    def test_finished_record_with_live_worker_still_requires_cleanup(self):
        worker = self.worker()
        self.path.write_text(json.dumps({"run_id": self.run_id, "state": "COMPLETED"}))
        record = read_run(self.root, self.run_id)
        self.assertTrue(shutdown.requires_shutdown(self.path, record))
        self.assertEqual(shutdown.cancel_run(self.root, self.run_id)["state"], "COMPLETED")
        self.assertIsNotNone(worker.poll())

    def test_worker_gone_without_cleanup_evidence_is_not_reported_cancelled(self):
        worker = self.worker(); worker.terminate(); worker.wait(timeout=5)
        with self.assertRaisesRegex(ValueError, "without verified cleanup evidence"):
            shutdown.cancel_run(self.root, self.run_id)
        self.assertEqual(read_run(self.root, self.run_id)["state"], "RUNNING")

    def test_cancellation_marker_survives_progress_record_updates(self):
        from integra_core.user_media import _is_run_cancelled
        shutdown.cancellation_path(self.path).touch()
        self.path.write_text(json.dumps({"run_id": self.run_id, "state": "RUNNING", "progress": 50}))
        self.assertTrue(_is_run_cancelled(self.root, self.run_id))

    def wait_for_file(self, path):
        deadline = time.monotonic() + 5
        while not path.is_file() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(path.is_file(), str(path))

    def test_termination_handler_cannot_spawn_an_untracked_session(self):
        ready = self.root / "ready"; child_pid = self.root / "child.pid"
        handler = ("def stop(*args):\n"
                   " child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],start_new_session=True)\n"
                   f" Path({str(child_pid)!r}).write_text(str(child.pid))\n"
                   " os._exit(0)\n")
        code = (f"import os,signal,subprocess,sys,time; from pathlib import Path; exec({handler!r}); "
                f"signal.signal(signal.SIGTERM,stop); Path({str(ready)!r}).touch(); time.sleep(30)")
        worker = self.worker(code)
        self.wait_for_file(ready)
        try:
            result = shutdown.cancel_run(self.root, self.run_id)
            self.assertEqual(result["state"], "CANCELLED")
            self.assertIsNotNone(worker.poll())
            self.assertFalse(child_pid.exists(), "Termination handler spawned a new session")
        finally:
            if child_pid.is_file():
                identity = shutdown.process_snapshot().get(int(child_pid.read_text()))
                if identity is not None:
                    shutdown._signal_owned(identity, signal.SIGKILL)

    def test_owned_child_exec_during_capture_is_still_stopped(self):
        child_pid = self.root / "child.pid"; trigger = self.root / "exec-trigger"
        wait_code = f"while not Path({str(trigger)!r}).exists(): time.sleep(.01)"
        child_code = (f"import os,time; from pathlib import Path; Path({str(child_pid)!r}).write_text(str(os.getpid())); "
                      f"exec({wait_code!r}); os.execl('/bin/sleep','sleep','30')")
        # repr keeps the leader's command single-line for precise ps identity.
        worker = self.worker(f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child_code!r}],start_new_session=True); time.sleep(30)")
        self.wait_for_file(child_pid)
        pid = int(child_pid.read_text())
        child_identity = shutdown.process_snapshot()[pid]
        original = shutdown._signal_owned
        switched = False
        def exec_before_stop(identity, sig):
            nonlocal switched
            if identity["pid"] == pid and sig == signal.SIGSTOP and not switched:
                trigger.touch(); switched = True
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    current = shutdown.process_snapshot().get(pid)
                    if current and current["command"] != child_identity["command"]:
                        break
                    time.sleep(.01)
                self.assertNotEqual(current["command"], child_identity["command"])
            original(identity, sig)
        try:
            with patch.object(shutdown, "_signal_owned", side_effect=exec_before_stop):
                result = shutdown.cancel_run(self.root, self.run_id)
            self.assertTrue(switched)
            self.assertEqual(result["state"], "CANCELLED")
            self.assertNotIn(pid, shutdown.process_snapshot())
            self.assertIsNotNone(worker.poll())
        finally:
            original(child_identity, signal.SIGKILL)

    def test_bridge_rejects_new_run_while_shutdown_lock_is_held(self):
        app_data = self.root / "app-data"; app_data.mkdir()
        bridge = Path(__file__).resolve().parents[1] / "macos/Resources/bridge.py"
        with (app_data / ".run-lifecycle.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = subprocess.run([sys.executable, str(bridge), "execute-plan"],
                                    input=json.dumps({"name": "Must not start", "plan": {}}),
                                    capture_output=True, text=True, timeout=5,
                                    env={**os.environ, "INTEGRA_APP_DATA_ROOT": str(app_data)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shutdown is in progress", json.loads(result.stdout)["error"])
        self.assertFalse((app_data / "projects").exists())

    def test_shutdown_waits_for_start_lock_before_reporting_ready(self):
        app_data = self.root / "app-data"; app_data.mkdir()
        bridge = Path(__file__).resolve().parents[1] / "macos/Resources/bridge.py"
        with (app_data / ".run-lifecycle.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            process = subprocess.Popen([sys.executable, str(bridge), "shutdown-active-runs"],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, env={**os.environ, "INTEGRA_APP_DATA_ROOT": str(app_data)})
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    process.communicate("{}", timeout=.3)
                fcntl.flock(lock, fcntl.LOCK_UN)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(json.loads(stdout)["result"]["state"], "SHUTDOWN_READY")
            finally:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
