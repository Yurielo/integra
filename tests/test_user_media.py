import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import unittest

from integra_core.user_media import import_source, preflight
from tests.asr_tools import media_environment, require_asr_runtime

ROOT=Path(__file__).resolve().parents[1]


class UserMediaWorkflowTests(unittest.TestCase):
    def test_restricted_path_accepts_explicit_safe_tools(self):
        require_asr_runtime()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); executable=root/"tool"; executable.write_text("#!/bin/sh\nexit 0\n"); executable.chmod(0o700)
            model=root/"model"; model.write_bytes(b"model")
            overrides={"PATH":"/usr/bin:/bin:/usr/sbin:/sbin","INTEGRA_FFMPEG":str(executable),"INTEGRA_WHISPER_CLI":str(executable),"INTEGRA_WHISPER_MODEL":str(model)}
            old={key:os.environ.get(key) for key in overrides}
            try:
                os.environ.update(overrides); self.assertEqual(preflight()["state"],"READY")
            finally:
                for key,value in old.items():
                    if value is None: os.environ.pop(key,None)
                    else: os.environ[key]=value
    def test_copy_on_write_import_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/"voice.mp3"; source.write_bytes(b"original")
            record=import_source(root/"project",source)
            self.assertEqual(source.read_bytes(),b"original")
            self.assertEqual(Path(record["owned_path"]).read_bytes(),b"original")
            self.assertFalse(record["source_modified"])

    def test_bridge_runs_media_job_without_creating_semantic_fakes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); tools=root/"tools"; tools.mkdir()
            overrides=media_environment(tools)
            source=root/"voice.wav"; source.write_bytes(b"audio")
            environment={**os.environ,"INTEGRA_APP_DATA_ROOT":str(root/"data"),**overrides}
            bridge=ROOT/"macos/Resources/bridge.py"
            def call(operation,request):
                result=subprocess.run(["python3",str(bridge),operation],input=json.dumps(request),capture_output=True,text=True,env=environment)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr); return json.loads(result.stdout)["result"]
            project=call("create-project",{"name":"Local Media"})
            job=call("import-media",{"project_id":project["project_id"],"source_path":str(source)})
            for _ in range(100):
                view=call("project-view",{"project_id":project["project_id"]})
                if view["job"]["state"] in {"COMPLETED","FAILED"}: break
                time.sleep(.05)
            self.assertEqual(view["job"]["state"],"COMPLETED",view["job"])
            self.assertEqual(view["transcript"]["assurance"],"MACHINE_TRANSCRIPT_UNREVIEWED")
            self.assertNotIn("topics", view)
            self.assertNotIn("package_dir", view["job"])
            self.assertTrue(Path(view["job"]["outputs"]["transcript"]).is_file())
            self.assertTrue(Path(view["job"]["outputs"]["subtitles"]).is_file())


if __name__ == "__main__": unittest.main()
