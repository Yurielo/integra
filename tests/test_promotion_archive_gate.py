"""Promotion must verify retained bytes before preparing any new records."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import promote_proposed_baseline_lite as promotion
import candidate_protection_gate as protection_gate


class PromotionArchiveGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "state").mkdir()
        self.old_candidate = {"candidate_id": "candidate-v1-" + "d" * 64, "bundle_digest": "e" * 64}
        self.current = {"current_id": "preserve-current", "records": [
            {"baseline_id": "preserve-current", "candidate": self.old_candidate}]}
        (self.root / "state/current_product_baseline_v2.json").write_text(json.dumps(self.current))
        self.candidate = {"candidate_id": "candidate-v1-" + "a" * 64,
                          "bundle_digest": "b" * 64, "manifest_digest": "c" * 64}
        self.proposal = self.root / "proposal.json"
        self.proposal.write_text(json.dumps({"candidate": self.candidate}))
        self.output = self.root / "new-current.json"
        self.history = self.root / "history.json"
        self.archive = self.root / "retained"
        self.archive.mkdir()
        self.old_archive = self.root / "old-retained"
        self.old_archive.mkdir()
        self.args = ["--proposal", str(self.proposal), "--owner-acceptance-ref", "explicit-owner-ref",
                     "--candidate-archive", str(self.archive), "--output", str(self.output),
                     "--current-archive", str(self.old_archive),
                     "--history-output", str(self.history)]
        self.mocks = {}
        for name in ("validate_current", "validate_proposal", "verify_promotion_material"):
            self.mocks[name] = self.enterContext(patch.object(promotion, name, return_value=[]))
        self.verify = self.enterContext(patch.object(promotion, "verify_archive", return_value={}))
        self.protection = self.enterContext(patch.object(promotion, "require_promotion", return_value=None))
        self.successor = self.enterContext(patch.object(promotion, "next_current", return_value={"new": True}))
        self.enterContext(patch.object(promotion, "ROOT", self.root))

    def run_main(self, args=None):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return promotion.main(self.args if args is None else args)

    def assert_unmodified(self):
        self.assertFalse(self.output.exists())
        self.assertFalse(self.history.exists())
        self.assertEqual(json.loads((self.root / "state/current_product_baseline_v2.json").read_text()), self.current)
        self.successor.assert_not_called()

    def test_archive_argument_is_required_even_with_owner_reference(self):
        args = self.args.copy()
        index = args.index("--candidate-archive")
        del args[index:index + 2]
        with self.assertRaises(SystemExit) as error:
            self.run_main(args)
        self.assertEqual(error.exception.code, 2)
        self.assert_unmodified()

    def test_missing_corrupt_or_mismatched_archive_blocks_all_writes(self):
        for error in (ValueError("digest mismatch"), FileNotFoundError("missing app")):
            with self.subTest(error=error):
                self.verify.side_effect = error
                self.assertEqual(self.run_main(), 1)
                self.assert_unmodified()

    def test_valid_archive_is_bound_to_all_three_proposal_identifiers(self):
        self.assertEqual(self.run_main(), 0)
        self.verify.assert_has_calls([call(self.archive, expected=self.candidate),
                                      call(self.old_archive, expected=self.old_candidate)])
        self.assertEqual(json.loads(self.history.read_text()), self.current)
        self.assertEqual(json.loads(self.output.read_text()), {"new": True})
        self.successor.assert_called_once_with(self.current, {"candidate": self.candidate},
                                              "explicit-owner-ref", previous_current_path="history.json")
        self.protection.assert_called_once_with({"candidate": self.candidate}, self.current,
                                                self.archive, self.old_archive)

    def test_missing_canonical_protection_blocks_before_any_write(self):
        self.protection.side_effect = ValueError('canonical protection unavailable')
        self.assertEqual(self.run_main(), 1)
        self.assert_unmodified()

    def test_live_pending_registry_blocks_even_when_archive_checks_are_mocked_pass(self):
        self.protection.side_effect = protection_gate.require_promotion
        self.assertEqual(self.run_main(), 1)
        self.assert_unmodified()

    def test_archive_does_not_replace_existing_governance_checks(self):
        self.mocks["verify_promotion_material"].return_value = ["invalid proposal"]
        self.assertEqual(self.run_main(), 1)
        self.verify.assert_not_called()
        self.assert_unmodified()

    def test_archive_does_not_replace_owner_acceptance(self):
        args = self.args.copy()
        index = args.index("--owner-acceptance-ref")
        del args[index:index + 2]
        with self.assertRaises(SystemExit):
            self.run_main(args)
        self.assert_unmodified()

    def test_missing_outgoing_current_archive_blocks_promotion(self):
        args = self.args.copy()
        index = args.index("--current-archive")
        del args[index:index + 2]
        with self.assertRaises(SystemExit):
            self.run_main(args)
        self.assert_unmodified()

    def test_invalid_outgoing_archive_blocks_all_writes(self):
        self.verify.side_effect = [{}, ValueError("outgoing archive differs")]
        self.assertEqual(self.run_main(), 1)
        self.assert_unmodified()

    def test_output_inside_either_archive_is_rejected_without_mutation(self):
        for archive in (self.archive, self.old_archive):
            for option in ("--output", "--history-output"):
                with self.subTest(archive=archive.name, option=option):
                    target = archive / "nested/new-record.json"
                    args = self.args.copy()
                    args[args.index(option) + 1] = str(target)
                    self.assertEqual(self.run_main(args), 1)
                    self.assertFalse(target.parent.exists())
                    self.assert_unmodified()

    def test_case_alias_output_inside_archive_is_rejected(self):
        alias = self.root / self.archive.name.upper()
        if not alias.exists() or not alias.samefile(self.archive):
            self.skipTest("case-sensitive filesystem")
        args = self.args.copy()
        args[args.index("--output") + 1] = str(alias / "nested/record.json")
        self.assertEqual(self.run_main(args), 1)
        self.assertFalse((self.archive / "nested").exists())
        self.assert_unmodified()

    def test_existing_output_is_preserved_and_history_is_not_written(self):
        self.output.write_text("must survive")
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.output.read_text(), "must survive")
        self.assertFalse(self.history.exists())
        self.successor.assert_not_called()

    def test_existing_history_is_preserved(self):
        self.history.write_text("old evidence")
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.history.read_text(), "old evidence")
        self.assertFalse(self.output.exists())

    def test_aliased_output_paths_are_rejected(self):
        args = self.args.copy()
        args[args.index("--output") + 1] = str(self.history)
        self.assertEqual(self.run_main(args), 1)
        self.assert_unmodified()


if __name__ == "__main__":
    unittest.main()
