import hashlib, os, platform, subprocess, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def macos_build_runtime_available():
    seminartext = Path(os.environ.get("INTEGRA_SEMINARTEXT_BUILD_CHECKOUT", ROOT / ".runtime-components/seminartext-pinned"))
    videotext = Path(os.environ.get("INTEGRA_VIDEOTEXT_BUILD_CHECKOUT", ROOT / ".runtime-components/videotext-pinned"))
    booktext = Path(os.environ.get("INTEGRA_BOOKTEXT_BUILD_CHECKOUT", ROOT / ".runtime-components/booktext-pinned"))
    packages = Path(os.environ.get("INTEGRA_WORD_ALIGNMENT_SITE_PACKAGES", ROOT / ".runtime-word-alignment/lib/python3.13/site-packages"))
    model = Path(os.environ.get("INTEGRA_WORD_ALIGNMENT_MODEL_DIR", "/Users/yurielokhin/.cache/huggingface/hub/models--jonatasgrosman--wav2vec2-large-xlsr-53-russian/snapshots/2329100508896c6d9b157019803ab5601e6f3406"))
    python = Path(os.environ.get("INTEGRA_WORD_ALIGNMENT_PYTHON", "/opt/homebrew/opt/python@3.13/bin/python3.13"))
    return all(((seminartext / ".git").exists(), (videotext / ".git").exists(),
                (booktext / ".git").exists(), (packages / "whisperx").is_dir(),
                (model / "pytorch_model.bin").is_file(), os.access(python, os.X_OK)))

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

    @unittest.skipUnless(
        platform.system()=="Darwin" and macos_build_runtime_available(),
        "READY_APP packaging requires the pinned external runtime sources",
    )
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
