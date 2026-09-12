"""Fail-closed bridge to the bundled pinned VideoText translation executable."""
from __future__ import annotations
import json, os, subprocess
from pathlib import Path
from typing import Any

RESOURCES=Path(__file__).resolve().parents[1]
WORKER=RESOURCES/"runtime"/"videotext"/"translation-worker"
COMMIT="2e098d1705b6815628bee1e023f4742718eabf02"
ADAPTER_SHA256="83e55d3cb82522cb431ee20617510b0c39f79ae0fa5309daedf5c7ff9911a577"

def preflight() -> dict[str,Any]:
    worker=Path(os.environ.get("INTEGRA_VIDEOTEXT_TRANSLATION_WORKER",str(WORKER)))
    if worker.is_symlink() or not worker.is_file() or not os.access(worker,os.X_OK): raise ValueError("VideoText translation runtime is unavailable")
    ollama=os.environ.get("INTEGRA_OLLAMA","ollama")
    result=subprocess.run([ollama,"list"],capture_output=True,text=True,timeout=10)
    models={line.split()[0] for line in result.stdout.splitlines()[1:] if line.split()}
    model=next((item for item in ("qwen3:8b","qwen2.5:7b") if item in models),None)
    if not model: raise ValueError("VideoText translation model is unavailable")
    return {"state":"READY","component":"videotext","commit_sha":COMMIT,"adapter_sha256":ADAPTER_SHA256,"worker":str(worker.resolve()),"model":model}

def translate(subtitles:Path,output:Path,target:str="en")->dict[str,Any]:
    runtime=preflight(); output.parent.mkdir(parents=True,exist_ok=True)
    result=subprocess.run([runtime["worker"],"--srt",str(subtitles),"--target",target,"--output",str(output)],capture_output=True,text=True,timeout=900)
    if result.returncode or output.is_symlink() or not output.is_file(): raise ValueError("VideoText translation did not produce a validated output")
    value=json.loads(output.read_bytes())
    if value.get("component")!="videotext" or value.get("capability")!="translation" or not value.get("cues"): raise ValueError("VideoText translation output is invalid")
    return value
