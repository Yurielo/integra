"""Deterministic discovery for an externally installed macOS Ollama CLI."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


MACOS_OLLAMA_PATHS = (
    Path("/opt/homebrew/bin/ollama"),
    Path("/usr/local/bin/ollama"),
    Path("/Applications/Ollama.app/Contents/Resources/ollama"),
)


def resolve_ollama() -> Path:
    """Resolve a configured, shell, or standard macOS Ollama executable."""
    configured = os.environ.get("INTEGRA_OLLAMA")
    candidates = [configured] if configured else []
    found = shutil.which("ollama")
    if found:
        candidates.append(found)
    candidates.extend(str(path) for path in MACOS_OLLAMA_PATHS)
    for value in candidates:
        try:
            path = Path(value).expanduser().resolve(strict=True)
        except OSError:
            continue
        if path.is_file() and os.access(path, os.X_OK):
            return path
    raise ValueError("Ollama is unavailable: install it or make its executable available to Integra")


def listed_models() -> tuple[Path, set[str]]:
    """Return local model names without exposing a raw executable error."""
    executable = resolve_ollama()
    try:
        result = subprocess.run([str(executable), "list"], capture_output=True, text=True,
                                check=False, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("Ollama is unavailable: its executable could not be run") from error
    if result.returncode != 0:
        raise ValueError("Ollama is unavailable: model inventory could not be read")
    return executable, {line.split()[0] for line in result.stdout.splitlines()[1:] if line.split()}
