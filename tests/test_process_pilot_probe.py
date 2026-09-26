import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts import probe_process_executor_pilot as probe


class PilotProbeIdentityTests(unittest.TestCase):
    def test_source_requires_exact_clean_commit_and_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True,
                                      capture_output=True, text=True).stdout.strip()

            git("init")
            git("config", "user.email", "synthetic@example.invalid")
            git("config", "user.name", "Synthetic")
            (root / "route.py").write_text("original\n")
            git("add", ".")
            git("commit", "-m", "synthetic source")
            identity = {"commit_sha": git("rev-parse", "HEAD"),
                        "tree_sha": git("rev-parse", "HEAD^{tree}")}
            probe.verify_source(root, identity)
            for field in identity:
                with self.subTest(field=field), self.assertRaises(SystemExit):
                    probe.verify_source(root, {**identity, field: "0" * 40})
            (root / "route.py").write_text("changed\n")
            with self.assertRaises(SystemExit):
                probe.verify_source(root, identity)

    def test_same_candidate_id_is_insufficient_for_baseline(self):
        baseline = {"candidate_id": probe.CURRENT_ID, "identity_sha256": "a" * 64,
                    "bundle": {"digest": "b" * 64}}
        active = {"candidate": {"identity_sha256": "a" * 64, "bundle_digest": "b" * 64}}
        probe.verify_baseline(baseline, active)
        changed = copy.deepcopy(baseline)
        changed["bundle"]["digest"] = "c" * 64
        with self.assertRaises(SystemExit):
            probe.verify_baseline(changed, active)
        changed = {**baseline, "identity_sha256": "d" * 64}
        with self.assertRaises(SystemExit):
            probe.verify_baseline(changed, active)
        with self.assertRaises(SystemExit):
            probe.verify_baseline({**baseline, "candidate_id": "other"}, active)
