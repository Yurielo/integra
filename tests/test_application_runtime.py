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
from tests.asr_tools import media_environment
from tests.test_videotext_media_runtime import real_media_fixture


class ApplicationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(); self.root=Path(self.directory.name); self.project=self.root/"project"; self.project.mkdir()
        (self.project/"jobs.json").write_text('{"schema_version":"1.0","jobs":[]}')

    def tearDown(self): self.directory.cleanup()

    def media_environment(self):
        return media_environment(self.root)

    def local_media_plan(self, *names):
        sources=[]
        for name in names:
            path=self.root/name; path.write_bytes(name.encode("utf-8"))
            sources.append(detect_source(str(path)))
        with patch("integra_core.capabilities.preflight",return_value={"state":"READY"}):
            return build_plan(sources,["transcript"]), sources

    def prepare_media_run(self, plan, *, recognition_mode="normal", source_speech_language="ru"):
        # The plan was built through the normal capability contract above;
        # this focused runtime test intentionally avoids local model discovery.
        with patch("integra_core.application_runtime.build_plan",return_value=plan):
            return prepare_run(self.project,plan,recognition_mode=recognition_mode,
                               source_speech_language=source_speech_language)

    def test_careful_recognition_mode_is_validated_and_persisted_to_media_jobs(self):
        plan, sources = self.local_media_plan("careful.wav")
        run = self.prepare_media_run(plan)
        self.assertEqual(run["recognition"]["requested_mode"], "normal")
        careful = self.prepare_media_run(plan, recognition_mode="careful")
        observed = []
        def runner(_project, job_id):
            job = json.loads((self.project / "jobs.json").read_bytes())["jobs"][-1]
            self.assertEqual(job["job_id"], job_id)
            observed.append(job)
            return {"state": "COMPLETED", "outputs": {}, "recognition": {
                "requested_mode": "careful", "executed_mode": "careful", "runtime": {"component": "test"}}}
        with patch("integra_core.application_runtime.run_job", side_effect=runner):
            completed = execute_run(self.project, careful["run_id"])
        self.assertEqual(observed[0]["recognition_mode"], "careful")
        self.assertEqual(completed["recognition"]["requested_mode"], "careful")
        self.assertEqual(completed["source_results"][0]["recognition"]["executed_mode"], "careful")
        with self.assertRaisesRegex(ValueError, "recognition mode"):
            self.prepare_media_run(plan, recognition_mode="draft")

    def test_source_speech_language_is_validated_persisted_and_sent_to_media_jobs(self):
        plan, _ = self.local_media_plan("language.wav")
        run = self.prepare_media_run(plan, source_speech_language="ru")
        self.assertEqual(run["source_speech_language"], {"requested": "ru"})
        observed = []
        def runner(_project, job_id):
            job = json.loads((self.project / "jobs.json").read_bytes())["jobs"][-1]
            self.assertEqual(job["job_id"], job_id)
            observed.append(job)
            return {"state": "COMPLETED", "outputs": {}, "source_speech_language": {
                "requested": "ru", "executed": "ru", "mode": "FIXED"}}
        with patch("integra_core.application_runtime.run_job", side_effect=runner):
            completed = execute_run(self.project, run["run_id"])
        self.assertEqual(observed[0]["source_speech_language"], "ru")
        self.assertEqual(completed["source_speech_language"]["executed"], "ru")
        self.assertEqual(completed["source_results"][0]["source_speech_language"]["executed"], "ru")
        with self.assertRaisesRegex(ValueError, "source-speech language"):
            self.prepare_media_run(plan, source_speech_language="en")

    def source_job_runner(self, *, failed=(), cancelled=(), reused=()):
        """Deterministic source-job boundary: no ASR/model runtime is invoked."""
        calls=[]; artifacts=self.project/"test-artifacts"; artifacts.mkdir(exist_ok=True)
        def run(_project, job_id):
            job=json.loads((self.project/"jobs.json").read_bytes())["jobs"][-1]
            self.assertEqual(job["job_id"],job_id)
            source_id=job["source_id"]; calls.append(source_id)
            if source_id in failed: raise ValueError("controlled corrupt-source failure")
            if source_id in cancelled: return {"state":"CANCELLED","outputs":{}}
            output=artifacts/(source_id.rsplit(":",1)[-1]+".txt"); output.write_text(source_id)
            result={"state":"COMPLETED","outputs":{"transcript":str(output)}}
            if source_id in reused: result["asr_reuse"]={"state":"REUSED"}
            return result
        return calls, run

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

    def youtube_playlist_downloader(self):
        downloader=self.root/"yt-dlp-playlist"
        downloader.write_text("#!/bin/sh\n"
                              "if [ \"$1\" = \"--version\" ]; then echo 2026.01.01; exit 0; fi\n"
                              "for arg in \"$@\"; do [ \"$arg\" = \"--flat-playlist\" ] && { echo '{\"id\":\"PL-real\",\"entries\":[{\"id\":\"video-a\",\"title\":\"First real video\",\"duration\":12,\"filesize_approx\":42},{\"id\":\"video-b\",\"title\":\"Second real video\",\"duration\":8,\"filesize\":24}]}'; exit 0; }; done\n"
                              "previous=''\n"
                              "for arg in \"$@\"; do [ \"$previous\" = \"--output\" ] && output=$arg; previous=$arg; done\n"
                              "target=$(printf '%s' \"$output\" | sed 's/%(ext)s/mp3/')\n"
                              "printf 'playlist-media' > \"$target\"\n")
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

    def test_downloads_youtube_playlist_sequentially_with_persisted_live_membership(self):
        old=os.environ.get("INTEGRA_YTDLP")
        try:
            os.environ["INTEGRA_YTDLP"]=self.youtube_playlist_downloader()
            source=detect_source("https://www.youtube.com/playlist?list=PL-real")
            plan=build_plan([source],["youtube_playlist_ingest"])
            self.assertEqual([stage["id"] for stage in plan["stages"]],["youtube_playlist_ingest"])
            run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        finally:
            if old is None: os.environ.pop("INTEGRA_YTDLP",None)
            else: os.environ["INTEGRA_YTDLP"]=old
        self.assertEqual(result["state"],"COMPLETED")
        outputs=result["source_results"][0]["outputs"]
        discovery=json.loads(Path(outputs["playlist_discovery"]).read_bytes())
        checkpoint=json.loads(Path(outputs["playlist_checkpoint"]).read_bytes())
        downloads=json.loads(Path(outputs["playlist_downloads"]).read_bytes())
        self.assertEqual([item["video_id"] for item in discovery["items"]],["video-a","video-b"])
        self.assertFalse(discovery["network_access_performed"])
        self.assertEqual(checkpoint["status"],"COMPLETE")
        self.assertEqual([item["video_id"] for item in checkpoint["completed"]],["video-a","video-b"])
        self.assertEqual(sorted(downloads),["video-a","video-b"])
        self.assertTrue(all((Path(outputs["playlist_artifacts_directory"])/item["relative_path"]).is_file() for item in checkpoint["completed"]))

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

        def timeline_drafts(_audio, _subtitles, output, *, diagnostic_context):
            self.assertEqual(diagnostic_context["stage"], "word_timeline")
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
        source_path=self.root/"video.mp4"; real_media_fixture(source_path)
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
        self.assertEqual(result["state"],"COMPLETED",result)
        self.assertGreater(Path(outputs["burned_video"]).stat().st_size,100)
        self.assertNotEqual(Path(outputs["burned_video"]).read_bytes(),source_path.read_bytes())

    def test_real_video_analysis_and_speed_do_not_invoke_asr(self):
        source=self.root/"video.mp4"; ffmpeg=real_media_fixture(source)
        with patch.dict(os.environ,{"INTEGRA_FFMPEG":ffmpeg}), \
             patch("integra_core.user_media.asr.transcribe",side_effect=AssertionError("ASR must not run")):
            plan=build_plan([detect_source(str(source))],["audio_analysis","speed_video"])
            run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"COMPLETED",result)
        outputs=result["source_results"][0]["outputs"]
        self.assertTrue(Path(outputs["audio_analysis"]).is_file())
        self.assertTrue(Path(outputs["speed_video"]).is_file())
        self.assertNotIn("transcript",outputs)
        self.assertIn("integratedLoudnessLUFS",json.loads(Path(outputs["audio_analysis"]).read_text()))

    def test_mixed_topics_and_real_burn_both_execute(self):
        source=self.root/"mixed.mp4"; real_media_fixture(source)
        overrides=self.media_environment()
        def timeline(_audio,_subtitles,output):
            output.write_text(json.dumps({"capability":"word_timeline","words":[{"alignment_status":"ALIGNED"}]}))
            return json.loads(output.read_text())
        def topics(_subtitles,output):
            output.write_text(json.dumps({"component":"seminartext","topics":[{"semantic_status":"REVIEW_REQUIRED"}]}))
            return json.loads(output.read_text())
        # ASR/topic fixtures isolate semantic model costs; VideoText really renders.
        with patch.dict(os.environ,overrides), \
             patch("integra_core.capabilities.seminartext_preflight",return_value={"state":"READY"}), \
             patch("integra_core.capabilities.word_timeline_preflight",return_value={"state":"READY"}), \
             patch("integra_core.user_media.generate_word_timeline",side_effect=timeline), \
             patch("integra_core.user_media.generate_topics",side_effect=topics) as topic_call:
            plan=build_plan([detect_source(str(source))],["topics","burn_subtitles"])
            run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"COMPLETED",result)
        outputs=result["source_results"][0]["outputs"]
        self.assertTrue(Path(outputs["burned_video"]).is_file())
        self.assertEqual(json.loads(Path(outputs["topics"]).read_text())["topics"][0]["semantic_status"],"REVIEW_REQUIRED")
        topic_call.assert_called_once()

    def test_videotext_cancellation_stays_cancelled_without_outputs(self):
        from integra_core.videotext_media_runtime import MediaCancelled
        source=self.root/"cancel.mp4"; source.write_bytes(b"cancellation-boundary-fixture")
        ffmpeg=self.root/"tool"; ffmpeg.write_text("#!/bin/sh\nexit 0\n"); ffmpeg.chmod(0o700)
        with patch.dict(os.environ,{"INTEGRA_FFMPEG":str(ffmpeg)}), \
             patch("integra_core.capabilities.media_component_preflight",return_value={"state":"READY"}), \
             patch("integra_core.user_media.videotext_media.process",side_effect=MediaCancelled("cancelled")):
            plan=build_plan([detect_source(str(source))],["speed_video"])
            run=prepare_run(self.project,plan); result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"CANCELLED",result)
        self.assertFalse(result["source_results"][0].get("outputs"))

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

    def test_suspicious_asr_fails_run_and_never_invokes_semantic_stages(self):
        from integra_core.seminartext_asr_runtime import ASRQualityError
        source_path=self.root/"audio.wav"; source_path.write_bytes(b"audio")
        with patch("tests.asr_tools.require_asr_runtime"):
            overrides=self.media_environment()
        report=self.project/"quality.txt"; report.write_text("Suspicious chunk requires audio review")
        record=self.project/"asr.json"; record.write_text('{"suspicious_chunks":1}')
        error=ASRQualityError("Suspicious ASR", {"review_txt":str(report), "record":str(record),
            "provenance":{"mode":"normal", "executed_source_speech_language":"ru",
            "source_speech_language_mode":"FIXED", "quality_diagnostics":{
                "status":"REQUIRES_ATTENTION", "suspicious_chunks":1,
                "protective_retry_count":1, "recovered_after_retry_count":0}}})
        with patch.dict(os.environ, overrides), \
             patch("integra_core.user_media.asr.preflight",return_value={"state":"READY"}), \
             patch("integra_core.capabilities.seminartext_preflight",return_value={"state":"READY"}), \
             patch("integra_core.capabilities.word_timeline_preflight",return_value={"state":"READY"}), \
             patch("integra_core.user_media.asr_reuse.transcribe_or_reuse",side_effect=error), \
             patch("integra_core.user_media.generate_word_timeline") as alignment, \
             patch("integra_core.user_media.generate_topics") as topics:
            plan=build_plan([detect_source(str(source_path))],["topics"])
            run=prepare_run(self.project,plan)
            with self.assertRaises(ASRQualityError): execute_run(self.project,run["run_id"])
        alignment.assert_not_called(); topics.assert_not_called()
        persisted=read_run(self.project,run["run_id"])
        self.assertEqual(persisted["state"],"FAILED")
        self.assertEqual(persisted["error"], "Расшифровка не прошла проверку качества. Проверьте аудио и повторите обработку.")
        outputs=persisted["source_results"][0]["outputs"]
        self.assertEqual(outputs,{"transcript_quality_report":str(report),"transcript_asr_record":str(record)})
        self.assertNotIn("transcript",outputs)
        self.assertEqual(persisted["source_results"][0]["asr_diagnostics"]["status"], "REQUIRES_ATTENTION")

    def test_cancelled_media_result_never_promotes_run_to_completed(self):
        source=self.root/"audio.wav"; source.write_bytes(b"audio")
        with patch("tests.asr_tools.require_asr_runtime"):
            overrides=self.media_environment()
        with patch.dict(os.environ,overrides), \
             patch("integra_core.user_media.asr.preflight",return_value={"state":"READY"}), \
             patch("integra_core.application_runtime.run_job",return_value={"state":"CANCELLED"}):
            plan=build_plan([detect_source(str(source))],["transcript"])
            run=prepare_run(self.project,plan)
            result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"CANCELLED")
        self.assertEqual(read_run(self.project,run["run_id"])["state"],"CANCELLED")
        self.assertEqual(result["completed_sources"],0)
        self.assertIsNone(result["current_stage"])

    def test_multi_source_good_good_completes_in_selected_order(self):
        plan,sources=self.local_media_plan("first.wav","second.wav")
        calls,runner=self.source_job_runner()
        with patch("integra_core.application_runtime.run_job",side_effect=runner):
            run=self.prepare_media_run(plan); result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"COMPLETED")
        self.assertEqual([item["source_id"] for item in result["source_results"]],[item["source_id"] for item in sources])
        self.assertEqual(calls,[item["source_id"] for item in sources])
        self.assertEqual([item["state"] for item in result["source_results"]],["COMPLETED","COMPLETED"])

    def test_multi_source_good_corrupt_records_every_source_and_preserves_good_output(self):
        plan,sources=self.local_media_plan("good.wav","corrupt.mp3")
        calls,runner=self.source_job_runner(failed={sources[1]["source_id"]})
        with patch("integra_core.application_runtime.run_job",side_effect=runner):
            run=self.prepare_media_run(plan); result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"FAILED")
        self.assertEqual(calls,[item["source_id"] for item in sources])
        self.assertEqual([item["state"] for item in result["source_results"]],["COMPLETED","FAILED"])
        self.assertTrue(Path(result["source_results"][0]["outputs"]["transcript"]).is_file())
        self.assertEqual(result["source_results"][1]["outputs"],{})
        self.assertIn("controlled corrupt-source failure",result["source_results"][1]["error"])

    def test_multi_source_good_fail_good_continues_later_independent_source(self):
        plan,sources=self.local_media_plan("first.wav","failed.mp3","later.wav")
        calls,runner=self.source_job_runner(failed={sources[1]["source_id"]})
        with patch("integra_core.application_runtime.run_job",side_effect=runner):
            run=self.prepare_media_run(plan); result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"FAILED")
        self.assertEqual(calls,[item["source_id"] for item in sources])
        self.assertEqual([item["state"] for item in result["source_results"]],["COMPLETED","FAILED","COMPLETED"])
        self.assertEqual(result["completed_sources"],2)

    def test_multi_source_fail_good_is_truthfully_failed_but_runs_later_source(self):
        plan,sources=self.local_media_plan("failed.mp3","later.wav")
        calls,runner=self.source_job_runner(failed={sources[0]["source_id"]})
        with patch("integra_core.application_runtime.run_job",side_effect=runner):
            run=self.prepare_media_run(plan); result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"FAILED")
        self.assertEqual(calls,[item["source_id"] for item in sources])
        self.assertEqual([item["state"] for item in result["source_results"]],["FAILED","COMPLETED"])

    def test_multi_source_retry_keeps_prior_success_artifacts_and_never_reuses_failed_success(self):
        plan,sources=self.local_media_plan("good.wav","failed.mp3","later.wav")
        first_calls,first_runner=self.source_job_runner(failed={sources[1]["source_id"]},reused={sources[0]["source_id"]})
        with patch("integra_core.application_runtime.run_job",side_effect=first_runner):
            first=self.prepare_media_run(plan); failed=execute_run(self.project,first["run_id"])
        retained=Path(failed["source_results"][0]["outputs"]["transcript"])
        self.assertTrue(retained.is_file())
        self.assertNotIn("asr_reuse",failed["source_results"][1])
        second_calls,second_runner=self.source_job_runner(reused={sources[0]["source_id"],sources[2]["source_id"]})
        with patch("integra_core.application_runtime.run_job",side_effect=second_runner):
            retry=self.prepare_media_run(plan); completed=execute_run(self.project,retry["run_id"])
        self.assertEqual(completed["state"],"COMPLETED")
        self.assertEqual(second_calls,[item["source_id"] for item in sources])
        self.assertTrue(retained.is_file())
        self.assertEqual(completed["source_results"][1]["state"],"COMPLETED")
        self.assertEqual(first_calls,[item["source_id"] for item in sources])

    def test_multi_source_cancellation_stops_remaining_sources_and_preserves_preceding_result(self):
        plan,sources=self.local_media_plan("good.wav","cancel.wav","later.wav")
        calls,runner=self.source_job_runner(cancelled={sources[1]["source_id"]})
        with patch("integra_core.application_runtime.run_job",side_effect=runner):
            run=self.prepare_media_run(plan); result=execute_run(self.project,run["run_id"])
        self.assertEqual(result["state"],"CANCELLED")
        self.assertEqual(calls,[item["source_id"] for item in sources[:2]])
        self.assertEqual([item["state"] for item in result["source_results"]],["COMPLETED","CANCELLED"])
        self.assertTrue(Path(result["source_results"][0]["outputs"]["transcript"]).is_file())

    def test_fails_closed_when_source_changes_after_plan_creation(self):
        source_path=self.root/"notes.md"; source_path.write_text("first")
        plan=build_plan([detect_source(str(source_path))],["document_text"])
        run=prepare_run(self.project,plan); source_path.write_text("other")
        with self.assertRaisesRegex(ValueError,"changed after plan creation"):
            execute_run(self.project,run["run_id"])
        self.assertEqual(read_run(self.project,run["run_id"])["state"],"FAILED")


if __name__=="__main__": unittest.main()
