import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import unittest

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
            plan=call("build-plan",{"sources":sources,"selected_outputs":["document_text"]})
            execution=call("execute-plan",{"plan":plan,"name":"Source-first test"}); project=execution["project"]; run=execution["run"]
            for _ in range(100):
                status=call("run-status",{"project_id":project["project_id"],"run_id":run["run_id"]})
                if status["state"] in {"COMPLETED","FAILED"}: break
                time.sleep(.03)
            self.assertEqual(status["state"],"COMPLETED",status)
            text=Path(status["source_results"][0]["outputs"]["text"]); self.assertTrue(text.is_file()); self.assertIn("Body",text.read_text())

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
                self.assertEqual(call("run-status",{"project_id":project_id,"run_id":run_id})["state"],"CANCELLED")
            finally:
                status=call("run-status",{"project_id":project_id,"run_id":run_id})
                if status["state"] in {"QUEUED","RUNNING"}:
                    call("cancel-run",{"project_id":project_id,"run_id":run_id})


if __name__=="__main__": unittest.main()
