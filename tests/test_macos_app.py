import json
import hashlib
from pathlib import Path
import subprocess
import platform
import struct
import tempfile
import unittest

from tests.test_publishing import fixtures
from integra_core.onedrive import build_onedrive_package


ROOT = Path(__file__).resolve().parents[1]


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

    @unittest.skipUnless(platform.system() == "Darwin", "native macOS build requires Darwin")
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

    def test_native_source_exposes_source_first_real_actions(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        for operation in ("detect-sources", "capability-registry", "build-plan", "execute-plan", "run-status", "media-navigation", "seminartext-preflight", "package-preview", "package-publish"):
            self.assertIn(operation, source)
        self.assertIn("NSOpenPanel", source)
        self.assertIn("Одиночное видео будет загружено в проект", source)
        self.assertIn("Плейлисты пока помечены «В разработке»", source)
        self.assertIn("ЧТО НУЖНО ПОЛУЧИТЬ?", source)
        self.assertIn("Выполнить", source)
        self.assertIn("Перетащите файлы сюда", source)
        self.assertIn('bridge.json("recent-runs")', source)
        self.assertIn('bridge.json("open-project"', source)
        self.assertIn("renderProject(project)", source)
        self.assertIn("renderSources()", source)
        self.assertIn("applicationShouldTerminateAfterLastWindowClosed", source)
        self.assertIn('bridge.json("cancel-run"', source)
        self.assertIn("СЛЕДУЮЩИЕ ДЕЙСТВИЯ", source)
        self.assertIn("AVPlayerView", source)
        self.assertIn("seekTranscriptCue", source)
        self.assertIn('object["error"] as? String', source)
        self.assertNotIn("Integra Reference Project", source)

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
