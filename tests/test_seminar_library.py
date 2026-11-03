import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys

from scripts.seminar_library_preview import build, canonical, validate
from integra_core.projects_sources import new_registry, register_project, register_youtube_video


class SeminarLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(value))
        return path

    def fixtures(self):
        st_root = self.root / "seminartext"
        (st_root / "seminar.yaml").parent.mkdir(parents=True, exist_ok=True)
        (st_root / "seminar.yaml").write_text("id: seminar_fixture\ntitle: Synthetic seminar\n")
        (st_root / "source/video").mkdir(parents=True)
        (st_root / "source/video/first.mp4").write_bytes(b"fixture media")
        (st_root / "source/video/disconnected.mp4").symlink_to(self.root / "offline" / "disconnected.mp4")
        st = self.write("seminartext/sources.json", {"schema_version": 1,
            "videos": [{"source_id":"video_001","type":"local","file":"source/video/first.mp4"},
                       {"source_id":"video_002","type":"local","file":"source/video/disconnected.mp4"},
                       {"source_id":"video_003","type":"youtube","url":"https://www.youtube.com/watch?v=abcdefghijk"}],
            "documents": [{"source_id":"doc_001","type":"other","file":"source/documents/missing.pdf"}]})
        evidence_bytes=canonical({"schema_version":"1.0.0","artifact_type":"seminartext.canonical_evidence","artifact_id":"synthetic_evidence"})
        (st_root/"evidence").mkdir()
        (st_root/"evidence/canonical_bundle.json").write_bytes(evidence_bytes)
        self.write("seminartext/evidence/manifest.json", {"schema_version":2,"artifact_type":"seminartext.project_evidence_manifest",
            "bundle_path":"evidence/canonical_bundle.json","bundle_sha256":hashlib.sha256(evidence_bytes).hexdigest(),
            "source_count":1,"registered_source_count":4,"all_registered_sources_composed":False,
            "registry_coverage":[{"source_registry_id":"video_001","evidence_status":"COMPOSED"},
                                 {"source_registry_id":"video_002","evidence_status":"EVIDENCE_UNAVAILABLE"},
                                 {"source_registry_id":"video_003","evidence_status":"EVIDENCE_UNAVAILABLE"},
                                 {"source_registry_id":"doc_001","evidence_status":"EVIDENCE_UNAVAILABLE"}]})
        vt_root = self.root / "videotext"
        (vt_root / "output.txt").parent.mkdir(parents=True, exist_ok=True)
        (vt_root / "output.txt").write_text("one")
        (vt_root / "output2.txt").write_text("two")
        vt = self.write("videotext/Support files/manifest.json", {"schemaVersion": 8,
            "sourceMediaPath": str(st_root / "source/video/first.mp4"),
            "sourceFingerprint":{"standardizedPath":str(st_root / "source/video/first.mp4"),"fileSize":13,"modificationTime":1},
            "artifacts":[{"id":"transcript-1","kind":"transcript","path":"output.txt","contentHash":hashlib.sha256(b"one").hexdigest(),"generatorVersion":"8"},
                         {"id":"topics-1","kind":"topics","path":"output2.txt","contentHash":None,"generatorVersion":"8"}]})
        bt_root = self.root / "booktext"
        shared_hash = hashlib.sha256(b"fixture media").hexdigest()
        document = {"schema_version":"0.1","artifact_type":"booktext.document","document_id":"document-1","revision_id":"revision-1",
                    "sources":[{"source_id":"source-1","filename":"missing.pdf","sha256":shared_hash,"source_index":1}],"pages":[]}
        doc = self.write("booktext/document.json",document)
        bt = self.write("booktext/manifest.json", {"schema_version":"0.1","artifact_type":"booktext.package_manifest",
            "document_id":"document-1","revision_id":"revision-1","package_status":"REVIEW_REQUIRED",
            "files":[{"filename":"document.json","sha256":hashlib.sha256(doc.read_bytes()).hexdigest()}]})
        registry = new_registry("fixture", "2026-10-28T00:00:00Z")
        registry, project_id = register_project(registry, project_key="seminar", kind="SEMINAR", title="Synthetic", occurred_at="2026-10-28T00:00:00Z")
        registry, _ = register_youtube_video(registry, project_id, video_id="abcdefghijk", title="Remote", availability="AVAILABLE", captured_at="2026-10-28T00:01:00Z")
        integ = self.write("integra/registry.json", registry)
        return [("seminartext",st),("videotext",vt),("booktext",bt),("integra",integ)]

    def test_multi_product_read_only_deterministic_preview(self):
        specs=self.fixtures()
        before={str(p):p.read_bytes() for p in self.root.rglob("*") if p.is_file() and not p.is_symlink()}
        output=build(specs,excluded=[specs[2][1]],classified=[specs[1][1]])
        self.assertEqual(canonical(output),canonical(build(list(reversed(specs)),excluded=[specs[2][1]],classified=[specs[1][1]])))
        self.assertEqual(output["summary"]["project_count"],4)
        self.assertEqual(output["summary"]["source_count"],6)
        self.assertEqual(output["summary"]["artifact_count"],3)
        self.assertEqual(output["summary"]["excluded_projects"],1)
        self.assertGreaterEqual(output["summary"]["missing_sources"],2)
        self.assertEqual({s["availability"] for s in output["sources"] if s["owner"]=="seminartext"},{"AVAILABLE","MISSING","SYMLINK","UNVERIFIED_REMOTE"})
        self.assertEqual(next(s for s in output["sources"] if s["source_type"]=="YOUTUBE_VIDEO" and s["owner"]=="seminartext")["provenance"]["youtube_video_id"],"abcdefghijk")
        self.assertTrue(any(x.startswith("INCOMPLETE_CONTENT_HASH:") for x in output["diagnostics"]))
        self.assertTrue(any(x.startswith("DUPLICATE_CANDIDATE:") for x in output["diagnostics"]) is False)
        self.assertEqual(before,{p:Path(p).read_bytes() for p in before})
        validate(output)

    def test_unsupported_malformed_and_stale_package(self):
        specs=self.fixtures()
        vt=specs[1][1]
        original=json.loads(vt.read_text());original["schemaVersion"]=7
        vt.write_bytes(canonical(original))
        bad=self.write("bad.json",{"schemaVersion":99})
        malformed=self.root / "malformed.json";malformed.write_text("{")
        output=build([("videotext",vt),("videotext",bad)])
        self.assertEqual(output["summary"]["unsupported_manifests"],2)
        with self.assertRaisesRegex(ValueError,"malformed manifest"):
            build([("videotext",malformed)])
        doc=self.root / "booktext/document.json";doc.write_text("{}")
        stale=build([specs[2]])
        self.assertEqual(stale["summary"]["unsupported_manifests"],1)

    def test_manifest_parent_symlink_is_rejected(self):
        specs = self.fixtures()
        alias = self.root / "manifest-alias"
        alias.symlink_to(specs[0][1].parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "manifest path is unsafe"):
            build([("seminartext", alias / "sources.json")])

    def test_duplicate_content_candidate_is_never_merged(self):
        specs=self.fixtures()
        bt=specs[2][1]
        (bt.parent/"missing.pdf").write_bytes(b"unrelated same-name file")
        d=json.loads((bt.parent/"document.json").read_text())
        d["sources"].append({**d["sources"][0],"source_id":"source-2","source_index":2})
        doc=self.write("booktext/document.json",d)
        manifest=json.loads(bt.read_text());manifest["files"][0]["sha256"]=hashlib.sha256(doc.read_bytes()).hexdigest()
        bt.write_bytes(canonical(manifest))
        output=build([("booktext",bt)])
        self.assertEqual(output["summary"]["source_count"],2)
        self.assertEqual(output["summary"]["duplicate_candidate_references"],1)
        self.assertTrue(all(s["availability"]=="UNKNOWN" and s["locator"] is None for s in output["sources"]))

    def test_supported_cli_preview_and_shared_native_source_reference(self):
        specs=self.fixtures()
        registry_path=specs[3][1]
        from integra_core.projects_sources import register_project, register_youtube_video
        registry=json.loads(registry_path.read_text())
        registry,second=register_project(registry,project_key="seminar-two",kind="SEMINAR",title="Second",occurred_at="2026-10-28T00:02:00Z")
        registry,_=register_youtube_video(registry,second,video_id="abcdefghijk",title="Remote",availability="AVAILABLE",captured_at="2026-10-28T00:03:00Z")
        registry_path.write_bytes(canonical(registry))
        cmd=[sys.executable,"-m","scripts.seminar_library_preview"]
        for owner,path in specs:cmd.extend(["--"+owner,str(path)])
        first=subprocess.check_output(cmd,cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(first,subprocess.check_output(cmd,cwd=Path(__file__).resolve().parents[1]))
        output=json.loads(first)
        self.assertEqual(output["summary"]["project_count"],5)
        integ=[s for s in output["sources"] if s["owner"]=="integra"]
        self.assertEqual(len(integ),2)
        self.assertEqual(len({s["native_id"] for s in integ}),1)
        self.assertEqual(len({s["key"] for s in integ}),2)
        self.assertEqual(len(integ[0]["revisions"]),2)

    def test_unknown_exclusion_and_tampered_registry_fail_closed(self):
        specs=self.fixtures()
        with self.assertRaisesRegex(ValueError,"not supplied"):
            build(specs,excluded=[self.root/"unknown.json"])
        with self.assertRaisesRegex(ValueError,"unknown native project"):
            build(specs,excluded_projects=["integra:missing"])
        registry=json.loads(specs[3][1].read_text())
        without_integra=build(specs,excluded_projects=["integra:"+registry["projects"][0]["project_id"]])
        self.assertEqual(without_integra["summary"]["excluded_projects"],1)
        self.assertFalse(any(s["owner"]=="integra" for s in without_integra["sources"]))
        path=specs[3][1]
        registry["projects"][0]["title"]="Tampered"
        path.write_bytes(canonical(registry))
        output=build([("integra",path)])
        self.assertEqual(output["summary"]["unsupported_manifests"],1)
        with self.assertRaisesRegex(ValueError,"summary count mismatch"):
            preview=build([("seminartext",specs[0][1])]);preview["summary"]["source_count"]=0;validate(preview)

    def test_nested_malformed_records_and_unsafe_absolute_locator(self):
        specs=self.fixtures()
        st=specs[0][1];s=json.loads(st.read_text());s["videos"][0]["file"]=str(self.root/"seminartext/../unrelated.mp4")
        st.write_bytes(canonical(s))
        output=build([("seminartext",st)])
        self.assertEqual(next(x for x in output["sources"] if x["native_id"]=="video_001")["availability"],"UNSAFE_LOCATION")
        s["videos"][0]["type"]="unknown-future-type";st.write_bytes(canonical(s))
        self.assertEqual(build([("seminartext",st)])["summary"]["unsupported_manifests"],1)
        vt=specs[1][1];v=json.loads(vt.read_text());v["transcriptRevisions"]=[42];vt.write_bytes(canonical(v))
        self.assertEqual(build([("videotext",vt)])["summary"]["unsupported_manifests"],1)
        v.pop("transcriptRevisions");v.pop("artifacts");vt.write_bytes(canonical(v))
        self.assertEqual(build([("videotext",vt)])["summary"]["artifact_count"],0)
        v["artifacts"]=False;vt.write_bytes(canonical(v))
        self.assertEqual(build([("videotext",vt)])["summary"]["unsupported_manifests"],1)
        bt=specs[2][1];d=json.loads((bt.parent/"document.json").read_text());d["sources"]=[42]
        doc=self.write("booktext/document.json",d);m=json.loads(bt.read_text());m["files"][0]["sha256"]=hashlib.sha256(doc.read_bytes()).hexdigest();bt.write_bytes(canonical(m))
        self.assertEqual(build([("booktext",bt)])["summary"]["unsupported_manifests"],1)
        m["files"]=[42];bt.write_bytes(canonical(m))
        self.assertEqual(build([("booktext",bt)])["summary"]["unsupported_manifests"],1)

    def test_stale_evidence_bundle_and_coverage_fail_closed(self):
        specs=self.fixtures();st=specs[0][1]
        bundle=st.parent/"evidence/canonical_bundle.json"
        original=bundle.read_bytes()
        bundle.write_text("{}")
        self.assertEqual(build([("seminartext",st)])["summary"]["unsupported_manifests"],1)
        bundle.write_bytes(original)
        evidence=st.parent/"evidence/manifest.json"
        e=json.loads(evidence.read_text());e["registry_coverage"].pop();evidence.write_bytes(canonical(e))
        result=build([("seminartext",st)])
        self.assertEqual(result["summary"]["unsupported_manifests"],1)
        self.assertTrue(any("coverage count mismatch" in d for d in result["diagnostics"]))

    def test_resealed_orphan_reference_is_rejected(self):
        specs=self.fixtures()
        preview=build([specs[1]])
        preview["artifacts"][0]["source_ids"]=["nonexistent"]
        from scripts.seminar_library_preview import digest
        preview["catalog_sha256"]=digest(canonical({k:v for k,v in preview.items() if k!="catalog_sha256"}))
        with self.assertRaisesRegex(ValueError,"orphan artifact"):
            validate(preview)


if __name__=="__main__":unittest.main()
