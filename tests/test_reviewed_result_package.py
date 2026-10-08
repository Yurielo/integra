"""Package only already-reviewed real pinned component fixture outputs."""
import hashlib
import json
from pathlib import Path
import unittest

from integra_core.identity import derive_imported_id
from integra_core.protocol import canonical_json, content_sha256
from integra_core.publishing import PublishingError
from integra_core.reviewed_result_package import build_reviewed_result_package, validate_reviewed_result_package
from tests import test_seminartext_topic_review_runtime as fixtures


@unittest.skipUnless((fixtures.PINNED / "seminartext_modules/human_review_workflow.py").is_file(), "requires pinned SeminarText checkout")
class ReviewedResultPackageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.TopicReviewRuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def build(self, result, **kwargs):
        return build_reviewed_result_package(project_dir=self.fixture.project, source_id=self.fixture.source_id,
            decisions_path=result["decisions_path"], project_id="urn:integra:project:00000000-0000-0000-0000-000000000001", project_slug="synthetic", **kwargs)

    def reviewed(self, v2=False):
        package = self.fixture.prepare_fragments() if v2 else self.fixture.prepare()
        return self.fixture.apply(package, self.fixture.decisions(package), boundaries_acknowledged=v2)

    def test_v1_package_is_deterministic_and_cross_validated(self):
        result = self.reviewed()
        manifest, files = self.build(result)
        self.assertEqual(manifest["result_kind"], "CANONICAL_KNOWLEDGE_V1")
        self.assertEqual(self.build(result), (manifest, files))
        self.assertTrue(any(path.startswith("view/") for path in files))
        self.assertFalse(any(str(self.fixture.project).encode() in payload for payload in files.values()))
        validate_reviewed_result_package(manifest, files)

    def test_v2_package_has_actual_fragments_and_no_fake_knowledge(self):
        result = self.reviewed(v2=True)
        manifest, files = self.build(result)
        self.assertEqual(manifest["result_kind"], "REVIEWED_FRAGMENTS_V2")
        self.assertNotIn("compiled_evidence", manifest["provenance"])
        self.assertFalse(any(path.startswith("view/") for path in files))
        self.assertEqual(self.build(result), (manifest, files))
        validate_reviewed_result_package(manifest, files)

    def test_v2_edited_partition_package_replays_without_losing_edits(self):
        from integra_core.seminartext_topic_review_runtime import prepare_topic_review
        package = prepare_topic_review(self.fixture.project, source_id=self.fixture.source_id,
            canonical_evidence_path=self.fixture.evidence, topics_path=str(self.fixture.topics), exact_fragments=True)
        choices = self.fixture.decisions(package)
        words = sorted(json.loads(Path(self.fixture.evidence).read_text())["words"], key=lambda item: item["sequence"])
        choices[0].update(action="RENAME", new_title="Сохранённая правка", new_summary="Проверенное описание",
                          word_start_id=words[1]["id"], word_end_id=words[30]["id"])
        result = self.fixture.apply(package, choices, boundaries_acknowledged=True)
        manifest, files = self.build(result)
        self.assertEqual(manifest["result_kind"], "REVIEWED_FRAGMENTS_V2")
        self.assertEqual(self.build(result), (manifest, files))
        payload = json.loads(files[manifest["result"]["path"]])
        self.assertEqual(payload["semantic_knowledge"][0]["title"], "Сохранённая правка")
        self.assertEqual(payload["semantic_knowledge"][0]["word_end_id"], words[30]["id"])
        self.assertEqual(len(payload["fragment_lineage"]), 4)
        validate_reviewed_result_package(manifest, files)

    def test_v2_notebook_links_bind_exact_source_revision_and_fragments(self):
        from urllib.parse import urlencode
        result = self.reviewed(v2=True)
        evidence = json.loads(Path(self.fixture.evidence).read_text())
        context = {"project_id": "urn:integra:project:00000000-0000-0000-0000-000000000001",
            "run_id": "urn:integra:run:00000000-0000-0000-0000-000000000002", "source_id": self.fixture.source_id,
            "source_revision_sha256": evidence["sources"][0]["content_sha256"],
            "notebook_id": "urn:integra:artifact:synthetic-notebook"}
        manifest, files = self.build(result, navigation_context=context)
        self.assertEqual(self.build(result, navigation_context=context), (manifest, files))
        reviewed = json.loads(files[manifest["result"]["path"]])
        fragment_id = reviewed["semantic_knowledge"][0]["fragment_refs"][0]
        expected = "integra://knowledge/fragment?" + urlencode({"project_id": context["project_id"], "run_id": context["run_id"],
            "source_id": context["source_id"], "fragment_id": fragment_id, "source_revision_sha256": context["source_revision_sha256"],
            "notebook_id": context["notebook_id"]})
        self.assertIn(expected.encode(), files["view/notebook.md"])
        original_notebook = files["view/notebook.md"]
        files["view/notebook.md"] = original_notebook.replace(urlencode({"notebook_id": context["notebook_id"]}).encode(),
                                                            b"notebook_id=urn%3Aintegra%3Aartifact%3Aforged-notebook")
        self.rehash_outer(manifest, files)
        with self.assertRaisesRegex(PublishingError, "source links"):
            validate_reviewed_result_package(manifest, files)
        files["view/notebook.md"] = original_notebook
        files["view/notebook.md"] = files["view/notebook.md"].replace(fragment_id.encode(), b"invented_fragment")
        self.rehash_outer(manifest, files)
        with self.assertRaisesRegex(PublishingError, "source links"):
            validate_reviewed_result_package(manifest, files)
        with self.assertRaisesRegex(ValueError, "source revision differs"):
            self.build(result, navigation_context=context | {"source_revision_sha256": "0" * 64})

    @staticmethod
    def rehash_outer(manifest, files):
        manifest["files"] = [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "ownership_class": "MANAGED_GENERATED"} for name, data in sorted(files.items())]
        for ref in manifest["provenance"].values():
            ref["sha256"] = hashlib.sha256(files[ref["path"]]).hexdigest()
        for ref in (manifest["result"], manifest["result"]["markdown"]):
            ref["sha256"] = hashlib.sha256(files[ref["path"]]).hexdigest()
        manifest["version_sha256"] = content_sha256({key: value for key, value in manifest.items() if key not in {"version_sha256", "package_id"}})
        manifest["package_id"] = derive_imported_id("artifact", "integra.reviewed_result", manifest["project_id"], manifest["version_sha256"])

    def test_swapped_decision_rejected_even_after_outer_hashes_recomputed(self):
        manifest, files = self.build(self.reviewed())
        decisions_path = manifest["provenance"]["decisions"]["path"]
        decisions = json.loads(files[decisions_path]); decisions["decisions"][0]["action"] = "REJECT"
        files[decisions_path] = canonical_json(decisions) + b"\n"
        self.rehash_outer(manifest, files)
        with self.assertRaises(PublishingError):
            validate_reviewed_result_package(manifest, files)

    def test_swapped_v2_result_rejected_even_after_outer_and_receipt_hashes_recomputed(self):
        manifest, files = self.build(self.reviewed(v2=True))
        result_path = manifest["result"]["path"]
        result = json.loads(files[result_path]); result["semantic_knowledge"][0]["title"] = "Invented title"
        files[result_path] = canonical_json(result) + b"\n"
        receipt_path = manifest["provenance"]["receipt"]["path"]
        receipt = json.loads(files[receipt_path]); receipt["reviewed_topics_sha256"] = hashlib.sha256(files[result_path]).hexdigest()
        files[receipt_path] = canonical_json(receipt) + b"\n"
        self.rehash_outer(manifest, files)
        with self.assertRaises(PublishingError):
            validate_reviewed_result_package(manifest, files)

    def test_changed_original_input_rejected_before_build(self):
        result = self.reviewed()
        self.fixture.topics.write_bytes(self.fixture.topics.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "topics changed"):
            self.build(result)

    def test_v2_container_swap_rejected_after_recomputed_checksums(self):
        manifest, files = self.build(self.reviewed(v2=True))
        result_path = manifest["result"]["path"]
        result = json.loads(files[result_path])
        result["non_semantic_excluded"].append(result["semantic_knowledge"].pop())
        files[result_path] = canonical_json(result) + b"\n"
        receipt_path = manifest["provenance"]["receipt"]["path"]
        receipt = json.loads(files[receipt_path]); receipt["reviewed_topics_sha256"] = hashlib.sha256(files[result_path]).hexdigest()
        files[receipt_path] = canonical_json(receipt) + b"\n"
        self.rehash_outer(manifest, files)
        with self.assertRaisesRegex(PublishingError, "container contradicts"):
            validate_reviewed_result_package(manifest, files)

    def test_v1_changed_scope_in_both_knowledge_documents_rejected(self):
        manifest, files = self.build(self.reviewed())
        for ref in (manifest["result"], manifest["provenance"]["knowledge_input"]):
            value = json.loads(files[ref["path"]]); value["topics"][0]["source_scope"]["order_end"] = 0
            files[ref["path"]] = canonical_json(value) + b"\n"
        receipt_path = manifest["provenance"]["receipt"]["path"]
        receipt = json.loads(files[receipt_path]); receipt["canonical_knowledge_sha256"] = hashlib.sha256(files[manifest["result"]["path"]]).hexdigest()
        files[receipt_path] = canonical_json(receipt) + b"\n"
        self.rehash_outer(manifest, files)
        with self.assertRaisesRegex(PublishingError, "knowledge source range"):
            validate_reviewed_result_package(manifest, files)

    def test_v1_source_evidence_quote_tamper_rejected_after_rebinding(self):
        manifest, files = self.build(self.reviewed())
        source_path = manifest["provenance"]["source_evidence"]["path"]
        source = json.loads(files[source_path]); source["evidence"][0]["quote"] = "Invented quotation"
        files[source_path] = canonical_json(source) + b"\n"
        source_sha = hashlib.sha256(files[source_path]).hexdigest()
        result_path = manifest["result"]["path"]
        result = json.loads(files[result_path]); result["source_evidence"]["sha256"] = source_sha
        files[result_path] = canonical_json(result) + b"\n"
        receipt_path = manifest["provenance"]["receipt"]["path"]
        receipt = json.loads(files[receipt_path]); receipt["source_evidence_sha256"] = source_sha
        receipt["canonical_knowledge_sha256"] = hashlib.sha256(files[result_path]).hexdigest()
        files[receipt_path] = canonical_json(receipt) + b"\n"
        self.rehash_outer(manifest, files)
        with self.assertRaisesRegex(PublishingError, "source Evidence quote"):
            validate_reviewed_result_package(manifest, files)

    def test_readable_markdown_tamper_rejected_even_with_all_checksums_updated(self):
        for v2 in (False, True):
            with self.subTest(v2=v2):
                # Fresh fixture project per mode avoids reusing a source package.
                if v2:
                    self.fixture.doCleanups(); self.fixture.setUp()
                manifest, files = self.build(self.reviewed(v2=v2))
                markdown_path = manifest["result"]["markdown"]["path"]
                files[markdown_path] = b"# Everything accepted automatically\n"
                receipt_path = manifest["provenance"]["receipt"]["path"]
                receipt = json.loads(files[receipt_path]); receipt["reviewed_topics_markdown_sha256" if v2 else "knowledge_markdown_sha256"] = hashlib.sha256(files[markdown_path]).hexdigest()
                files[receipt_path] = canonical_json(receipt) + b"\n"
                self.rehash_outer(manifest, files)
                with self.assertRaisesRegex(PublishingError, "readable"):
                    validate_reviewed_result_package(manifest, files)

    def test_rehashed_derived_topic_note_rejected_by_real_renderer(self):
        manifest, files = self.build(self.reviewed())
        name = next(name for name in files if name.startswith("view/Topics/"))
        files[name] += b"\nInvented claim not present in reviewed knowledge.\n"
        derived_path = manifest["provenance"]["derived_manifest"]["path"]
        derived = json.loads(files[derived_path])
        derived["files"][name.removeprefix("view/")] = hashlib.sha256(files[name]).hexdigest()
        files[derived_path] = canonical_json(derived) + b"\n"
        self.rehash_outer(manifest, files)
        with self.assertRaisesRegex(PublishingError, "derived note differs"):
            validate_reviewed_result_package(manifest, files)

    def test_rehashed_false_derived_resolver_or_coverage_rejected(self):
        manifest, files = self.build(self.reviewed())
        derived_path = manifest["provenance"]["derived_manifest"]["path"]
        original = files[derived_path]
        for field in ("resolver_states", "coverage"):
            with self.subTest(field=field):
                derived = json.loads(original)
                if field == "resolver_states":
                    derived[field] = {key: "AVAILABLE" for key in derived[field]}
                else:
                    derived[field]["full_seminar_coverage"] = False
                files[derived_path] = canonical_json(derived) + b"\n"
                self.rehash_outer(manifest, files)
                with self.assertRaisesRegex(PublishingError, "derived manifest coverage or resolver"):
                    validate_reviewed_result_package(manifest, files)

    def test_no_result_means_no_semantic_replay(self):
        package = self.fixture.prepare()
        with self.assertRaises(ValueError):
            self.build({"decisions_path": str(Path(package["package_path"]).parent.parent / "decisions.json")})
        self.assertFalse(list(self.fixture.project.rglob("canonical_knowledge.json")))


class ReviewedPackagePureValidationTests(unittest.TestCase):
    def test_malformed_manifest_raises_transport_exception(self):
        with self.assertRaises(PublishingError):
            validate_reviewed_result_package({}, {})
