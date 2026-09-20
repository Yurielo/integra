"""Fail-closed local WhisperX runtime for Integra-owned Word Timeline artifacts."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

MODEL_SHA256 = "d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c"
MODEL_REVISION = "2329100508896c6d9b157019803ab5601e6f3406"
RESOURCES = Path(__file__).resolve().parents[1]
BUNDLED_SITE_PACKAGES = RESOURCES / "runtime" / "word-alignment" / "site-packages"
BUNDLED_MODEL_DIR = RESOURCES / "runtime" / "word-alignment" / "model"
WORKER = RESOURCES / "workers" / "seminartext_word_alignment_worker.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight() -> dict[str, Any]:
    python_candidate = Path(os.environ.get("INTEGRA_WORD_ALIGNMENT_PYTHON", "/opt/homebrew/opt/python@3.13/bin/python3.13"))
    packages = Path(os.environ.get("INTEGRA_WORD_ALIGNMENT_SITE_PACKAGES", str(BUNDLED_SITE_PACKAGES)))
    model = Path(os.environ.get("INTEGRA_WORD_ALIGNMENT_MODEL_DIR", str(BUNDLED_MODEL_DIR)))
    try:
        python = python_candidate.resolve(strict=True)
    except OSError:
        raise ValueError("Word Timeline Python 3.13 runtime is unavailable") from None
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError("Word Timeline Python 3.13 runtime is unavailable")
    if packages.is_symlink() or not packages.is_dir() or not (packages / "whisperx").is_dir():
        raise ValueError("Word Timeline WhisperX runtime is unavailable")
    weights = model / "pytorch_model.bin"
    if model.is_symlink() or not model.is_dir() or weights.is_symlink() or not weights.is_file():
        raise ValueError("pinned Russian Word Timeline model is unavailable")
    if _sha256(weights) != MODEL_SHA256:
        raise ValueError("pinned Russian Word Timeline model hash differs")
    if WORKER.is_symlink() or not WORKER.is_file():
        raise ValueError("Word Timeline worker is unavailable")
    version = subprocess.run([str(python), "--version"], capture_output=True, text=True, check=False, timeout=5)
    if version.returncode != 0 or not version.stdout.startswith("Python 3.13."):
        raise ValueError("Word Timeline requires Python 3.13")
    imported = subprocess.run([str(python), "-c", "import whisperx; print('READY')"], capture_output=True, text=True,
                               env={**os.environ, "PYTHONPATH": str(packages), "HF_HUB_OFFLINE": "1"}, timeout=20)
    if imported.returncode != 0 or imported.stdout.strip() != "READY":
        raise ValueError("Word Timeline WhisperX runtime cannot be imported")
    return {"state":"READY", "component":"seminartext", "capability":"word_timeline", "python":str(python),
            "site_packages":str(packages.resolve(strict=True)), "model_dir":str(model.resolve(strict=True)),
            "model_revision":MODEL_REVISION, "model_sha256":MODEL_SHA256, "worker":str(WORKER.resolve(strict=True))}


def generate_word_timeline(audio: Path, subtitles: Path, output: Path) -> dict[str, Any]:
    runtime = preflight()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [runtime["python"], runtime["worker"], "--audio", str(audio), "--srt", str(subtitles),
               "--model-dir", runtime["model_dir"], "--output", str(output)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=1200,
                               env={**os.environ, "PYTHONPATH": runtime["site_packages"], "HF_HUB_OFFLINE":"1"})
    diagnostic = output.with_suffix(".worker-diagnostic.json")
    diagnostic.write_text(json.dumps({"schema_version": "1.0", "component": "seminartext",
        "stage": "word_timeline", "command": command, "exit_status": completed.returncode,
        "stdout": completed.stdout[-16384:], "stderr": completed.stderr[-16384:]}, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    if completed.returncode != 0 or output.is_symlink() or not output.is_file():
        raise ValueError(f"Word Timeline worker did not produce a validated output; diagnostics: {diagnostic}")
    result = json.loads(output.read_bytes()); words = result.get("words") if isinstance(result, dict) else None
    if result.get("capability") != "word_timeline" or not isinstance(words, list) or not words:
        raise ValueError("Word Timeline output is invalid")
    if any(item.get("alignment_status") not in {"ALIGNED", "UNALIGNED"} for item in words if isinstance(item, dict)):
        raise ValueError("Word Timeline alignment status is invalid")
    return result
