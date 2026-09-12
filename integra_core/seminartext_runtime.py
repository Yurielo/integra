"""Fail-closed runtime discovery for the pinned read-only SeminarText adapter."""
from __future__ import annotations

import os
import shutil
import subprocess
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
