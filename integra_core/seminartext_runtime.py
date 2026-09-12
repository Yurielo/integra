"""Fail-closed runtime discovery for the pinned read-only SeminarText adapter."""
from __future__ import annotations

import os
import json
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PINNED_COMMIT = "a94936cd77cde13561c97c804ece1ac1134e01a6"
ENTRYPOINT = Path("seminartext_modules/seminartext_topics.py")
ENTRYPOINT_SHA256 = "d8a14e83b877024c3e016a33e594af17d512741a77735ff3d8c7d1262628c8db"
BUNDLED_RUNTIME_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "seminartext"


def _entrypoint_is_exact(entrypoint: Path) -> bool:
    return (not entrypoint.is_symlink() and entrypoint.is_file()
            and hashlib.sha256(entrypoint.read_bytes()).hexdigest() == ENTRYPOINT_SHA256)


def preflight() -> dict[str, Any]:
    """Verify only facts required before Integra can invoke SeminarText topics."""
    checkout_value = os.environ.get("INTEGRA_SEMINARTEXT_CHECKOUT")
    model = os.environ.get("INTEGRA_SEMINARTEXT_TOPIC_MODEL", "gemma3:4b")
    if checkout_value:
        checkout = Path(checkout_value)
        if checkout.is_symlink() or not checkout.is_dir():
            raise ValueError("SeminarText checkout is unsafe or missing")
        try:
            commit = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError("SeminarText checkout cannot be verified") from error
        if commit != PINNED_COMMIT:
            raise ValueError("SeminarText checkout does not match the pinned commit")
        entrypoint = checkout / ENTRYPOINT
        origin = "EXTERNAL_PINNED_CHECKOUT"
    else:
        checkout = BUNDLED_RUNTIME_ROOT
        commit = PINNED_COMMIT
        entrypoint = checkout / ENTRYPOINT
        origin = "BUNDLED_PERSONAL_RUNTIME"
        if checkout.is_symlink() or not checkout.is_dir():
            raise ValueError("SeminarText runtime is not configured")
    if not _entrypoint_is_exact(entrypoint):
        raise ValueError("SeminarText Topic Engine entrypoint differs from the pinned runtime")
    ollama = shutil.which("ollama")
    if not ollama:
        raise ValueError("Ollama is not installed")
    models = subprocess.run([ollama, "list"], capture_output=True, text=True, check=False, timeout=10).stdout
    if model not in {line.split()[0] for line in models.splitlines()[1:] if line.split()}:
        raise ValueError("SeminarText topic model is unavailable")
    return {"state":"READY","component":"seminartext","commit_sha":commit,"checkout":str(checkout.resolve(strict=True)),"entrypoint":str(entrypoint.resolve(strict=True)),"model":model,"origin":origin}


def generate_topics(subtitles: Path, output: Path) -> dict[str, Any]:
    """Invoke the pinned Topic Engine and accept only its validated draft output."""
    runtime = preflight()
    if subtitles.is_symlink() or not subtitles.is_file():
        raise ValueError("timed subtitles are unavailable")
    output.parent.mkdir(parents=True, exist_ok=True)
    worker = Path(__file__).resolve().parents[1] / "workers" / "seminartext_topics_worker.py"
    if worker.is_symlink() or not worker.is_file():
        raise ValueError("SeminarText Topic Engine worker is missing")
    completed = subprocess.run(
        [sys.executable, str(worker), "--checkout", runtime["checkout"], "--srt", str(subtitles),
         "--model", runtime["model"], "--output", str(output)],
        capture_output=True, text=True, timeout=900,
    )
    if completed.returncode != 0 or output.is_symlink() or not output.is_file():
        raise ValueError("SeminarText Topic Engine did not produce a validated output")
    result = json.loads(output.read_bytes())
    topics = result.get("topics") if isinstance(result, dict) else None
    if result.get("component") != "seminartext" or not isinstance(topics, list) or not topics:
        raise ValueError("SeminarText Topic Engine output is invalid")
    if any(item.get("semantic_status") != "REVIEW_REQUIRED" for item in topics if isinstance(item, dict)):
        raise ValueError("SeminarText Topic Engine output has invalid semantic status")
    result["runtime"] = {"commit_sha": runtime["commit_sha"], "model": runtime["model"]}
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result
