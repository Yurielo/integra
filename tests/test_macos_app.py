import json
import os
import pty
import hashlib
import os
from pathlib import Path
import subprocess
import platform
import stat
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

from tests.test_publishing import fixtures
from integra_core.capabilities import build_plan
from integra_core.onedrive import build_onedrive_package


ROOT = Path(__file__).resolve().parents[1]


def macos_build_runtime_available():
    seminartext = Path(os.environ.get(
        "INTEGRA_SEMINARTEXT_BUILD_CHECKOUT",
        ROOT / ".runtime-components/seminartext-pinned",
    ))
    videotext = Path(os.environ.get(
        "INTEGRA_VIDEOTEXT_BUILD_CHECKOUT",
        ROOT / ".runtime-components/videotext-pinned",
    ))
    booktext = Path(os.environ.get(
        "INTEGRA_BOOKTEXT_BUILD_CHECKOUT",
        ROOT / ".runtime-components/booktext-pinned",
    ))
    packages = Path(os.environ.get(
        "INTEGRA_WORD_ALIGNMENT_SITE_PACKAGES",
        ROOT / ".runtime-word-alignment/lib/python3.13/site-packages",
    ))
    model = Path(os.environ.get(
        "INTEGRA_WORD_ALIGNMENT_MODEL_DIR",
        "/Users/yurielokhin/.cache/huggingface/hub/"
        "models--jonatasgrosman--wav2vec2-large-xlsr-53-russian/"
        "snapshots/2329100508896c6d9b157019803ab5601e6f3406",
    ))
    python = Path(os.environ.get(
        "INTEGRA_WORD_ALIGNMENT_PYTHON",
        "/opt/homebrew/opt/python@3.13/bin/python3.13",
    ))
    return all((
        (seminartext / ".git").exists(),
        (videotext / ".git").exists(),
        (booktext / ".git").exists(),
        (packages / "whisperx").is_dir(),
        (model / "pytorch_model.bin").is_file(),
        os.access(python, os.X_OK),
    ))


