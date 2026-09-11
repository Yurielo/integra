#!/usr/bin/env python3
"""Create and verify non-destructive READY_APP_V1 project snapshots."""
import argparse, hashlib, json, os, shutil, tempfile
from pathlib import Path

def inventory(root):
    result=[]
    for path in sorted(root.rglob("*")):
        if path.is_symlink(): raise ValueError("backup source contains symlink")
        if path.is_file(): result.append({"path":path.relative_to(root).as_posix(),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"size":path.stat().st_size})
        elif not path.is_dir(): raise ValueError("backup source contains special filesystem object")
    return result

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("mode",choices=["create","verify"]); parser.add_argument("source"); parser.add_argument("snapshot"); args=parser.parse_args()
    source=Path(args.source); snapshot=Path(args.snapshot)
    if args.mode=="create":
        if source.is_symlink() or not source.is_dir() or snapshot.exists(): raise ValueError("unsafe backup source or existing snapshot")
        snapshot.parent.mkdir(parents=True,exist_ok=True); temporary=Path(tempfile.mkdtemp(prefix=".integra-backup-",dir=snapshot.parent))
        try:
            shutil.copytree(source,temporary/"data",symlinks=False,dirs_exist_ok=True)
            manifest={"schema_version":"1.0","files":inventory(temporary/"data")}
            (temporary/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,separators=(",",":"))+"\n")
            os.replace(temporary,snapshot)
        except Exception:
            shutil.rmtree(temporary,ignore_errors=True); raise
    manifest=json.loads((snapshot/"manifest.json").read_text())
    if manifest!={"schema_version":"1.0","files":inventory(snapshot/"data")}: raise ValueError("snapshot verification failed")
    print("INTEGRA_BACKUP_VERIFICATION: PASS")
if __name__=="__main__": main()
