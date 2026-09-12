import json
import os
import zipfile
from pathlib import Path
import stat
import tempfile
import unittest

from integra_core.application_runtime import execute_run, prepare_run, read_run
from integra_core.capabilities import build_plan, detect_source


class ApplicationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(); self.root=Path(self.directory.name); self.project=self.root/"project"; self.project.mkdir()
        (self.project/"jobs.json").write_text('{"schema_version":"1.0","jobs":[]}')

    def tearDown(self): self.directory.cleanup()

    def media_environment(self):
        ffmpeg=self.root/"ffmpeg"; ffmpeg.write_text("#!/bin/sh\nsrc=''\nprev=''\nfor arg in \"$@\"; do [ \"$prev\" = '-i' ] && src=$arg; prev=$arg; out=$arg; done\ncp \"$src\" \"$out\"\n")
        whisper=self.root/"whisper"; whisper.write_text("#!/bin/sh\nout=''\nwhile [ $# -gt 0 ]; do [ \"$1\" = '-of' ] && { shift; out=$1; }; shift; done\nprintf '1\\n00:00:00,000 --> 00:00:01,000\\nReal result\\n' > \"$out.srt\"\n")
        for item in (ffmpeg,whisper): item.chmod(item.stat().st_mode|stat.S_IXUSR)
        model=self.root/"model"; model.write_bytes(b"model")
        return {"INTEGRA_FFMPEG":str(ffmpeg),"INTEGRA_WHISPER_CLI":str(whisper),"INTEGRA_WHISPER_MODEL":str(model)}

    def test_executes_selected_real_media_outputs_without_semantic_fakes(self):
        source_path=self.root/"audio.wav"; source_path.write_bytes(b"audio"); overrides=self.media_environment(); old={key:os.environ.get(key) for key in overrides}
        try:
            os.environ.update(overrides); plan=build_plan([detect_source(str(source_path))],["subtitles"]); run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        finally:
            for key,value in old.items():
                if value is None: os.environ.pop(key,None)
                else: os.environ[key]=value
        self.assertEqual(result["state"],"COMPLETED"); outputs=result["source_results"][0]["outputs"]
        self.assertEqual(result["source_results"][0]["display_name"],"audio.wav")
        self.assertTrue(Path(outputs["transcript"]).is_file()); self.assertTrue(Path(outputs["subtitles"]).is_file())
        self.assertTrue(outputs["transcript"].endswith(".txt"))
        self.assertEqual(Path(outputs["transcript"]).name, "transcript.txt")
        self.assertTrue(Path(outputs["transcript_json"]).is_file())
        artifact=Path(outputs["transcript"]).parent
        self.assertFalse((artifact/"topics.json").exists()); self.assertFalse((artifact/"knowledge.json").exists())

    def test_executes_native_document_extraction(self):
        source_path=self.root/"notes.md"; source_path.write_text("# Heading\nActual document text")
        source=detect_source(str(source_path)); plan=build_plan([source],["document_text","document_structure"])
        run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"COMPLETED"); outputs=result["source_results"][0]["outputs"]
        self.assertEqual(result["source_results"][0]["display_name"],"notes.md")
        self.assertIn("Actual document text",Path(outputs["text"]).read_text())
        self.assertTrue(str(outputs["text"]).endswith(".txt"))
        self.assertTrue(Path(outputs["document_structure"]).is_file())
        structure=json.loads(Path(outputs["document_structure"]).read_bytes())
        self.assertGreaterEqual(structure["entry_count"],1)
        record=json.loads(Path(outputs["document_record"]).read_bytes()); self.assertEqual(record["ocr"]["status"],"NOT_REQUIRED")
        self.assertEqual(read_run(self.project,run["run_id"])["state"],"COMPLETED")

    def test_executes_document_discovery_output_for_docx_without_embeds(self):
        source_path=self.root/"empty.docx"
        with zipfile.ZipFile(source_path,"w") as container:
            container.writestr("word/document.xml",
                               b'<?xml version="1.0" encoding="UTF-8"?>'
                               b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                               b'<w:body><w:p><w:r><w:t>Docx test</w:t></w:r></w:p></w:body>'
                               b'</w:document>')
        source=detect_source(str(source_path)); plan=build_plan([source],["discover_images"])
        run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"COMPLETED"); outputs=result["source_results"][0]["outputs"]
        self.assertTrue(Path(outputs["discover_images"]).is_file())
        discover=json.loads(Path(outputs["discover_images"]).read_bytes())
        self.assertIn("embedded_media",discover)

    def test_rejects_tampered_plan(self):
        source_path=self.root/"notes.md"; source_path.write_text("text")
        plan=build_plan([detect_source(str(source_path))],["document_text"]); plan["selected_outputs"]=["knowledge"]
        with self.assertRaises(ValueError): prepare_run(self.project,plan)

    def test_fails_closed_when_source_changes_after_plan_creation(self):
        source_path=self.root/"notes.md"; source_path.write_text("first")
        plan=build_plan([detect_source(str(source_path))],["document_text"])
        run=prepare_run(self.project,plan); source_path.write_text("other")
        with self.assertRaisesRegex(ValueError,"changed after plan creation"):
            execute_run(self.project,run["run_id"])
        self.assertEqual(read_run(self.project,run["run_id"])["state"],"FAILED")


if __name__=="__main__": unittest.main()
