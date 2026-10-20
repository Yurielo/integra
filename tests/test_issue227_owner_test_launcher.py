"""Owner launcher regressions: no stdin prompt and no cleanup during a GUI session."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import launch_k2_owner_test as launcher  # noqa: E402


class Issue227OwnerTestLauncherTests(unittest.TestCase):
    def test_exact_candidate_is_pinned_and_launcher_has_no_read_prompt(self):
        self.assertEqual(launcher.IDENTITY, {
            "candidate_id": "candidate-v1-2d770b6b3ff323a9b60c45cecdb7b5c36652b11cb102f16de63145530997dd11",
            "bundle_digest": "e3c5bce9cefd8facb8ca228b56b66a560443629d94e97dd3e0d630ed06fb9164",
            "manifest_digest": "6d5bb4b9f4abc8863ecfc05222df3651141cb23a37e135e3d19aeb5c4ef57ccc",
        })
        source = (SCRIPTS / "launch_k2_owner_test.py").read_text(encoding="utf-8")
        self.assertNotIn("read -r", source)
        self.assertIn('"--wait-for-child-exit"', source)
        self.assertIn("stdin=subprocess.DEVNULL", source)
        self.assertIn('"--self-test"', source)
        self.assertIn('OWNER_TEST_PACKAGED_SELF_TEST: PASS', source)

    def test_old_bash_lc_read_failure_reproduces_eof_then_cleanup(self):
        """Reproduce lifecycle -> bash -lc -> launched command -> read EOF."""
        with tempfile.TemporaryDirectory(prefix="integra-issue227-eof-") as temporary:
            base = Path(temporary)
            fake_open = base / "open"
            fake_open.write_text("#!/bin/sh\nprintf 'OPEN_REACHED\\n'\n", encoding="utf-8")
            fake_open.chmod(0o700)
            command_text = f"'{fake_open}' ; read -r; printf 'READ_RETURNED\\n'"
            command = [sys.executable, "-B", str(SCRIPTS / "temp_workspace_lifecycle.py"),
                       "run", "--purpose", "issue227-eof-repro", "--base", str(base),
                       "--expected-bytes", "1", "--reserve-bytes", "0", "--timeout-seconds", "5",
                       "--", "/bin/bash", "-lc", command_text]
            started = time.monotonic()
            result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, timeout=10, check=False)
            elapsed = time.monotonic() - started
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OPEN_REACHED", result.stdout)
            self.assertIn("READ_RETURNED", result.stdout)
            self.assertLess(elapsed, 3, "closed stdin should make the old read return immediately")
            events = [json.loads(line) for line in result.stderr.splitlines() if line.startswith("{")]
            created = next(item for item in events if item.get("event") == "WORKSPACE_CREATED")
            cleaned = next(item for item in events if item.get("event") == "WORKSPACE_CLEANUP_COMPLETED")
            self.assertEqual(created["root"], cleaned["root"])
            self.assertFalse(Path(created["root"]).exists())

    def test_owned_workspace_and_fixture_live_until_gui_child_exits(self):
        """Exercise the launcher wait helper under the real lifecycle supervisor."""
        with tempfile.TemporaryDirectory(prefix="integra-issue227-session-") as temporary:
            base = Path(temporary)
            observation = base / "observed.json"
            fake_app = base / "fake-integra"
            fake_app.write_text(
                "#!/bin/sh\n"
                "test -f \"$INTEGRA_OWNED_WORKSPACE/QA_ONLY.json\" || exit 23\n"
                "printf '{\"pid\":%s,\"workspace\":\"%s\"}\\n' \"$$\" \"$INTEGRA_OWNED_WORKSPACE\" > \"$OWNER_TEST_OBSERVATION\"\n"
                "while [ ! -f \"$INTEGRA_OWNED_WORKSPACE/release\" ]; do sleep 0.05; done\n",
                encoding="utf-8")
            fake_app.chmod(0o700)
            candidate_sentinel = base / "immutable-candidate.bin"
            candidate_sentinel.write_bytes(b"candidate bytes are not an output")
            candidate_before = hashlib.sha256(candidate_sentinel.read_bytes()).hexdigest()
            code = (
                "import os,sys; from pathlib import Path; "
                f"sys.path.insert(0, {str(SCRIPTS)!r}); "
                "from launch_k2_owner_test import launch_application; "
                "root=Path(os.environ['INTEGRA_OWNED_WORKSPACE']); "
                "(root/'QA_ONLY.json').write_text('{\\\"fixture\\\":true}'); "
                "launch_application(Path(os.environ['OWNER_TEST_FAKE_APP']),root,os.environ.copy(),"
                "root/'fake-app.log',startup_seconds=.2)"
            )
            command = [sys.executable, "-B", str(SCRIPTS / "temp_workspace_lifecycle.py"),
                       "run", "--purpose", "issue227-session-test", "--base", str(base),
                       "--expected-bytes", "1", "--reserve-bytes", "0", "--timeout-seconds", "0.01",
                       "--wait-for-child-exit", "--", sys.executable, "-B", "-c", code]
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True,
                                       env={**os.environ, "OWNER_TEST_FAKE_APP": str(fake_app),
                                            "OWNER_TEST_OBSERVATION": str(observation)})
            try:
                deadline = time.monotonic() + 8
                while not observation.exists() and time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    time.sleep(.05)
                self.assertTrue(observation.exists(), "fake GUI did not launch")
                observed = json.loads(observation.read_text(encoding="utf-8"))
                workspace = Path(observed["workspace"])
                self.assertTrue(workspace.is_dir())
                self.assertTrue((workspace / "QA_ONLY.json").is_file(), "fixture disappeared during GUI session")
                self.assertIsNone(process.poll(), "lifecycle returned while GUI process was still active")
                time.sleep(.25)
                self.assertTrue(workspace.is_dir(), "workspace was cleaned before the GUI exited")
                (workspace / "release").touch()
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                self.assertIn("OWNER_TEST_APP_RUNNING", stdout)
                self.assertIn("WORKSPACE_CLEANUP_COMPLETED", stderr)
                self.assertFalse(workspace.exists(), "workspace was not cleaned after app exit")
                self.assertEqual(hashlib.sha256(candidate_sentinel.read_bytes()).hexdigest(), candidate_before)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
