"""Issue #236 fixture regressions; synthetic choices are not product acceptance."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import k2_qa_fixture as fixture
from temp_workspace_lifecycle import _process_start_token


class K2QAFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="integra-owned-" + fixture.PURPOSE + "-", dir=fixture.BASE)
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.marker = {"schema_version": fixture.SCHEMA, "artifact_type": "integra.disposable_workspace",
            "root": str(self.workspace), "purpose": fixture.PURPOSE, "created_at": "synthetic-test",
            "run_id": "synthetic-test", "expected_bytes": 0, "reserve_bytes": 0,
            "owner": {"pid": os.getpid(), "start_token": _process_start_token(os.getpid())},
            "child": {}, "state": "CREATED", "events": []}
        self.write_marker()

    def write_marker(self):
        (self.workspace / fixture.MARKER).write_bytes(fixture.encoded(self.marker))

    def test_seed_is_deterministic_two_distinct_nonoverlapping_units(self):
        project = self.workspace / "projects" / fixture.PROJECT_UUID
        first = fixture.payloads(project)
        self.assertEqual(first, fixture.payloads(project))
        topics = json.loads(first["topics.json"])["topics"]
        self.assertEqual(len(topics), 2)
        self.assertEqual(tuple(item["title"] for item in topics), fixture.TITLES)
        self.assertLess(topics[0]["end_seconds"], topics[1]["start_seconds"])
        self.assertTrue(all(item["semantic_status"] == "REVIEW_REQUIRED" for item in topics))
        self.assertFalse(json.loads(first["QA_ONLY.json"])["production_acceptance"])

    def test_isolated_fixture_does_not_touch_demo_or_candidate(self):
        # Sentinels deliberately have no production paths. prepare() has no
        # source/Candidate parameter and only writes its exclusive output root.
        with tempfile.TemporaryDirectory() as unrelated:
            parent = Path(unrelated)
            demo, candidate = parent / "demo.json", parent / "candidate.bin"
            demo.write_bytes(b"canonical demo sentinel")
            candidate.write_bytes(b"immutable candidate sentinel")
            before = (demo.read_bytes(), candidate.read_bytes())
            project = fixture.prepare(self.workspace)
            self.assertEqual(before, (demo.read_bytes(), candidate.read_bytes()))
            self.assertTrue(project.is_relative_to(self.workspace / "projects"))
            self.assertEqual(set(fixture.payloads(project)),
                             {p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_file()})
            self.assertFalse(any(p.is_symlink() for p in project.rglob("*")))

    def test_refuses_overwrite_and_symlink_destination(self):
        with tempfile.TemporaryDirectory() as unrelated:
            target = Path(unrelated)
            (target / "sentinel").write_bytes(b"keep")
            (self.workspace / "projects").symlink_to(target, target_is_directory=True)
            with self.assertRaises(FileExistsError):
                fixture.prepare(self.workspace)
            self.assertEqual((target / "sentinel").read_bytes(), b"keep")

    def test_refuses_second_preparation(self):
        fixture.prepare(self.workspace)
        with self.assertRaises(FileExistsError):
            fixture.prepare(self.workspace)

    def test_rejects_wrong_purpose_dead_owner_and_extra_marker_fields(self):
        for change in ({"purpose": "issue227"}, {"owner": {"pid": -1, "start_token": "dead"}}, {"unexpected": True}):
            original = self.marker.copy()
            self.marker.update(change)
            self.write_marker()
            with self.assertRaises(ValueError):
                fixture.prepare(self.workspace)
            self.assertFalse((self.workspace / "projects").exists())
            self.marker = original

    def test_rejects_symlink_marker_and_group_writable_root(self):
        marker = self.workspace / fixture.MARKER
        marker.unlink()
        marker.symlink_to("missing")
        with self.assertRaises(ValueError):
            fixture.prepare(self.workspace)
        marker.unlink()
        self.write_marker()
        os.chmod(self.workspace, 0o770)
        try:
            with self.assertRaises(ValueError):
                fixture.prepare(self.workspace)
        finally:
            os.chmod(self.workspace, 0o700)

    def test_rejects_nonworkspace_root(self):
        with self.assertRaises(ValueError):
            fixture.prepare(ROOT)

    def test_two_unit_guard_rejects_insufficient_review_before_k2(self):
        operations = []
        def bridge(operation, request):
            operations.append(operation)
            if operation == "knowledge-open":
                return {"topics": [{"id": "one"}], "state_sha256": "test"}
            return {"status": "REVIEWED_FRAGMENTS_V2", "reviewed": {"semantic_knowledge": [{"title": "one"}]}}
        with self.assertRaisesRegex(ValueError, "two distinct reviewed units"):
            fixture.exercise(bridge)
        self.assertEqual(operations, ["knowledge-open", "knowledge-save"])

    def test_relation_uses_exact_two_concept_endpoints_and_fragment_selection(self):
        proposals = {"proposals": [{"entity_kind": "concepts", "after": {"id": identity}}
                                   for identity in ("concept-A", "concept-B")]}
        fragments = ["fragment-A", "fragment-B"]
        relation = fixture.relation_input(proposals, fragments)
        self.assertEqual(relation, {"source_concept_id": "concept-A", "target_concept_id": "concept-B",
                                   "relation_type": "associated_with", "fragment_ids": fragments})
        fragments.clear()
        self.assertEqual(relation["fragment_ids"], ["fragment-A", "fragment-B"])

    def test_relation_rejects_single_or_duplicate_concept_endpoints(self):
        for identities in (("only-one",), ("same", "same")):
            proposals = {"proposals": [{"entity_kind": "concepts", "after": {"id": identity}}
                                       for identity in identities]}
            with self.assertRaisesRegex(ValueError, "two distinct Concept endpoints"):
                fixture.relation_input(proposals, ["fragment-A", "fragment-B"])


PINNED = Path(os.environ.get("INTEGRA_TEST_SEMINARTEXT_CHECKOUT", ROOT / ".runtime-components/seminartext-pinned"))


@unittest.skipUnless((PINNED / "seminartext_modules/human_review_workflow.py").is_file(),
                     "requires exact pinned review runtime (same K1 test prerequisite)")
class K2FixtureRealReviewTests(unittest.TestCase):
    setUp = K2QAFixtureTests.setUp
    write_marker = K2QAFixtureTests.write_marker
    def test_actual_review_contract_produces_two_eligible_units(self):
        from integra_core import knowledge_notebook as notebook
        project = fixture.prepare(self.workspace)
        with patch.dict(os.environ, {"INTEGRA_SEMINARTEXT_CHECKOUT": str(PINNED), "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.environ.get("INTEGRA_TEST_REVIEW_PYTHONPATH", str(ROOT / ".runtime-components/review-python"))}):
            opened = notebook.open_notebook(project, **fixture.IDENTITY, create=True)
            reviewed = notebook.save_notebook(project, **fixture.IDENTITY, expected_state_sha256=opened["state_sha256"],
                decisions=[{"topic_id": t["id"], "action": "ACCEPT", "reason": "Synthetic QA only"} for t in opened["topics"]],
                reviewer_id="synthetic-fixture-qa-only")
            units = reviewed["reviewed"]["semantic_knowledge"]
            self.assertEqual(reviewed["status"], "REVIEWED_FRAGMENTS_V2")
            self.assertEqual(len(units), 2)
            self.assertEqual({u["title"] for u in units}, set(fixture.TITLES))
            self.assertTrue(all(u["fragment_refs"] for u in units))
            self.assertTrue(all(r["transcript_provenance"]["verification_state"] == "machine_unverified"
                                for r in reviewed["transcript_revisions"]))
            self.assertEqual(notebook.open_notebook(project, **fixture.IDENTITY), reviewed)


if __name__ == "__main__":
    unittest.main()
