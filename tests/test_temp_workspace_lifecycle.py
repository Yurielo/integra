import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temp_workspace_lifecycle as lifecycle  # noqa: E402


class TempWorkspaceLifecycleTests(unittest.TestCase):
    def test_volume_ledger_does_not_authorize_sweeping_a_different_base(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / 'first', Path(directory) / 'second'
            first.mkdir(); second.mkdir()
            old, marker = lifecycle.create_workspace(purpose='old-stage', base=first,
                                                     expected_bytes=1, reserve_bytes=0)
            marker['owner'] = {'pid': 99999999, 'start_token': 'dead'}
            lifecycle._atomic_json(old / lifecycle.MARKER, marker)
            with lifecycle.disk_admission._ledger(first) as (_, records):
                records[marker['run_id']].update(pid=99999999, start_token='dead')
            new, _ = lifecycle.create_workspace(purpose='retry-stage', base=second,
                                                 expected_bytes=1, reserve_bytes=0)
            try:
                self.assertTrue(old.exists())
                self.assertIn(str(old), lifecycle.reap_stale(base=first)['removed'])
            finally:
                lifecycle.cleanup_workspace(new, reason='TEST', allow_live_owner=True)

    def test_failed_child_registration_terminates_process_before_cleanup(self):
        children = []
        original_spawn = subprocess.Popen
        original_bind = lifecycle.disk_admission.bind
        def spawn(*args, **kwargs):
            child = original_spawn(*args, **kwargs)
            children.append(child)
            return child
        def bind(*args, **kwargs):
            if kwargs.get('process_group'):
                raise ValueError('injected child registration failure')
            return original_bind(*args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(purpose='child-failure', base=directory, expected_bytes=1,
                                   reserve_bytes=0, timeout_seconds=5,
                                   argv=[sys.executable, '-c', 'import time; time.sleep(30)'])
            with patch.object(lifecycle.subprocess, 'Popen', side_effect=spawn), patch.object(
                    lifecycle.disk_admission, 'bind', side_effect=bind):
                with self.assertRaisesRegex(ValueError, 'registration failure'):
                    lifecycle._run_owned_worker(args, {'pid': os.getpid(),
                        'start_token': lifecycle._process_start_token(os.getpid())})
            self.assertTrue(children)
            self.assertTrue(all(child.poll() is not None for child in children))
            self.assertEqual(list(Path(directory).glob('integra-owned-*')), [])

    def test_failed_marker_creation_removes_unmarked_root_and_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.object(lifecycle, '_atomic_json', side_effect=OSError('injected marker failure')):
                with self.assertRaises(OSError):
                    lifecycle.create_workspace(purpose='marker-failure', base=base,
                                               expected_bytes=1, reserve_bytes=0)
            self.assertEqual(list(base.glob('integra-owned-*')), [])
            _, _, ledger = lifecycle.disk_admission._paths(base)
            self.assertFalse(any(item.get('workspace', '').startswith(str(base))
                                 for item in json.loads(ledger.read_text()).values()))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_run_marks_before_materialization_and_cleans_success(self):
        probe = self.base / "probe.json"
        command = [sys.executable, "-c", (
            "import json,os,pathlib; root=pathlib.Path(os.environ['INTEGRA_OWNED_WORKSPACE']); "
            "assert (root/'.integra-owned-workspace.json').is_file(); "
            "pathlib.Path(os.environ['PROBE']).write_text((root/'.integra-owned-workspace.json').read_text())"
        )]
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "temp_workspace_lifecycle.py"), "run",
                                 "--purpose", "success", "--base", str(self.base), "--expected-bytes", "1",
                                 "--reserve-bytes", "0", "--timeout-seconds", "5", "--", *command],
                                env={**__import__("os").environ, "PROBE": str(probe)}, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(probe.read_text())["artifact_type"], "integra.disposable_workspace")
        self.assertEqual(list(self.base.glob("integra-owned-success-*")), [])

    def test_failure_and_timeout_cleanup_owned_process_group(self):
        failing = subprocess.run([sys.executable, str(ROOT / "scripts" / "temp_workspace_lifecycle.py"), "run",
                                  "--purpose", "failure", "--base", str(self.base), "--expected-bytes", "1",
                                  "--reserve-bytes", "0", "--timeout-seconds", "5", "--", sys.executable,
                                  "-c", "raise SystemExit(7)"], check=False)
        self.assertEqual(failing.returncode, 7)
        timed = subprocess.run([sys.executable, str(ROOT / "scripts" / "temp_workspace_lifecycle.py"), "run",
                                "--purpose", "timeout", "--base", str(self.base), "--expected-bytes", "1",
                                "--reserve-bytes", "0", "--timeout-seconds", "0.1", "--", sys.executable,
                                "-c", "import time; time.sleep(10)"], check=False)
        self.assertEqual(timed.returncode, 124)
        self.assertEqual(list(self.base.glob("integra-owned-*")), [])

    def test_killed_child_is_failure_and_leaves_no_workspace(self):
        killed = subprocess.run([sys.executable, str(ROOT / "scripts" / "temp_workspace_lifecycle.py"),
                                 "run", "--purpose", "killed-child", "--base", str(self.base),
                                 "--expected-bytes", "1", "--reserve-bytes", "0",
                                 "--timeout-seconds", "5", "--", sys.executable, "-c",
                                 "import os,signal; os.kill(os.getpid(), signal.SIGKILL)"], check=False)
        self.assertEqual(killed.returncode, 137)
        self.assertEqual(list(self.base.glob("integra-owned-killed-child-*")), [])

    def test_full_candidate_cannot_lower_disk_reserve(self):
        candidate = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_macos_candidate.py"),
                                    "--base", str(self.base), "--expected-bytes", "1",
                                    "--reserve-bytes", "0"], capture_output=True, text=True, check=False)
        self.assertNotEqual(candidate.returncode, 0)
        self.assertIn("hard disk reserve", candidate.stderr)
        self.assertEqual(list(self.base.glob("integra-owned-*")), [])

    def test_sigterm_cleans_owned_workspace(self):
        process = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "temp_workspace_lifecycle.py"), "run",
                                    "--purpose", "sigterm", "--base", str(self.base), "--expected-bytes", "1",
                                    "--reserve-bytes", "0", "--timeout-seconds", "30", "--", sys.executable,
                                    "-c", "import time; time.sleep(30)"])
        try:
            deadline = time.monotonic() + 5
            while not list(self.base.glob("integra-owned-sigterm-*")) and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(list(self.base.glob("integra-owned-sigterm-*")))
            process.terminate()
            # Cancellation may spend 1s in its signal handler plus the
            # supervisor's 5s termination grace on Linux zombie groups.
            # Leave bounded time for reaping, cleanup and caller notification.
            self.assertEqual(process.wait(timeout=10), 128)
            self.assertEqual(list(self.base.glob("integra-owned-sigterm-*")), [])
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    def test_killed_caller_is_reaped_by_detached_supervisor(self):
        pid_file = self.base / "child.pid"
        child_code = (
            "import os,pathlib,time; "
            "pathlib.Path(os.environ['PID_FILE']).write_text(str(os.getpid())); "
            "(pathlib.Path(os.environ['INTEGRA_OWNED_WORKSPACE'])/'large-sentinel').write_bytes(b'x'*1024); "
            "time.sleep(30)"
        )
        caller = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "temp_workspace_lifecycle.py"),
                                   "run", "--purpose", "parent-killed", "--base", str(self.base),
                                   "--expected-bytes", "1024", "--reserve-bytes", "0",
                                   "--timeout-seconds", "30", "--", sys.executable, "-c", child_code],
                                  env={**os.environ, "PID_FILE": str(pid_file)})
        try:
            deadline = time.monotonic() + 5
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(pid_file.exists())
            worker_pid = int(pid_file.read_text())
            caller.kill()
            caller.wait(timeout=5)
            deadline = time.monotonic() + 8
            while list(self.base.glob("integra-owned-parent-killed-*")) and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertEqual(list(self.base.glob("integra-owned-parent-killed-*")), [])
            status = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(worker_pid)],
                                    capture_output=True, text=True, timeout=5).stdout.strip()
            self.assertTrue(not status or status.startswith("Z"), status)
        finally:
            if caller.poll() is None:
                caller.kill()
                caller.wait(timeout=5)

    def test_reaper_preserves_live_and_removes_stale_owned_only(self):
        live, _ = lifecycle.create_workspace(purpose="live", base=self.base, expected_bytes=1, reserve_bytes=0)
        foreign = self.base / "integra-owned-foreign"
        foreign.mkdir()
        (foreign / lifecycle.MARKER).write_text("not json")
        stale = subprocess.run([sys.executable, str(ROOT / "scripts" / "temp_workspace_lifecycle.py"), "create",
                                "--purpose", "stale", "--base", str(self.base), "--expected-bytes", "1",
                                "--reserve-bytes", "0"], capture_output=True, text=True, check=True)
        stale_root = Path(stale.stdout.strip())
        outcome = lifecycle.reap_stale(base=self.base)
        self.assertIn(str(stale_root), outcome["removed"])
        self.assertTrue(live.exists())
        self.assertTrue(foreign.exists())
        self.assertTrue(any(item["root"] == str(live) and item["reason"] == "LIVE_OWNER_OR_CHILD" for item in outcome["skipped"]))
        lifecycle.cleanup_workspace(live, reason="TEST", allow_live_owner=True)

    def test_cleanup_is_idempotent_after_owned_root_is_removed(self):
        root, _ = lifecycle.create_workspace(purpose="idempotent", base=self.base,
                                             expected_bytes=1, reserve_bytes=0)
        self.assertTrue(lifecycle.cleanup_workspace(root, reason="TEST", allow_live_owner=True))
        self.assertFalse(lifecycle.cleanup_workspace(root, reason="TEST_AGAIN", allow_live_owner=True))

    def test_preflight_includes_live_reservations_before_materialization(self):
        live, _ = lifecycle.create_workspace(purpose="reservation", base=self.base, expected_bytes=100, reserve_bytes=0)
        usage = type("Usage", (), {"free": 150})()
        with patch.object(lifecycle.shutil, "disk_usage", return_value=usage):
            with self.assertRaisesRegex(ValueError, "live reservations"):
                lifecycle.create_workspace(purpose="second", base=self.base, expected_bytes=100, reserve_bytes=0)
        lifecycle.cleanup_workspace(live, reason="TEST", allow_live_owner=True)

    def test_low_level_build_rejects_unowned_temp_output(self):
        script = (ROOT / "scripts" / "build_macos_app.sh").read_text(encoding="utf-8")
        self.assertIn("unowned temporary directory", script)
        self.assertIn(".integra-owned-workspace.json", script)

    def test_excel_named_unowned_temporary_candidate_is_rejected_before_build(self):
        # These were the real recurrence names.  The rejection must happen
        # before source-component checks or a multi-GiB app materialization.
        target = Path("/private/tmp") / f"integra-excel-regression-{os.getpid()}"
        result = subprocess.run([str(ROOT / "scripts" / "build_macos_app.sh"), str(target)],
                                capture_output=True, text=True, timeout=10, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unowned temporary directory", result.stderr)
        self.assertFalse((target / "Integra.app").exists())

    def test_macos_full_build_test_uses_authoritative_lifecycle(self):
        script = (ROOT / "scripts" / "test_macos_app.sh").read_text(encoding="utf-8")
        self.assertIn("build_macos_candidate.py", script)
        self.assertIn("--native-tests", script)
        wrapper = (ROOT / "scripts/build_macos_candidate.py").read_text()
        self.assertIn("run_owned(args)", wrapper)
        self.assertIn("candidate_retention.reserved_build", wrapper)
        self.assertIn("--owned-workspace", script)

    def test_owner_candidate_publication_is_explicit_and_engineering_builds_are_disposable(self):
        """A repair build cannot accidentally consume an Owner-review slot."""
        wrapper = (ROOT / "scripts" / "build_macos_candidate.py").read_text()
        self.assertIn('"lifecycle": "ENGINEERING_QA_BUILD"', wrapper)
        self.assertIn('archive publication requires --publish-owner-candidate', wrapper)
        self.assertIn('"--publish-owner-candidate"', wrapper)
        rejected = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_macos_candidate.py"),
                                   "--archive-root", str(self.base)],
                                  capture_output=True, text=True, check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('--publish-owner-candidate', rejected.stderr)