class MacOSApplicationTests(unittest.TestCase):
    def test_approved_app_icon_assets_are_exact(self):
        catalog = ROOT / "macos/Assets.xcassets/AppIcon.appiconset"
        canonical = catalog / "Integra_app_icon.png"
        self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(),
                         "9de0c4871eb80ce057f2d977c00b5b1f8f8f6f2ebdb4003912f8b3e39f654dce")
        contents = json.loads((catalog / "Contents.json").read_text())
        expected = {
            "icon_16x16.png": (16, 16), "icon_16x16@2x.png": (32, 32),
            "icon_32x32.png": (32, 32), "icon_32x32@2x.png": (64, 64),
            "icon_128x128.png": (128, 128), "icon_128x128@2x.png": (256, 256),
            "icon_256x256.png": (256, 256), "icon_256x256@2x.png": (512, 512),
            "icon_512x512.png": (512, 512), "icon_512x512@2x.png": (1024, 1024),
        }
        self.assertEqual({item["filename"] for item in contents["images"]}, set(expected))
        for filename, dimensions in expected.items():
            data = (catalog / filename).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", data[16:24]), dimensions)
    @unittest.skipUnless(platform.system() == "Darwin", "icon generation requires macOS sips and iconutil")
    def test_app_icon_regeneration_is_byte_reproducible(self):
        catalog = ROOT / "macos/Assets.xcassets/AppIcon.appiconset"
        filenames = {item["filename"] for item in json.loads((catalog / "Contents.json").read_text())["images"]}
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory) / "macos"
            subprocess.run([str(ROOT / "scripts/generate_macos_app_icon.sh"), str(generated)], check=True)
            self.assertEqual((generated / "Resources/Integra.icns").read_bytes(),
                             (ROOT / "macos/Resources/Integra.icns").read_bytes())
            for filename in filenames:
                self.assertEqual((generated / "Assets.xcassets/AppIcon.appiconset" / filename).read_bytes(),
                                 (catalog / filename).read_bytes())

    def test_source_first_workflow_contains_no_production_fixture_data(self):
        workflow = json.loads((ROOT / "macos/Resources/source_first_workflow.json").read_text())
        self.assertEqual(workflow["workflow"], "SOURCE_FIRST")
        self.assertEqual(workflow["default_screen"], "Новая обработка")
        self.assertEqual(workflow["unimplemented_label"], "В разработке")
        self.assertFalse(workflow["component_selection_visible_to_user"])
        self.assertFalse(workflow["production_fixture_data"])

    def test_deferred_registry_has_no_actions(self):
        registry = json.loads((ROOT / "macos/Resources/deferred_features.json").read_text())
        self.assertFalse(registry["actions_available"])
        self.assertEqual(registry["status"], "DEFERRED_TO_LATER_WORK")
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        self.assertIn("— В разработке", source)
        self.assertIn("enabled:false", source.replace(" ", ""))

    def test_topic_detail_control_is_bounded_and_sent_with_the_execution_request(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text(encoding="utf-8")
        self.assertIn('NSSegmentedControl(labels: ["Крупно", "Обычно", "Подробно"]', source)
        self.assertIn('topicDetail = ["low", "auto", "high"]', source)
        self.assertIn('"topic_detail": topicDetail', source)
        self.assertIn('result["topic_detail"]', source)

    def test_closed_bridge_rejects_unknown_and_previews_without_writes(self):
        bridge = ROOT / "macos/Resources/bridge.py"
        unknown = subprocess.run(["python3", str(bridge), "publish"], capture_output=True, text=True)
        self.assertNotEqual(unknown.returncode, 0)
        for operation in ("obsidian-preview", "onedrive-preview"):
            result = subprocess.run(["python3", str(bridge), operation], check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["writes_performed"]); self.assertFalse(payload["external_actions_performed"])
            self.assertFalse(payload["cloud_verified"])
            self.assertEqual(len(payload["domain_contract_sha256"]), 64)

    def test_closed_bridge_empty_tty_request_does_not_wait_for_terminal_eof(self):
        bridge = ROOT / "macos/Resources/bridge.py"
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(["python3", str(bridge), "obsidian-preview"],
                                       stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True)
        finally:
            os.close(slave)
        try:
            stdout, stderr = process.communicate(timeout=5)
        finally:
            os.close(master)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(json.loads(stdout)["state"], "DRY_RUN_REQUIRES_PACKAGE")

    @unittest.skipUnless(
        platform.system() == "Darwin" and macos_build_runtime_available(),
        "native macOS rebuild requires the pinned external runtime sources",
    )
    def test_reproducible_build_and_launch_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([str(ROOT / "scripts/test_macos_app.sh")], check=True,
                                    capture_output=True, text=True, timeout=180)
            self.assertIn("INTEGRA_MACOS_SELF_TEST: PASS", result.stdout)
            self.assertIn("INTEGRA_MACOS_LAUNCH_TEST: PASS", result.stdout)
            self.assertIn("INTEGRA_MACOS_CLOSE_TEST: PASS", result.stdout)
            self.assertIn("INTEGRA_FINDER_ICON: PASS", result.stdout)
            self.assertIn("INTEGRA_DOCK_CMDTAB_ICON: PASS", result.stdout)
            self.assertIn("INTEGRA_BUNDLED_SEMINARTEXT_PREFLIGHT: PASS", result.stdout)
            self.assertIn("INTEGRA_BUNDLED_WORD_TIMELINE_PREFLIGHT: PASS", result.stdout)
            self.assertIn("INTEGRA_BUNDLED_BOOKTEXT_PREFLIGHT: PASS", result.stdout)

    def test_bridge_creates_opens_and_persists_project_and_job(self):
        bridge = ROOT / "macos/Resources/bridge.py"
        with tempfile.TemporaryDirectory() as directory:
            environment = {**__import__("os").environ, "INTEGRA_APP_DATA_ROOT": directory}
            created = subprocess.run(
                ["python3", str(bridge), "create-project"], input='{"name":"Test Project"}',
                check=True, capture_output=True, text=True, env=environment,
            )
            project = json.loads(created.stdout)["result"]
            listed = subprocess.run(["python3", str(bridge), "projects"], input="{}",
                                    check=True, capture_output=True, text=True, env=environment)
            self.assertEqual(json.loads(listed.stdout)["result"], [project])
            opened = subprocess.run(
                ["python3", str(bridge), "open-project"],
                input=json.dumps({"project_id": project["project_id"]}), check=True,
                capture_output=True, text=True, env=environment,
            )
            self.assertEqual(json.loads(opened.stdout)["result"], project)
            job = subprocess.run(
                ["python3", str(bridge), "start-job"],
                input=json.dumps({"project_id": project["project_id"]}), check=True,
                capture_output=True, text=True, env=environment,
            )
            self.assertEqual(json.loads(job.stdout)["result"]["state"], "COMPLETED")
            jobs = subprocess.run(
                ["python3", str(bridge), "jobs"],
                input=json.dumps({"project_id": project["project_id"]}), check=True,
                capture_output=True, text=True, env=environment,
            )
            self.assertEqual(len(json.loads(jobs.stdout)["result"]), 1)

    def test_bridge_discovers_a_folder_before_the_existing_plan_is_built(self):
        bridge = ROOT / "macos/Resources/bridge.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "materials"; folder.mkdir()
            (folder / "b.wav").write_bytes(b"b")
            (folder / "A.mp3").write_bytes(b"a")
            (folder / "ignored.zip").write_bytes(b"zip")
            (folder / ".hidden.wav").write_bytes(b"hidden")
            environment = {**__import__("os").environ, "INTEGRA_APP_DATA_ROOT": str(root / "app-data")}
            discovered = subprocess.run(
                ["python3", str(bridge), "discover-folder-sources"],
                input=json.dumps({"folder": str(folder)}), check=True,
                capture_output=True, text=True, env=environment,
            )
            result = json.loads(discovered.stdout)["result"]
            self.assertEqual([item["display_name"] for item in result["sources"]], ["A.mp3", "b.wav"])
            self.assertEqual({item["reason"] for item in result["ignored"]}, {"HIDDEN", "UNSUPPORTED"})
            with patch("integra_core.capabilities.preflight", return_value={"state": "READY"}):
                plan = build_plan(result["sources"], ["transcript"])
            self.assertEqual(plan["sources"], result["sources"])
            self.assertEqual([item["source_id"] for item in plan["source_plans"]], [
                item["source_id"] for item in result["sources"]
            ])

    def test_bridge_discovers_zoom_recordings_before_the_existing_plan_is_built(self):
        bridge = ROOT / "macos/Resources/bridge.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "Zoom Meeting"; folder.mkdir()
            (folder / "zoom_0.mp4").write_bytes(b"video")
            (folder / "audio_only.m4a").write_bytes(b"audio")
            (folder / "recording.conf").write_text("config", encoding="utf-8")
            second = folder / "part-02"; second.mkdir(); (second / "zoom_1.mp4").write_bytes(b"part")
            environment = {**__import__("os").environ, "INTEGRA_APP_DATA_ROOT": str(root / "app-data")}
            discovered = subprocess.run(
                ["python3", str(bridge), "discover-zoom-folder-sources"],
                input=json.dumps({"folder": str(folder)}), check=True,
                capture_output=True, text=True, env=environment,
            )
            result = json.loads(discovered.stdout)["result"]
            self.assertEqual([item["display_name"] for item in result["sources"]], ["audio_only.m4a", "zoom_1.mp4"])
            self.assertEqual(result["sources"][0]["zoom_discovery"]["recognition"], "ZOOM_RECORDING_FOLDER_S07")
            with patch("integra_core.capabilities.preflight", return_value={"state": "READY"}):
                plan = build_plan(result["sources"], ["transcript"])
            self.assertEqual(plan["sources"], result["sources"])

    def test_bridge_resolves_youtube_playlist_before_the_existing_plan_is_built(self):
        bridge = ROOT / "macos/Resources/bridge.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloader = root / "yt-dlp"
            downloader.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"--version\" ]; then echo 2026.01.01; exit 0; fi\n"
                "for arg in \"$@\"; do [ \"$arg\" = \"--flat-playlist\" ] && { echo '{\"id\":\"PL-bridge\",\"title\":\"Bridge playlist\",\"entries\":[{\"id\":\"bridge-video\",\"title\":\"Bridge video\",\"duration\":1,\"filesize\":4},{\"id\":\"private-video\",\"title\":\"[Private video]\",\"availability\":\"private\"}]}'; exit 0; }; done\n"
                "previous=''\n"
                "for arg in \"$@\"; do [ \"$previous\" = \"--output\" ] && output=$arg; previous=$arg; done\n"
                "target=$(printf '%s' \"$output\" | sed 's/%(ext)s/mp3/')\n"
                "printf 'real-bridge-media' > \"$target\"\n"
            )
            downloader.chmod(downloader.stat().st_mode | stat.S_IXUSR)
            environment = {**os.environ, "INTEGRA_APP_DATA_ROOT": str(root / "app-data"), "INTEGRA_YTDLP": str(downloader)}

            def invoke(operation, request):
                completed = subprocess.run(
                    ["python3", str(bridge), operation], input=json.dumps(request), check=True,
                    capture_output=True, text=True, env=environment,
                )
                return json.loads(completed.stdout)["result"]

            playlist = invoke("detect-sources", {"inputs": ["https://www.youtube.com/playlist?list=PL-bridge"]})[0]
            resolution = invoke("discover-youtube-playlist", {"source": playlist})
            self.assertEqual(resolution["playlist"]["playlist_title"], "Bridge playlist")
            self.assertEqual([item["display_name"] for item in resolution["sources"]], ["Bridge video"])
            self.assertEqual(resolution["unavailable"][0]["video_id"], "private-video")
            plan = invoke("build-plan", {"sources": resolution["sources"], "selected_outputs": ["youtube_ingest"]})
            execution = invoke("execute-plan", {"plan": plan, "name": "Bridge playlist"})
            project_id = execution["project"]["project_id"]
            run_id = execution["run"]["run_id"]
            result = None
            for _ in range(100):
                result = invoke("run-status", {"project_id": project_id, "run_id": run_id})
                if result["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                    break
                time.sleep(0.05)
            self.assertEqual(result["state"], "COMPLETED")
            outputs = result["source_results"][0]["outputs"]
            record = json.loads(Path(outputs["youtube_source_record"]).read_bytes())
            self.assertEqual(record["playlist_membership"]["video_id"], "bridge-video")
            self.assertEqual(record["playlist_context"]["playlist_native_id"], "PL-bridge")

    def test_native_source_exposes_source_first_real_actions(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        bridge_allow_list = source[source.index("let allowed = ["):source.index("guard allowed.contains(operation)")]
        for operation in ("detect-sources", "discover-folder-sources", "discover-zoom-folder-sources", "discover-youtube-playlist", "capability-registry", "build-plan", "execute-plan", "run-status", "media-navigation", "seminartext-preflight", "package-preview", "package-publish"):
            self.assertIn(operation, source)
            self.assertIn(operation, bridge_allow_list)
        self.assertIn("NSOpenPanel", source)
        self.assertIn("Папка с Mac", source)
        self.assertIn("Папка Zoom", source)
        self.assertIn("Подтвердите записи Zoom", source)
        self.assertIn("Подтвердите источники", source)
        self.assertIn("Добавить \\(discovered.count) источников", source)
        self.assertIn("Подтвердите видео плейлиста", source)
        self.assertIn("Добавить выбранные источники", source)
        self.assertIn("ЧТО НУЖНО ПОЛУЧИТЬ?", source)
        self.assertIn("Режим распознавания", source)
        self.assertIn("Язык исходной речи", source)
        self.assertIn("Русский", source)
        self.assertIn("Обычный", source)
        self.assertIn("Тщательный", source)
        self.assertIn('"recognition_mode": recognitionMode', source)
        self.assertIn('"source_speech_language": sourceSpeechLanguage', source)
        self.assertNotIn("SeminarText: фрагмент", source)
        self.assertIn("Выполнить", source)
        self.assertIn("Перетащите файлы сюда", source)
        self.assertIn('bridge.json("recent-runs")', source)
        self.assertIn('bridge.json("open-project"', source)
        self.assertIn("renderProject(project)", source)
        self.assertIn("renderSources()", source)
        self.assertIn("applicationShouldTerminateAfterLastWindowClosed", source)
        self.assertIn('service.json("cancel-run"', source)
        self.assertNotIn("СЛЕДУЮЩИЕ ДЕЙСТВИЯ", source)
        self.assertIn("AVPlayerView", source)
        self.assertIn("seekTranscriptCue", source)
        self.assertIn('object["error"] as? String', source)
        self.assertNotIn("Integra Reference Project", source)

    def test_knowledge_fragment_viewer_uses_retained_window_and_reports_playback_failure(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        start = source.index("private func presentKnowledgeNavigation")
        end = source.index("@objc private func reviewKnowledge", start)
        viewer = source[start:end]
        self.assertIn("renderKnowledgeFragment", viewer)
        self.assertNotIn("NSAlert", viewer)
        self.assertIn("knowledgeMediaWindow", viewer)
        self.assertIn("knowledgePlayerStatusObserver", viewer)
        self.assertIn("AVPlayerItem(asset: asset)", viewer)
        self.assertIn("fileExists(atPath: source.path)", viewer)
        self.assertIn("Исходный файл для точного фрагмента недоступен", viewer)
        self.assertIn("Не удалось открыть исходное видео", viewer)
        self.assertIn("forwardPlaybackEndTime", viewer)

    def test_youtube_source_type_stays_internal_to_normal_source_lists(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        self.assertIn('case "YOUTUBE_VIDEO": return "YouTube"', source)
        self.assertIn('case "YOUTUBE_PLAYLIST": return "Плейлист YouTube"', source)
        self.assertEqual(source.count("sourcePresentationDetail(source)"), 3)
        self.assertNotIn('detail: source["source_type"] as? String ?? "UNKNOWN"', source)
        self.assertNotIn('detail: "\\(source["source_type"] ?? "UNKNOWN")"', source)

    def test_macos_build_packages_seminartext_topics_worker(self):
        build = (ROOT / "scripts/build_macos_app.sh").read_text()
        self.assertIn('workers/seminartext_topics_worker.py', build)
        self.assertIn('Resources/workers', build)
        self.assertIn('runtime/seminartext', build)
        self.assertIn('seminartext_topics.py', build)

    def test_macos_build_packages_pinned_booktext_ocr_runtime(self):
        build = (ROOT / "scripts/build_macos_app.sh").read_text()
        self.assertIn('workers/booktext_ocr_worker.py', build)
        self.assertIn('runtime/booktext', build)
        self.assertIn('booktext.py', build)
        self.assertIn('VisionOCR.swift', build)

    def test_bridge_previews_and_publishes_validated_obsidian_package(self):
        *_, manifest, files = fixtures()
        bridge = ROOT / "macos/Resources/bridge.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); package = root / "package"; payloads = package / "files"
            payloads.mkdir(parents=True)
            (package / "package.json").write_text(json.dumps(manifest))
            for name, payload in files.items():
                destination = payloads / name; destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(payload)
            target = root / "vault"; target.mkdir(); app_data = root / "app-data"
            environment = {**__import__("os").environ, "INTEGRA_APP_DATA_ROOT": str(app_data)}
            request = json.dumps({"package_dir": str(package), "target_dir": str(target)})
            preview = subprocess.run(["python3", str(bridge), "package-preview"], input=request,
                                     check=True, capture_output=True, text=True, env=environment)
            self.assertEqual(json.loads(preview.stdout)["result"]["state"], "DRY_RUN")
            published = subprocess.run(["python3", str(bridge), "package-publish"], input=request,
                                       check=True, capture_output=True, text=True, env=environment)
            receipt = json.loads(published.stdout)["result"]
            self.assertEqual(receipt["state"], "EXPORTED")
            self.assertFalse(receipt["cloud_verified"])
            replay = subprocess.run(["python3", str(bridge), "package-publish"], input=request,
                                    check=True, capture_output=True, text=True, env=environment)
            self.assertEqual(json.loads(replay.stdout)["result"]["state"], "UNCHANGED")

    def test_bridge_publishes_onedrive_package_without_cloud_claim(self):
        *_, obsidian_manifest, source_files = fixtures()
        manifest, files = build_onedrive_package(obsidian_manifest, source_files, created_at="2026-09-11T12:00:00Z")
        bridge = ROOT / "macos/Resources/bridge.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); package = root / "package"; payloads = package / "files"; payloads.mkdir(parents=True)
            (package / "package.json").write_text(json.dumps(manifest))
            for name, payload in files.items():
                destination = payloads / name; destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(payload)
            target = root / "onedrive"; target.mkdir(); workspace = root / "workspace"; workspace.mkdir()
            environment = {**__import__("os").environ, "INTEGRA_APP_DATA_ROOT": str(root / "app-data")}
            request = json.dumps({"package_dir":str(package), "target_dir":str(target), "workspace_dir":str(workspace)})
            result = subprocess.run(["python3", str(bridge), "package-publish"], input=request,
                                    check=True, capture_output=True, text=True, env=environment)
            receipt = json.loads(result.stdout)["result"]
            self.assertEqual(receipt["state"], "LOCALLY_PUBLISHED")
            self.assertFalse(receipt["cloud_verified"])


if __name__ == "__main__":
    unittest.main()
