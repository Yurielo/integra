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


if __name__=="__main__": unittest.main()
