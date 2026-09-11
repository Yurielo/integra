import hashlib, os, platform, subprocess, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def tree_hash(root):
    value=hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file(): value.update(path.relative_to(root).as_posix().encode()+b"\0"+path.read_bytes())
    return value.hexdigest()

class ReadyAppTests(unittest.TestCase):
    def test_backup_is_verified_and_detects_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/"source"; source.mkdir(); (source/"project.json").write_text("{}")
            snapshot=root/"snapshot"; script=ROOT/"scripts/integra_backup.py"
            result=subprocess.run(["python3",str(script),"create",str(source),str(snapshot)],check=True,capture_output=True,text=True)
            self.assertIn("PASS",result.stdout)
            subprocess.run(["python3",str(script),"verify",str(source),str(snapshot)],check=True)
            (snapshot/"data/project.json").write_text("changed")
            self.assertNotEqual(subprocess.run(["python3",str(script),"verify",str(source),str(snapshot)],capture_output=True).returncode,0)

    def test_bridge_error_redacts_home_path(self):
        bridge=ROOT/"macos/Resources/bridge.py"
        result=subprocess.run(["python3",str(bridge),"package-preview"],input='{"package_dir":"'+str(Path.home()/"secret/path")+'","target_dir":"/tmp"}',capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0); self.assertNotIn(str(Path.home()),result.stdout)

    @unittest.skipUnless(platform.system()=="Darwin","READY_APP packaging requires macOS")
    def test_local_candidate_is_reproducible_signed_and_launchable(self):
        script=ROOT/"scripts/package_ready_app.sh"
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); one=subprocess.run([str(script),str(root/"one")],check=True,capture_output=True,text=True).stdout.strip().splitlines()[-1]
            two=subprocess.run([str(script),str(root/"two")],check=True,capture_output=True,text=True).stdout.strip().splitlines()[-1]
            self.assertEqual(tree_hash(Path(one)),tree_hash(Path(two)))
            subprocess.run(["codesign","--verify","--deep","--strict",one],check=True)
            result=subprocess.run([str(Path(one)/"Contents/MacOS/Integra"),"--self-test"],check=True,capture_output=True,text=True)
            self.assertIn("PASS",result.stdout)

if __name__=="__main__": unittest.main()
