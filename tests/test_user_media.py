import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import unittest

from integra_core.publishing import validate_package
from integra_core.onedrive import validate_onedrive_package
from integra_core.user_media import import_source

ROOT=Path(__file__).resolve().parents[1]


class UserMediaWorkflowTests(unittest.TestCase):
    def test_copy_on_write_import_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/"voice.mp3"; source.write_bytes(b"original")
            record=import_source(root/"project",source)
            self.assertEqual(source.read_bytes(),b"original")
            self.assertEqual(Path(record["owned_path"]).read_bytes(),b"original")
            self.assertFalse(record["source_modified"])

    def test_bridge_runs_media_job_and_builds_both_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); tools=root/"tools"; tools.mkdir(); model=root/"model.bin"; model.write_bytes(b"model")
            ffmpeg=tools/"ffmpeg"; ffmpeg.write_text("#!/bin/sh\nsrc=''\nprev=''\nfor arg in \"$@\"; do [ \"$prev\" = '-i' ] && src=$arg; prev=$arg; out=$arg; done\ncp \"$src\" \"$out\"\n")
            whisper=tools/"whisper-cli"; whisper.write_text("#!/bin/sh\nout=''\nwhile [ $# -gt 0 ]; do [ \"$1\" = '-of' ] && { shift; out=$1; }; shift; done\nprintf '1\\n00:00:00,000 --> 00:00:01,250\\nHello Integra\\n' > \"$out.srt\"\n")
            for path in (ffmpeg,whisper): path.chmod(path.stat().st_mode|stat.S_IXUSR)
            source=root/"voice.wav"; source.write_bytes(b"audio")
            environment={**os.environ,"INTEGRA_APP_DATA_ROOT":str(root/"data"),"INTEGRA_FFMPEG":str(ffmpeg),"INTEGRA_WHISPER_CLI":str(whisper),"INTEGRA_WHISPER_MODEL":str(model)}
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
            self.assertEqual(view["topics"][0]["status"],"REVIEW_REQUIRED")
            package=Path(view["job"]["package_dir"]); manifest=json.loads((package/"package.json").read_bytes())
            files={item["path"]:(package/"files"/item["path"]).read_bytes() for item in manifest["files"]}; validate_package(manifest,files)
            one=Path(json.loads((package/"onedrive_package.json").read_bytes())["package_dir"]); one_manifest=json.loads((one/"package.json").read_bytes())
            one_files={item["path"]:(one/"files"/item["path"]).read_bytes() for item in one_manifest["files"]}; validate_onedrive_package(one_manifest,one_files)


if __name__ == "__main__": unittest.main()
