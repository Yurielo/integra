import hashlib
import json
import os
import zipfile
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

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

    def youtube_downloader(self):
        downloader=self.root/"yt-dlp"
        downloader.write_text("#!/bin/sh\n"
                              "if [ \"$1\" = \"--version\" ]; then echo 2026.01.01; exit 0; fi\n"
                              "previous=''\n"
                              "for arg in \"$@\"; do [ \"$previous\" = \"--output\" ] && output=$arg; previous=$arg; done\n"
                              "target=$(printf '%s' \"$output\" | sed 's/%(ext)s/mp3/')\n"
                              "printf 'downloaded-media' > \"$target\"\n")
        downloader.chmod(downloader.stat().st_mode|stat.S_IXUSR)
        return str(downloader)

    def test_downloads_selected_youtube_video_into_owned_project_storage(self):
        old=os.environ.get("INTEGRA_YTDLP")
        try:
            os.environ["INTEGRA_YTDLP"]=self.youtube_downloader()
            source=detect_source("https://www.youtube.com/watch?v=real-video")
            plan=build_plan([source],["youtube_ingest"])
            self.assertEqual([stage["id"] for stage in plan["stages"]],["youtube_ingest"])
            run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        finally:
            if old is None: os.environ.pop("INTEGRA_YTDLP",None)
            else: os.environ["INTEGRA_YTDLP"]=old
        self.assertEqual(result["state"],"COMPLETED")
        outputs=result["source_results"][0]["outputs"]
        self.assertEqual(Path(outputs["downloaded_media"]).read_bytes(),b"downloaded-media")
        record=json.loads(Path(outputs["youtube_source_record"]).read_bytes())
        self.assertEqual(record["source_url"],source["input"])
        self.assertEqual(record["content_sha256"],hashlib.sha256(b"downloaded-media").hexdigest())

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

    def test_executes_selected_topics_as_review_required_seminartext_drafts(self):
        source_path=self.root/"audio.wav"; source_path.write_bytes(b"audio")
        overrides=self.media_environment(); old={key:os.environ.get(key) for key in overrides}

        def timeline_drafts(_audio, _subtitles, output):
            output.write_text(json.dumps({"capability":"word_timeline", "words":[{"alignment_status":"ALIGNED"}]}))
            return json.loads(output.read_text())

        def topic_drafts(subtitles, output):
            self.assertTrue(subtitles.is_file())
            output.write_text(json.dumps({"component":"seminartext", "topics":[{"semantic_status":"REVIEW_REQUIRED"}]}))
            return json.loads(output.read_text())

        try:
            os.environ.update(overrides)
            with patch("integra_core.capabilities.seminartext_preflight", return_value={"state":"READY"}), \
                 patch("integra_core.capabilities.word_timeline_preflight", return_value={"state":"READY"}), \
                 patch("integra_core.user_media.generate_word_timeline", side_effect=timeline_drafts) as generated_timeline, \
                 patch("integra_core.user_media.generate_topics", side_effect=topic_drafts) as generated:
                plan=build_plan([detect_source(str(source_path))],["topics"])
                self.assertEqual([stage["id"] for stage in plan["stages"]], ["media_preparation", "transcript", "word_timeline", "topics"])
                run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        finally:
            for key,value in old.items():
                if value is None: os.environ.pop(key,None)
                else: os.environ[key]=value
        self.assertEqual(result["state"],"COMPLETED")
        outputs=result["source_results"][0]["outputs"]
        self.assertTrue(Path(outputs["transcript"]).is_file())
        self.assertTrue(Path(outputs["subtitles"]).is_file())
        self.assertTrue(Path(outputs["word_timeline"]).is_file())
        self.assertTrue(Path(outputs["topics"]).is_file())
        generated_timeline.assert_called_once()
        generated.assert_called_once()
        self.assertEqual(json.loads(Path(outputs["topics"]).read_text())["topics"][0]["semantic_status"], "REVIEW_REQUIRED")
        self.assertNotIn("knowledge", outputs)

    def test_burns_generated_subtitles_into_local_video(self):
        source_path=self.root/"video.mp4"; source_path.write_bytes(b"video")
        overrides=self.media_environment(); old={key:os.environ.get(key) for key in overrides}
        try:
            os.environ.update(overrides); plan=build_plan([detect_source(str(source_path))],["burn_subtitles"])
            run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        finally:
            for key,value in old.items():
                if value is None: os.environ.pop(key,None)
                else: os.environ[key]=value
        outputs=result["source_results"][0]["outputs"]
        self.assertTrue(Path(outputs["burned_video"]).is_file())
        self.assertEqual(Path(outputs["burned_video"]).read_bytes(),b"video")

    def test_enhances_audio_without_requiring_transcription_runtime(self):
        source_path=self.root/"audio.wav"; source_path.write_bytes(b"audio")
        ffmpeg=self.root/"ffmpeg"; ffmpeg.write_text("#!/bin/sh\nsrc=''\nprev=''\nfor arg in \"$@\"; do [ \"$prev\" = '-i' ] && src=$arg; prev=$arg; out=$arg; done\ncp \"$src\" \"$out\"\n")
        ffmpeg.chmod(ffmpeg.stat().st_mode|stat.S_IXUSR)
        old={key:os.environ.get(key) for key in ("INTEGRA_FFMPEG","INTEGRA_WHISPER_CLI","INTEGRA_WHISPER_MODEL")}
        try:
            os.environ["INTEGRA_FFMPEG"]=str(ffmpeg)
            os.environ.pop("INTEGRA_WHISPER_CLI",None); os.environ.pop("INTEGRA_WHISPER_MODEL",None)
            plan=build_plan([detect_source(str(source_path))],["enhance_audio"])
            run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        finally:
            for key,value in old.items():
                if value is None: os.environ.pop(key,None)
                else: os.environ[key]=value
        self.assertEqual(result["state"],"COMPLETED")
        outputs=result["source_results"][0]["outputs"]
        self.assertEqual(Path(outputs["enhanced_audio"]).read_bytes(),b"audio")
        record=json.loads(Path(outputs["audio_enhancement_record"]).read_bytes())
        self.assertEqual(record["engine"],"ffmpeg")
        self.assertNotIn("transcript",outputs)

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

    def test_materializes_embedded_images_through_the_application_runtime(self):
        png=bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
            "0000000a49444154789c636000000002000148afa4710000000049454e44ae426082"
        )
        source_path=self.root/"illustrated.docx"
        with zipfile.ZipFile(source_path,"w") as container:
            container.writestr("word/document.xml",
                               b'<?xml version="1.0" encoding="UTF-8"?>'
                               b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                               b'<w:body><w:p><w:r><w:t>Illustrated document</w:t></w:r></w:p></w:body></w:document>')
            container.writestr("word/media/image1.png",png)
        source=detect_source(str(source_path)); plan=build_plan([source],["extract_images"])
        run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"COMPLETED"); outputs=result["source_results"][0]["outputs"]
        manifest=json.loads(Path(outputs["embedded_images_manifest"]).read_bytes())
        self.assertEqual(manifest["embedded_media_count"],1)
        image_path=Path(outputs["embedded_images_directory"])/manifest["embedded_media"][0]["relative_path"]
        self.assertEqual(image_path.read_bytes(),png)

    def test_executes_booktext_ocr_for_a_scanned_image_without_inventing_text(self):
        png=bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
            "0000000a49444154789c636000000002000148afa4710000000049454e44ae426082"
        )
        source_path=self.root/"scan.png"; source_path.write_bytes(png)
        result_dir=self.root/"booktext-result"; result_dir.mkdir()
        (result_dir/"book_clean.txt").write_text("Actual OCR text\n")
        (result_dir/"book.md").write_text("# Actual OCR text\n")
        actual={"component":"booktext","commit_sha":"46396649214275eb18054b670a842bace02d02e1",
                "entrypoint_sha256":"a"*64,"runtime":{"model_sha256":"b"*64},
                "blocks":[{"unit_index":1,"text":"Actual OCR text","confidence":0.75}]}
        with patch("integra_core.capabilities.booktext_preflight",return_value={"state":"READY"}), \
             patch("integra_core.application_runtime.run_booktext_ocr") as invoked:
            def materialize(_source, destination):
                import shutil
                shutil.copytree(result_dir,destination)
                return actual
            invoked.side_effect=materialize
            source=detect_source(str(source_path)); plan=build_plan([source],["document_text"])
            run=prepare_run(self.project,plan); completed=execute_run(self.project,run["run_id"])
        outputs=completed["source_results"][0]["outputs"]
        self.assertEqual(Path(outputs["text"]).read_text(),"Actual OCR text\n")
        self.assertEqual(Path(outputs["booktext_text"]).read_text(),"Actual OCR text\n")
        record=json.loads(Path(outputs["document_record"]).read_bytes())
        self.assertEqual(record["ocr"]["status"],"COMPLETE")
        self.assertEqual(record["ocr"]["blocks"][0]["text"],"Actual OCR text")
        self.assertNotIn("knowledge",outputs)
        invoked.assert_called_once()

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
