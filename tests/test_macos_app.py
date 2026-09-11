import json
from pathlib import Path
import subprocess
import platform
import tempfile
import unittest

from tests.test_publishing import fixtures
from integra_core.onedrive import build_onedrive_package


ROOT = Path(__file__).resolve().parents[1]


class MacOSApplicationTests(unittest.TestCase):
    def test_reference_workflow_exposes_required_surfaces(self):
        workflow = json.loads((ROOT / "macos/Resources/reference_workflow.json").read_text())
        self.assertEqual([item["id"] for item in workflow["sections"]], [
            "projects", "transcript", "knowledge", "media", "navigation",
            "operations", "obsidian", "onedrive", "deferred",
        ])
        self.assertEqual(workflow["sections"][-1]["status"], "LATER_UNAVAILABLE")
        self.assertIn("#t=", workflow["navigation"]["source_locator"])

    def test_deferred_registry_has_no_actions(self):
        registry = json.loads((ROOT / "macos/Resources/deferred_features.json").read_text())
        self.assertFalse(registry["actions_available"])
        self.assertEqual(registry["status"], "DEFERRED_TO_LATER_WORK")
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        self.assertIn('section.id == "deferred"', source)
        self.assertIn("actionButton.isEnabled = false", source)

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
                                    capture_output=True, text=True, timeout=60)
            self.assertIn("INTEGRA_MACOS_SELF_TEST: PASS", result.stdout)
            self.assertIn("INTEGRA_MACOS_LAUNCH_TEST: PASS", result.stdout)

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

    def test_native_source_exposes_real_project_job_and_package_actions(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        for operation in ("create-project", "open-project", "start-job", "package-preview", "package-publish"):
            self.assertIn(operation, source)
        self.assertIn("NSOpenPanel", source)
        self.assertIn("Publish this verified package?", source)
        self.assertIn('object["error"] as? String', source)
        self.assertIn('Integra — New local project', source)

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
