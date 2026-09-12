import json
import os
import zipfile
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import unittest
from integra_core.publishing import validate_package
from integra_core.onedrive import validate_onedrive_package

ROOT=Path(__file__).resolve().parents[1]


class SourceFirstBridgeTests(unittest.TestCase):
    def test_detect_plan_execute_and_status_use_real_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/"notes.md"; source.write_text("# Real source\nBody")
            environment={**os.environ,"INTEGRA_APP_DATA_ROOT":str(root/"data")}; bridge=ROOT/"macos/Resources/bridge.py"
            def call(operation,request):
                result=subprocess.run(["python3",str(bridge),operation],input=json.dumps(request),capture_output=True,text=True,env=environment)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr); return json.loads(result.stdout)["result"]
            sources=call("detect-sources",{"inputs":[str(source)]})
            registry=call("capability-registry",{"sources":sources})
            self.assertTrue(next(item for item in registry if item["id"]=="document_text")["runtime_available"])
            plan=call("build-plan",{"sources":sources,"selected_outputs":["document_text","document_structure"]})
            execution=call("execute-plan",{"plan":plan,"name":"Source-first test"}); project=execution["project"]; run=execution["run"]
            for _ in range(100):
                status=call("run-status",{"project_id":project["project_id"],"run_id":run["run_id"]})
                if status["state"] in {"COMPLETED","FAILED"}: break
                time.sleep(.03)
            self.assertEqual(status["state"],"COMPLETED",status)
            text=Path(status["source_results"][0]["outputs"]["text"]); self.assertTrue(text.is_file()); self.assertIn("Body",text.read_text())
            self.assertTrue(Path(status["source_results"][0]["outputs"]["document_structure"]).is_file())

    def test_bridge_document_discover_images_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/"empty.docx"
            with zipfile.ZipFile(source,"w") as container:
                container.writestr("word/document.xml",
                                   b'<?xml version="1.0" encoding="UTF-8"?>'
                                   b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                                   b'<w:body><w:p><w:r><w:t>Docx test</w:t></w:r></w:p></w:body>'
                                   b'</w:document>')
            environment={**os.environ,"INTEGRA_APP_DATA_ROOT":str(root/"data")}
            bridge=ROOT/"macos/Resources/bridge.py"
            def call(operation,request):
                result=subprocess.run(["python3",str(bridge),operation],input=json.dumps(request),capture_output=True,text=True,env=environment)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr); return json.loads(result.stdout)["result"]
            sources=call("detect-sources",{"inputs":[str(source)]})
            plan=call("build-plan",{"sources":sources,"selected_outputs":["discover_images"]})
            execution=call("execute-plan",{"plan":plan,"name":"Docx discovery test"})
            project=execution["project"]; run=execution["run"]
            for _ in range(100):
                status=call("run-status",{"project_id":project["project_id"],"run_id":run["run_id"]})
                if status["state"] in {"COMPLETED","FAILED"}: break
                time.sleep(.03)
            self.assertEqual(status["state"],"COMPLETED",status)
            self.assertTrue(Path(status["source_results"][0]["outputs"]["discover_images"]).is_file())

    def test_bridge_materializes_verified_embedded_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/"illustrated.docx"
            png=bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
                              "0000000a49444154789c636000000002000148afa4710000000049454e44ae426082")
            with zipfile.ZipFile(source,"w") as container:
                container.writestr("word/document.xml",
                                   b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                                   b'<w:body><w:p><w:r><w:t>Image test</w:t></w:r></w:p></w:body></w:document>')
                container.writestr("word/media/image1.png",png)
            environment={**os.environ,"INTEGRA_APP_DATA_ROOT":str(root/"data")}; bridge=ROOT/"macos/Resources/bridge.py"
            def call(operation,request):
                result=subprocess.run(["python3",str(bridge),operation],input=json.dumps(request),capture_output=True,text=True,env=environment)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr); return json.loads(result.stdout)["result"]
            sources=call("detect-sources",{"inputs":[str(source)]})
            registry={item["id"]:item for item in call("capability-registry",{"sources":sources})}
            self.assertTrue(registry["extract_images"]["runtime_available"])
            plan=call("build-plan",{"sources":sources,"selected_outputs":["extract_images"]})
            execution=call("execute-plan",{"plan":plan,"name":"Docx image extraction test"})
            project=execution["project"]; run=execution["run"]
            for _ in range(100):
                status=call("run-status",{"project_id":project["project_id"],"run_id":run["run_id"]})
                if status["state"] in {"COMPLETED","FAILED"}: break
                time.sleep(.03)
            self.assertEqual(status["state"],"COMPLETED",status)
            outputs=status["source_results"][0]["outputs"]
            manifest=json.loads(Path(outputs["embedded_images_manifest"]).read_bytes())
            image=Path(outputs["embedded_images_directory"])/manifest["embedded_media"][0]["relative_path"]
            self.assertEqual(image.read_bytes(),png)

    def test_source_first_media_builds_publication_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/"voice.wav"; source.write_bytes(b"audio")
            ffmpeg=root/"ffmpeg"; ffmpeg.write_text("#!/usr/bin/env python3\n"
                              "import sys, shutil\n"
                              "args = sys.argv[1:]\n"
                              "index = args.index('-i') + 1\n"
                              "input_path = args[index]\n"
                              "output_path = args[-1]\n"
                              "shutil.copyfile(input_path, output_path)\n")
            ffmpeg.chmod(ffmpeg.stat().st_mode | 0o111)
            whisper=root/"whisper-cli"; whisper.write_text("#!/usr/bin/env python3\n"
                              "import sys\n"
                              "args = sys.argv[1:]\n"
                              "index = args.index('-of') + 1\n"
                              "output_path = args[index]\n"
                              "with open(f'{output_path}.srt','w',encoding='utf-8') as stream:\n"
                              "    stream.write('1\\n00:00:00,000 --> 00:00:01,250\\nHello Integra\\n')\n")
            whisper.chmod(whisper.stat().st_mode | 0o111)
            model=root/"model.bin"; model.write_bytes(b"model")
            environment={**os.environ,"INTEGRA_APP_DATA_ROOT":str(root/"data"),
                         "INTEGRA_FFMPEG":str(ffmpeg),"INTEGRA_WHISPER_CLI":str(whisper),
                         "INTEGRA_WHISPER_MODEL":str(model)}
            bridge=ROOT/"macos/Resources/bridge.py"
            def call(operation,request):
                result=subprocess.run(["python3",str(bridge),operation],input=json.dumps(request),capture_output=True,text=True,env=environment,timeout=5)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr); return json.loads(result.stdout)["result"]
            sources=call("detect-sources",{"inputs":[str(source)]})
            plan=call("build-plan",{"sources":sources,"selected_outputs":["transcript","subtitles"]})
            execution=call("execute-plan",{"plan":plan,"name":"Source-first media package test"})
            project_id=execution["project"]["project_id"]; run_id=execution["run"]["run_id"]
            for _ in range(200):
                status=call("run-status",{"project_id":project_id,"run_id":run_id})
                if status["state"] in {"COMPLETED","FAILED"}: break
                time.sleep(.03)
            self.assertEqual(status["state"],"COMPLETED",status)
            outputs=status["source_results"][0]["outputs"]
            package=Path(outputs["package_dir"])
            self.assertTrue((package / "package.json").is_file())
            manifest=json.loads((package/"package.json").read_text(encoding="utf-8"))
            files={}
            for item in manifest["files"]:
                payload=(package/"files"/item["path"]).read_bytes()
                files[item["path"]]=payload
            validate_package(manifest,files)
            onedrive_root=Path(json.loads((package/"onedrive_package.json").read_text(encoding="utf-8"))["package_dir"])
            self.assertTrue((onedrive_root/"package.json").is_file())
            one_manifest=json.loads((onedrive_root/"package.json").read_text(encoding="utf-8"))
            one_files={}
            for item in one_manifest["files"]:
                one_files[item["path"]]=(onedrive_root/"files"/item["path"]).read_bytes()
            validate_onedrive_package(one_manifest,one_files)

    def test_cancel_run_stops_real_worker_group_and_persists_cancelled_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/"recording.wav"; source.write_bytes(b"real-input")
            ffmpeg=root/"ffmpeg"; ffmpeg.write_text("#!/bin/sh\nsleep 30\n"); ffmpeg.chmod(0o755)
            whisper=root/"whisper-cli"; whisper.write_text("#!/bin/sh\nexit 1\n"); whisper.chmod(0o755)
            model=root/"model.bin"; model.write_bytes(b"model")
            environment={**os.environ,"INTEGRA_APP_DATA_ROOT":str(root/"data"),
                         "INTEGRA_FFMPEG":str(ffmpeg),"INTEGRA_WHISPER_CLI":str(whisper),
                         "INTEGRA_WHISPER_MODEL":str(model)}
            bridge=ROOT/"macos/Resources/bridge.py"
            def call(operation,request):
                result=subprocess.run(["python3",str(bridge),operation],input=json.dumps(request),
                                      capture_output=True,text=True,env=environment,timeout=5)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                return json.loads(result.stdout)["result"]
            sources=call("detect-sources",{"inputs":[str(source)]})
            plan=call("build-plan",{"sources":sources,"selected_outputs":["transcript"]})
            execution=call("execute-plan",{"plan":plan,"name":"Cancellation test"})
            project_id=execution["project"]["project_id"]; run_id=execution["run"]["run_id"]
            try:
                for _ in range(100):
                    jobs=call("jobs",{"project_id":project_id})
                    if jobs and jobs[-1]["state"] == "RUNNING": break
                    time.sleep(.03)
                self.assertTrue(jobs and jobs[-1]["state"] == "RUNNING",jobs)
                cancelled=call("cancel-run",{"project_id":project_id,"run_id":run_id})
                self.assertEqual(cancelled["state"],"CANCELLED")
                self.assertIsNone(cancelled["current_stage"])
                self.assertEqual(call("jobs",{"project_id":project_id})[-1]["state"],"CANCELLED")
                for _ in range(100):
                    status = call("run-status",{"project_id":project_id,"run_id":run_id})
                    if status["state"] not in {"QUEUED","RUNNING"}: break
                    time.sleep(.03)
                self.assertEqual(status["state"],"CANCELLED")
            finally:
                status=call("run-status",{"project_id":project_id,"run_id":run_id})
                if status["state"] in {"QUEUED","RUNNING"}:
                    call("cancel-run",{"project_id":project_id,"run_id":run_id})


if __name__=="__main__": unittest.main()
