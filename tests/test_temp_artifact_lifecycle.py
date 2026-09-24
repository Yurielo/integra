"""Regression coverage for owned, crash-safe macOS build/test scratch roots."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = ROOT / "scripts" / "temp_artifact_lifecycle.py"
WRAPPER = ROOT / "scripts" / "with_temp_artifact_root.sh"


class TempArtifactLifecycleTests(unittest.TestCase):
    def create(self, base: Path, purpose: str, pid: int | None = None) -> Path:
        command = ["python3", str(LIFECYCLE), "create", "--base", str(base), "--purpose", purpose]
        if pid is not None:
            command += ["--owner-pid", str(pid)]
        return Path(subprocess.check_output(command, text=True).strip())

    def test_normal_completion_removes_owned_large_candidate_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); receipt = base / "root.txt"
            command = [str(WRAPPER), "--purpose", "success", "--", "sh", "-c",
                       'printf "%s" "$INTEGRA_TEMP_ARTIFACT_ROOT" > "$1"; dd if=/dev/zero of="$INTEGRA_TEMP_ARTIFACT_ROOT/candidate.bin" bs=1m count=4 status=none',
                       "sh", str(receipt)]
            subprocess.run(command, check=True, env=os.environ | {"TMPDIR": str(base)})
            root = Path(receipt.read_text())
            self.assertFalse(root.exists())

    def test_failure_removes_owned_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); receipt = base / "root.txt"
            command = [str(WRAPPER), "--purpose", "failure", "--", "sh", "-c",
                       'printf "%s" "$INTEGRA_TEMP_ARTIFACT_ROOT" > "$1"; dd if=/dev/zero of="$INTEGRA_TEMP_ARTIFACT_ROOT/candidate.bin" bs=1m count=4 status=none; exit 23',
                       "sh", str(receipt)]
            result = subprocess.run(command, check=False, env=os.environ | {"TMPDIR": str(base)})
            self.assertEqual(result.returncode, 23)
            self.assertFalse(Path(receipt.read_text()).exists())

    def test_sigterm_removes_only_terminated_wrapper_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); first_receipt = base / "first.txt"; second_receipt = base / "second.txt"
            def start(purpose, receipt):
                return subprocess.Popen([str(WRAPPER), "--purpose", purpose, "--", "sh", "-c",
                    'printf "%s" "$INTEGRA_TEMP_ARTIFACT_ROOT" > "$1"; sleep 30', "sh", str(receipt)],
                    env=os.environ | {"TMPDIR": str(base)})
            first, second = start("first", first_receipt), start("second", second_receipt)
            for _ in range(100):
                if first_receipt.exists() and second_receipt.exists(): break
                time.sleep(.02)
            first_root, second_root = Path(first_receipt.read_text()), Path(second_receipt.read_text())
            first.send_signal(signal.SIGTERM); first.wait(timeout=10)
            self.assertFalse(first_root.exists())
            self.assertTrue(second_root.is_dir())
            second.send_signal(signal.SIGTERM); second.wait(timeout=10)
            self.assertFalse(second_root.exists())

    def test_stale_reaper_skips_live_owner_and_retained_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            live = self.create(base, "live", os.getpid())
            retained = self.create(base, "retain", os.getpid())
            marker = retained / ".integra-temp-artifact.json"
            value = json.loads(marker.read_text()); value["cleanup_policy"] = "RETAIN_EVIDENCE"
            marker.write_text(json.dumps(value), encoding="utf-8")
            stale = self.create(base, "stale", os.getpid())
            stale_marker = stale / ".integra-temp-artifact.json"
            stale_value = json.loads(stale_marker.read_text())
            stale_value["owner"] = {"pid": 999999, "process_start_token": "dead", "run_token": stale_value["owner"]["run_token"]}
            stale_marker.write_text(json.dumps(stale_value), encoding="utf-8")
            result = json.loads(subprocess.check_output(["python3", str(LIFECYCLE), "reap", "--base", str(base)], text=True))
            self.assertIn(str(stale), result["removed"])
            self.assertTrue(live.exists()); self.assertTrue(retained.exists())
            subprocess.run(["python3", str(LIFECYCLE), "cleanup", "--root", str(live), "--allow-live-owner"], check=True)

    def test_unmarked_canonical_build_is_never_a_cleanup_target(self):
        with tempfile.TemporaryDirectory() as directory:
            canonical = Path(directory) / "current-build" / "Integra.app"
            canonical.mkdir(parents=True); (canonical / "sentinel").write_text("canonical")
            result = subprocess.run(["python3", str(LIFECYCLE), "cleanup", "--root", str(canonical)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((canonical / "sentinel").read_text(), "canonical")

    def test_macos_harness_uses_marker_bound_cleanup(self):
        source = (ROOT / "scripts" / "test_macos_app.sh").read_text(encoding="utf-8")
        self.assertIn("temp_artifact_lifecycle.py\" create --purpose macos-app-test", source)
        self.assertIn("trap 'exit 130' INT", source)
        self.assertNotIn("mktemp -d", source)

    def test_retained_candidate_helper_refuses_temporary_output(self):
        source = (ROOT / "scripts" / "build_macos_candidate.sh").read_text(encoding="utf-8")
        self.assertIn("retained Candidate output must not be under temporary storage", source)
        self.assertIn("candidate_manifest.py\" validate", source)

    def test_build_stdout_contract_leaves_diagnostics_on_stderr(self):
        source = (ROOT / "scripts" / "build_macos_app.sh").read_text(encoding="utf-8")
        self.assertIn('package_review_runtime.py" "$seminartext_checkout" "$app/Contents/Resources" >&2', source)


if __name__ == "__main__":
    unittest.main()
