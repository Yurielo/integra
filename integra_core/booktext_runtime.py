"""Fail-closed local bridge to the pinned personal BookText OCR runtime."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


RESOURCES = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = RESOURCES / "runtime" / "booktext"
ENTRYPOINT = RUNTIME_ROOT / "booktext.py"
WORKER = RESOURCES / "workers" / "booktext_ocr_worker.py"
RUNTIME_MANIFEST = RUNTIME_ROOT / "runtime.json"
PINNED_COMMIT = "46396649214275eb18054b670a842bace02d02e1"
ENTRYPOINT_SHA256 = "32ecbb3f9a46e0648f4f701a3935487d0be91799334b27128161a51a1f99f05f"
VISION_SHA256 = "3b5a25577a58713cb4cb3a7e81d3883bdf822ce9df6ef0aa4b60d56186e92753"


def validate_page_selection(pages: str | None = None, exclude_pages: str | None = None) -> dict[str, str | None]:
    """Validate CLI transport, leaving actual page resolution to BookText."""
    result = {}
    for key, value in (("pages", pages), ("exclude_pages", exclude_pages)):
        if value is None or value == "":
            result[key] = None
            continue
        if not isinstance(value, str) or len(value) > 4096:
            raise ValueError("BookText page selection must be a bounded page/range string")
        parts = value.split(",")
        normalized = []
        for part in parts:
            part = part.strip()
            if not re.fullmatch(r"[1-9][0-9]*(?:-[1-9][0-9]*)?", part):
                raise ValueError("BookText pages must use positive numbers or ranges, for example 1-5,8")
            numbers = [int(item) for item in part.split("-")]
            if any(number > 100000 for number in numbers) or numbers[-1] < numbers[0]:
                raise ValueError("BookText page range is invalid or exceeds 100000")
            normalized.append(part)
        result[key] = ",".join(normalized)
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _executable(configured: str | None, fallback: Path | None, command: str) -> Path:
    candidates = [configured] if configured else []
    if fallback is not None:
        candidates.append(str(fallback))
    discovered = shutil.which(command)
    if discovered:
        candidates.append(discovered)
    for value in candidates:
        if not value:
            continue
        try:
            path = Path(value).expanduser().resolve(strict=True)
        except OSError:
            continue
        if not path.is_symlink() and path.is_file() and os.access(path, os.X_OK):
            return path
    raise ValueError(f"BookText dependency is unavailable: {command}")


def preflight() -> dict[str, Any]:
    """Verify the packaged BookText code and required local OCR tools."""
    if ENTRYPOINT.is_symlink() or not ENTRYPOINT.is_file() or _sha256(ENTRYPOINT) != ENTRYPOINT_SHA256:
        raise ValueError("BookText runtime differs from the pinned component")
    if WORKER.is_symlink() or not WORKER.is_file():
        raise ValueError("BookText OCR worker is missing")
    try:
        manifest = json.loads(RUNTIME_MANIFEST.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("BookText runtime manifest is unavailable") from error
    if manifest != {
        "component": "booktext", "commit_sha": PINNED_COMMIT,
        "entrypoint_sha256": ENTRYPOINT_SHA256, "vision_sha256": VISION_SHA256,
        "personal_use_only": True,
    }:
        raise ValueError("BookText runtime manifest differs from the pinned component")
    surya = _executable(
        os.environ.get("INTEGRA_BOOKTEXT_SURYA_CLI"),
        Path.home() / "AITools/booktext/benchmark/surya-env/bin/surya_ocr",
        "surya_ocr",
    )
    vision = _executable(
        os.environ.get("INTEGRA_BOOKTEXT_VISION_OCR"),
        RUNTIME_ROOT / "visionocr",
        "visionocr",
    )
    if os.environ.get("INTEGRA_BOOKTEXT_SURYA_MODEL"):
        raise ValueError("BookText custom model override cannot be verified by the source CLI")
    model = Path.home() / ".cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2.gguf"
    try:
        model = model.resolve(strict=True)
    except OSError as error:
        raise ValueError("BookText Surya model is unavailable") from error
    if not model.is_file() or model.is_symlink():
        raise ValueError("BookText Surya model is unavailable")
    model_sha256 = _sha256(model)
    tools = {name: _executable(None, None, name) for name in ("magick", "pdftoppm", "ddjvu", "djvused", "tesseract", "ocrmypdf", "llama-server")}
    return {
        "state": "READY", "component": "booktext", "commit_sha": PINNED_COMMIT,
        "entrypoint": str(ENTRYPOINT.resolve(strict=True)), "surya": str(surya),
        "vision": str(vision), "model": str(model), "model_sha256": model_sha256,
        "model_evidence": "AVAILABLE_LOCAL_MODEL_NOT_EXECUTION_ATTESTATION",
        "tools": {key: str(value) for key, value in tools.items()},
    }


def run_ocr(source: Path, output_dir: Path, *, pages: str | None = None, exclude_pages: str | None = None) -> dict[str, Any]:
    """Run real BookText OCR and return its persisted integration manifest."""
    selection = validate_page_selection(pages, exclude_pages)
    runtime = preflight()
    if source.is_symlink() or not source.is_file():
        raise ValueError("BookText source is unavailable")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_sha256 = _sha256(source)
    command = [sys.executable, str(WORKER), "--booktext", str(ENTRYPOINT), "--source", str(source),
               "--output-dir", str(output_dir), "--surya", runtime["surya"], "--vision", runtime["vision"]]
    for key, value in selection.items():
        if value is not None:
            command.extend(["--" + key.replace("_", "-"), value])
    completed = subprocess.run(
        command,
        capture_output=True, text=True, timeout=1800,
    )
    manifest_path = output_dir / "integra_booktext_manifest.json"
    if completed.returncode != 0 or manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("BookText OCR did not produce a validated output")
    try:
        result = json.loads(manifest_path.read_bytes())
    except json.JSONDecodeError as error:
        raise ValueError("BookText OCR integration manifest is invalid") from error
    if result.get("component") != "booktext" or result.get("commit_sha") != PINNED_COMMIT or not result.get("blocks"):
        raise ValueError("BookText OCR output is invalid")
    if result.get("selection") != selection or result.get("source_sha256") != source_sha256 or _sha256(source) != source_sha256:
        raise ValueError("BookText OCR source or selection provenance differs")
    result["runtime"] = {"commit_sha": PINNED_COMMIT, "surya": runtime["surya"], "vision": runtime["vision"], "model_sha256": runtime["model_sha256"]}
    result["runtime"]["model_evidence"] = runtime["model_evidence"]
    return result
