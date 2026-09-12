"""Fail-closed runtime discovery for the pinned read-only SeminarText adapter."""
from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PINNED_COMMIT = "a94936cd77cde13561c97c804ece1ac1134e01a6"
ENTRYPOINT = Path("seminartext_modules/seminartext_topics.py")


def preflight() -> dict[str, Any]:
    """Verify only facts required before Integra can invoke SeminarText topics."""
    checkout_value = os.environ.get("INTEGRA_SEMINARTEXT_CHECKOUT")
    model = os.environ.get("INTEGRA_SEMINARTEXT_TOPIC_MODEL")
    if not checkout_value:
        raise ValueError("SeminarText runtime is not configured")
    if not model:
        raise ValueError("SeminarText topic model is not configured")
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
    if entrypoint.is_symlink() or not entrypoint.is_file():
        raise ValueError("SeminarText Topic Engine entrypoint is missing")
    ollama = shutil.which("ollama")
    if not ollama:
        raise ValueError("Ollama is not installed")
    models = subprocess.run([ollama, "list"], capture_output=True, text=True, check=False, timeout=10).stdout
    if model not in {line.split()[0] for line in models.splitlines()[1:] if line.split()}:
        raise ValueError("SeminarText topic model is unavailable")
    return {"state":"READY","component":"seminartext","commit_sha":commit,"checkout":str(checkout.resolve(strict=True)),"entrypoint":str(entrypoint.resolve(strict=True)),"model":model}


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
