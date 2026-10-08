#!/usr/bin/env python3
"""Generate and validate an immutable, embedded Integra Candidate Manifest."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integra_core.candidate_identity import (  # noqa: E402
    MANIFEST_NAME, candidate_id, canonical_bytes, sha256_file, tree_sha256,
    validate_bundle,
)


def command(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15).stdout.strip()


def source_identity(root: Path) -> dict[str, object]:
    dirty = command("git", "-C", str(root), "status", "--porcelain")
    diff = subprocess.run(["git", "-C", str(root), "diff", "--binary", "HEAD"], check=True,
                          capture_output=True, timeout=15).stdout
    return {
        "commit_sha": command("git", "-C", str(root), "rev-parse", "HEAD"),
        "tree_sha": command("git", "-C", str(root), "rev-parse", "HEAD^{tree}"),
        "dirty": bool(dirty),
        "dirty_diff_sha256": __import__("hashlib").sha256(diff).hexdigest(),
    }


def source_timestamp(root: Path) -> str:
    """Use the source commit time so identical sources package identically."""
    return command("git", "-C", str(root), "show", "-s", "--format=%cI", "HEAD")


def executable_identity(path: Path) -> dict[str, str]:
    resolved = path.resolve(strict=True)
    version = command(str(resolved), "--version")
    arch = command("file", "-b", str(resolved))
    return {"path": str(resolved), "sha256": sha256_file(resolved), "version": version, "architecture": arch}


def optional_ollama_identity() -> dict[str, object]:
    contract = {
        "resolution_order": ["INTEGRA_OLLAMA", "PATH:ollama", "/opt/homebrew/bin/ollama",
                             "/usr/local/bin/ollama", "/Applications/Ollama.app/Contents/Resources/ollama"],
    }
    try:
        from integra_core.ollama_runtime import resolve_ollama
        executable = resolve_ollama()
        result = subprocess.run([str(executable), "--version"], capture_output=True, text=True,
                                check=False, timeout=10)
        contract.update({"state": "RESOLVED", "executable": executable_identity(executable),
                         "version_output": (result.stdout or result.stderr).strip(), "version_exit_status": result.returncode})
    except (OSError, subprocess.SubprocessError, ValueError):
        contract["state"] = "UNRESOLVED_AT_BUILD"
    return contract


def generate(app: Path, source_root: Path, build_command: str, word_python: Path) -> dict[str, object]:
    app = app.resolve(strict=True)
    resources = app / "Contents" / "Resources"
    if (resources / MANIFEST_NAME).exists():
        raise ValueError("candidate manifest already exists; build output must be fresh")
    seminar_root = resources / "runtime" / "seminartext"
    word_root = resources / "runtime" / "word-alignment"
    video_root = resources / "runtime" / "videotext"
    book_root = resources / "runtime" / "booktext"
    seminar = json.loads((seminar_root / "runtime.json").read_text(encoding="utf-8"))
    video = json.loads((video_root / "runtime.json").read_text(encoding="utf-8"))
    book = json.loads((book_root / "runtime.json").read_text(encoding="utf-8"))
    word = json.loads((word_root / "runtime.json").read_text(encoding="utf-8"))
    from integra_core.word_timeline_runtime import resolve_ffmpeg
    ffmpeg = resolve_ffmpeg()
    word.update({
        "site_packages_tree_sha256": tree_sha256(word_root / "site-packages"),
        "weights_actual_sha256": sha256_file(word_root / "model" / "pytorch_model.bin"),
    })
    from integra_core.translategemma_runtime import preflight as translation_preflight
    translation = translation_preflight()
    identity = {
        "source": source_identity(source_root),
        "build_command": {"path": "scripts/build_macos_app.sh", "identity": build_command,
                          "script_sha256": sha256_file(ROOT / "scripts" / "build_macos_app.sh")},
        "components": {"seminartext": seminar, "videotext": video, "booktext": book,
                       "integra.translation": translation},
        "execution": {
            "gui_python": executable_identity(Path("/usr/bin/python3")),
            "word_alignment_python": executable_identity(word_python),
            "word_alignment": word,
            "word_timeline_ffmpeg": ffmpeg,
            "ollama": optional_ollama_identity(),
            "host_architecture": platform.machine(),
        },
    }
    digest = tree_sha256(app, exclude={"Contents/Resources/" + MANIFEST_NAME})
    value: dict[str, object] = {
        "schema_version": "1.0",
        "candidate_id": candidate_id(identity),
        "identity_sha256": candidate_id(identity).removeprefix("candidate-v1-"),
        "identity": identity,
        "bundle": {"digest_algorithm": "sha256-tree-excluding-candidate-manifest", "digest": digest},
        "build": {"timestamp": source_timestamp(source_root),
                  "build_id": os.environ.get("INTEGRA_BUILD_ID", "local")},
    }
    (resources / MANIFEST_NAME).write_bytes(canonical_bytes(value) + b"\n")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="operation", required=True)
    create = sub.add_parser("generate")
    create.add_argument("--app", type=Path, required=True)
    create.add_argument("--source-root", type=Path, default=ROOT)
    create.add_argument("--build-command", default="scripts/build_macos_app.sh")
    create.add_argument("--word-python", type=Path, required=True)
    check = sub.add_parser("validate")
    check.add_argument("app", type=Path)
    args = parser.parse_args()
    value = generate(args.app, args.source_root, args.build_command, args.word_python) if args.operation == "generate" else validate_bundle(args.app)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
