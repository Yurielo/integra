"""Fail-closed local WhisperX runtime for Integra-owned Word Timeline artifacts."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .candidate_identity import load_manifest, sanitized_environment, write_evidence

MODEL_SHA256 = "d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c"
MODEL_REVISION = "2329100508896c6d9b157019803ab5601e6f3406"
RESOURCES = Path(__file__).resolve().parents[1]
BUNDLED_SITE_PACKAGES = RESOURCES / "runtime" / "word-alignment" / "site-packages"
BUNDLED_MODEL_DIR = RESOURCES / "runtime" / "word-alignment" / "model"
WORKER = RESOURCES / "workers" / "seminartext_word_alignment_worker.py"
FFMPEG_SEARCH_PATHS = (
    "/opt/homebrew/opt/ffmpeg-full/bin",
    "/usr/local/opt/ffmpeg-full/bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_ffmpeg() -> dict[str, Any]:
    """Resolve the external tool without relying on a GUI-inherited PATH."""
    candidates: list[tuple[str, Path]] = []
    configured = os.environ.get("INTEGRA_FFMPEG")
    if configured:
        candidates.append(("INTEGRA_FFMPEG", Path(configured).expanduser()))
    candidates.extend((f"standard:{directory}", Path(directory) / "ffmpeg") for directory in FFMPEG_SEARCH_PATHS)
    seen: set[str] = set()
    for source, candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if str(resolved) in seen or not resolved.is_file() or not os.access(resolved, os.X_OK):
            continue
        seen.add(str(resolved))
        try:
            version = subprocess.run([str(resolved), "-version"], capture_output=True, text=True,
                                     check=False, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue
        if version.returncode != 0:
            continue
        version_output = (version.stdout or version.stderr).splitlines()
        return {
            "path": str(resolved),
            "sha256": _sha256(resolved),
            "version": version_output[0] if version_output else "",
            "resolution_source": source,
            "path_classification": {
                "uses_inherited_path": False,
                "homebrew_directory": "/opt/homebrew" in str(resolved),
                "parent": str(resolved.parent),
            },
        }
    raise ValueError("Word Timeline ffmpeg runtime is unavailable")


def _worker_environment(runtime: dict[str, Any]) -> dict[str, str]:
    """Give WhisperX a bounded deterministic PATH containing resolved ffmpeg."""
    ffmpeg = Path(runtime["ffmpeg"]["path"])
    bounded_path = os.pathsep.join([str(ffmpeg.parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
    return {
        **os.environ,
        "PATH": bounded_path,
        "INTEGRA_FFMPEG": str(ffmpeg),
        "INTEGRA_FFMPEG_RESOLUTION_SOURCE": str(runtime["ffmpeg"]["resolution_source"]),
        "PYTHONPATH": runtime["site_packages"],
        "HF_HUB_OFFLINE": "1",
    }


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
    ffmpeg = resolve_ffmpeg()
    return {"state":"READY", "component":"seminartext", "capability":"word_timeline", "python":str(python),
            "site_packages":str(packages.resolve(strict=True)), "model_dir":str(model.resolve(strict=True)),
            "model_revision":MODEL_REVISION, "model_sha256":MODEL_SHA256, "worker":str(WORKER.resolve(strict=True)),
            "ffmpeg":ffmpeg}


def _candidate_manifest() -> dict[str, Any] | None:
    try:
        return load_manifest(RESOURCES)
    except ValueError:
        return None


def generate_word_timeline(audio: Path, subtitles: Path, output: Path,
                           *, diagnostic_context: dict[str, str] | None = None) -> dict[str, Any]:
    """Run the external worker and persist bounded, candidate-bound evidence."""
    runtime = preflight()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [runtime["python"], runtime["worker"], "--audio", str(audio), "--srt", str(subtitles),
               "--model-dir", runtime["model_dir"], "--output", str(output)]
    environment = _worker_environment(runtime)
    stdout = stderr = ""
    exit_status: int | None = None
    reason: str | None = None
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=1200, env=environment)
        stdout, stderr, exit_status = completed.stdout, completed.stderr, completed.returncode
        if exit_status != 0 or output.is_symlink() or not output.is_file():
            reason = "worker_nonzero_exit_or_missing_output"
            raise ValueError("Word Timeline worker did not produce a validated output")
        result = json.loads(output.read_bytes())
        words = result.get("words") if isinstance(result, dict) else None
        if result.get("capability") != "word_timeline" or not isinstance(words, list) or not words:
            reason = "output_validator_invalid_structure"
            raise ValueError("Word Timeline output is invalid")
        if any(item.get("alignment_status") not in {"ALIGNED", "UNALIGNED"} for item in words if isinstance(item, dict)):
            reason = "output_validator_invalid_alignment_status"
            raise ValueError("Word Timeline alignment status is invalid")
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""; stderr = error.stderr or ""; reason = "worker_timeout"
        raise ValueError("Word Timeline worker timed out") from error
    except json.JSONDecodeError as error:
        reason = "output_validator_invalid_json"
        raise ValueError("Word Timeline output is invalid") from error
    finally:
        evidence = output.with_suffix(".worker-evidence.json")
        context = diagnostic_context or {}
        details = {
            "stage": context.get("stage", "word_timeline"), "run_id": context.get("run_id"),
            "command": command, "environment": sanitized_environment(environment), "runtime": runtime,
            "timeout_seconds": 1200, "exit_status": exit_status,
            "stdout_tail": stdout[-16384:], "stderr_tail": stderr[-16384:],
            "inputs": {"audio_sha256": _sha256(audio), "subtitles_sha256": _sha256(subtitles)},
            "output_sha256": _sha256(output) if output.is_file() and not output.is_symlink() else None,
            "validator_reason": reason,
        }
        write_evidence(evidence, candidate=_candidate_manifest(), gate_name="word_timeline_worker",
                       result="PASS" if reason is None and exit_status == 0 else "FAIL",
                       timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                       artifact_locations=[str(evidence), str(output)], details=details)
    return result
