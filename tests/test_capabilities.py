import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from integra_core.capabilities import build_plan, capability_registry, detect_source


class CapabilityRegistryTests(unittest.TestCase):
    def media_runtime(self, root: Path):
        tool=root/"tool"; tool.write_text("#!/bin/sh\nexit 0\n"); tool.chmod(tool.stat().st_mode|stat.S_IXUSR)
        model=root/"model"; model.write_bytes(b"model")
        return {"INTEGRA_FFMPEG":str(tool),"INTEGRA_WHISPER_CLI":str(tool),"INTEGRA_WHISPER_MODEL":str(model)}

    def test_source_detection_distinguishes_media_documents_and_youtube(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); audio=root/"talk.mp3"; audio.write_bytes(b"audio")
            text=root/"notes.md"; text.write_text("# Notes\nreal text")
            self.assertEqual(detect_source(str(audio))["source_type"],"LOCAL_AUDIO")
            document=detect_source(str(text)); self.assertEqual(document["source_type"],"MARKDOWN")
            self.assertEqual(document["properties"]["ocr_status"],"NOT_REQUIRED")
            self.assertEqual(detect_source("https://youtu.be/abc")["source_type"],"YOUTUBE_VIDEO")
            self.assertEqual(detect_source("https://youtube.com/playlist?list=PL1")["source_type"],"YOUTUBE_PLAYLIST")

    def test_registry_never_marks_component_only_features_working(self):
        source={"source_id":"s","display_name":"v.mp4","input":"/v.mp4","source_type":"LOCAL_VIDEO","kind":"MEDIA","properties":{}}
        with tempfile.TemporaryDirectory() as directory:
            overrides=self.media_runtime(Path(directory)); old={key:os.environ.get(key) for key in overrides}
            try:
                os.environ.update(overrides); registry={item["id"]:item for item in capability_registry([source])}
            finally:
                for key,value in old.items():
                    if value is None: os.environ.pop(key,None)
                    else: os.environ[key]=value
        self.assertTrue(registry["transcript"]["runtime_available"])
        self.assertTrue(registry["subtitles"]["runtime_available"])
        self.assertEqual(registry["topics"]["implementation_state"], "IMPLEMENTED")
        self.assertFalse(registry["topics"]["runtime_available"])
        self.assertEqual(registry["topics"]["ui_state"], "Недоступно: SeminarText runtime is not configured")
        self.assertEqual(registry["translation"]["implementation_state"], "IMPLEMENTED")
        self.assertFalse(registry["translation"]["runtime_available"])
        self.assertTrue(registry["translation"]["ui_state"].startswith("Недоступно:"))
        for identifier in ("review","evidence","knowledge","clips"):
            self.assertEqual(registry[identifier]["ui_state"],"В разработке")
            self.assertFalse(registry[identifier]["runtime_available"])

    def test_planner_resolves_hidden_prerequisites_and_rejects_unimplemented(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source_path=root/"talk.wav"; source_path.write_bytes(b"audio")
            overrides=self.media_runtime(root); old={key:os.environ.get(key) for key in overrides}
            try:
                os.environ.update(overrides); source=detect_source(str(source_path)); plan=build_plan([source],["subtitles"])
                self.assertEqual([item["id"] for item in plan["stages"]],["media_preparation","transcript","subtitles"])
                with self.assertRaisesRegex(ValueError,"not executable"): build_plan([source],["topics"])
            finally:
                for key,value in old.items():
                    if value is None: os.environ.pop(key,None)
                    else: os.environ[key]=value

    def test_youtube_video_uses_a_real_ingest_stage_but_playlist_remains_deferred(self):
        video=detect_source("https://www.youtube.com/watch?v=real-video")
        playlist=detect_source("https://www.youtube.com/playlist?list=PL1")
        with tempfile.TemporaryDirectory() as directory:
            overrides=self.media_runtime(Path(directory)); old={key:os.environ.get(key) for key in overrides}
            try:
                os.environ.update(overrides)
                with patch("integra_core.capabilities.youtube_preflight",return_value={"state":"READY"}):
                    registry={item["id"]:item for item in capability_registry([video])}
                    plan=build_plan([video],["subtitles"])
                    deferred={item["id"]:item for item in capability_registry([playlist])}
            finally:
                for key,value in old.items():
                    if value is None: os.environ.pop(key,None)
                    else: os.environ[key]=value
        self.assertTrue(registry["youtube_ingest"]["runtime_available"])
        self.assertEqual(registry["youtube_ingest"]["implementation_state"],"IMPLEMENTED")
        self.assertEqual([item["id"] for item in plan["stages"]],["youtube_ingest","media_preparation","transcript","subtitles"])
        self.assertEqual(deferred["youtube_playlist_ingest"]["ui_state"],"В разработке")

    def test_scanned_document_requires_verified_booktext_runtime(self):
        source={"source_id":"s","display_name":"scan.pdf","input":"/scan.pdf","source_type":"PDF","kind":"DOCUMENT",
                "properties":{"ocr_status":"REQUIRED","content_mode":"IMAGE_HEAVY"}}
        registry={item["id"]:item for item in capability_registry([source])}
        self.assertFalse(registry["document_text"]["runtime_available"])
        self.assertEqual(registry["ocr"]["component"],"booktext")
        self.assertEqual(registry["ocr"]["implementation_state"],"IMPLEMENTED")
        self.assertTrue(registry["ocr"]["ui_state"].startswith("Недоступно:"))

    def test_scanned_document_exposes_real_ocr_only_after_booktext_preflight(self):
        source={"source_id":"s","display_name":"scan.png","input":"/scan.png","source_type":"IMAGE","kind":"DOCUMENT",
                "properties":{"ocr_status":"REQUIRED","content_mode":"SCAN"}}
        with patch("integra_core.capabilities.booktext_preflight", return_value={"state":"READY"}):
            registry={item["id"]:item for item in capability_registry([source])}
            plan=build_plan([source],["document_text"])
        self.assertTrue(registry["ocr"]["runtime_available"])
        self.assertTrue(registry["document_text"]["runtime_available"])
        self.assertEqual([stage["id"] for stage in plan["stages"]],["document_analysis","ocr","document_text"])

    def test_registry_exposes_verified_embedded_image_materialization(self):
        source={"source_id":"s","display_name":"slides.pptx","input":"/slides.pptx","source_type":"PPTX","kind":"DOCUMENT",
                "properties":{"ocr_status":"NOT_REQUIRED","content_mode":"MIXED"}}
        registry={item["id"]:item for item in capability_registry([source])}
        self.assertTrue(registry["extract_images"]["runtime_available"])
        self.assertEqual(registry["extract_images"]["implementation_state"],"IMPLEMENTED")
        plan=build_plan([source],["extract_images"])
        self.assertEqual([stage["id"] for stage in plan["stages"]],["document_analysis","discover_images","extract_images"])

    def test_video_subtitle_burning_uses_the_real_local_runtime(self):
        source={"source_id":"s","display_name":"video.mp4","input":"/video.mp4","source_type":"LOCAL_VIDEO","kind":"MEDIA","properties":{}}
        with tempfile.TemporaryDirectory() as directory:
            overrides=self.media_runtime(Path(directory)); old={key:os.environ.get(key) for key in overrides}
            try:
                os.environ.update(overrides); registry={item["id"]:item for item in capability_registry([source])}
            finally:
                for key,value in old.items():
                    if value is None: os.environ.pop(key,None)
                    else: os.environ[key]=value
        self.assertTrue(registry["burn_subtitles"]["runtime_available"])
        self.assertEqual(registry["burn_subtitles"]["component"],"integra.local_media_adapter")

    def test_audio_enhancement_requires_only_the_owned_ffmpeg_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source_path=root/"talk.wav"; source_path.write_bytes(b"audio")
            ffmpeg=root/"ffmpeg"; ffmpeg.write_text("#!/bin/sh\nexit 0\n"); ffmpeg.chmod(ffmpeg.stat().st_mode|stat.S_IXUSR)
            old={key:os.environ.get(key) for key in ("INTEGRA_FFMPEG","INTEGRA_WHISPER_CLI","INTEGRA_WHISPER_MODEL")}
            try:
                os.environ["INTEGRA_FFMPEG"]=str(ffmpeg)
                os.environ.pop("INTEGRA_WHISPER_CLI",None); os.environ.pop("INTEGRA_WHISPER_MODEL",None)
                registry={item["id"]:item for item in capability_registry([detect_source(str(source_path))])}
                plan=build_plan([detect_source(str(source_path))],["enhance_audio"])
            finally:
                for key,value in old.items():
                    if value is None: os.environ.pop(key,None)
                    else: os.environ[key]=value
        self.assertTrue(registry["enhance_audio"]["runtime_available"])
        self.assertEqual(registry["enhance_audio"]["component"],"integra.local_media_adapter")
        self.assertEqual([stage["id"] for stage in plan["stages"]],["media_preparation","enhance_audio"])


if __name__=="__main__": unittest.main()
