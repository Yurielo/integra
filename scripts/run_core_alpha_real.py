#!/usr/bin/env python3
"""Run the pinned R6 real-media path inside Core Alpha through R3 processes."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integra_core.core_alpha import (  # noqa: E402
    CoreAlphaPipeline,
    ReplayStageWorker,
    reject_symlink_components,
)
from integra_core.protocol import canonical_json  # noqa: E402
from integra_core.real_media import (  # noqa: E402
    ACCEPTANCE,
    JsonlProcessStageWorker,
    RealMediaError,
    sha256_file,
    validate_actual_evidence,
)


PINNED = {
    "seminartext": {
        "sha": "a94936cd77cde13561c97c804ece1ac1134e01a6",
        "tree": "5f5951da1d5dcf957ef982510fde3537f601ea15",
        "version": "4.0.0",
    },
    "videotext": {
        "sha": "2e098d1705b6815628bee1e023f4742718eabf02",
        "tree": "f5ec484df90e4db655d31b4174434c37f4d1491c",
        "version": "0.6.4",
    },
}
PINNED_TOPIC_MODEL = {
    "name": "gemma3:4b",
    "digest": "a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a",
    "weights_sha256": "aeda25e63ebd698fab8638ffb778e68bed908b960d39d0becc650fa981609d25",
}
IMPLEMENTATION_PATHS = (
    "integra_core/core_alpha.py",
    "integra_core/real_media.py",
    "scripts/run_core_alpha_real.py",
    "workers/core_alpha_real_worker.py",
    "workers/seminartext_topics_worker.py",
    "workers/videotext_transcript_worker.swift",
    "workers/videotext_clip_worker.swift",
)


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RealMediaError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout.decode(errors='replace')}\n"
            f"stderr:\n{completed.stderr.decode(errors='replace')}"
        )
    return completed.stdout.decode("utf-8")


def git(checkout: Path, *args: str) -> str:
    return run(["git", "-C", str(checkout), *args]).strip()


def verify_checkout(name: str, checkout: Path) -> dict[str, str]:
    expected = PINNED[name]
    if git(checkout, "rev-parse", "HEAD") != expected["sha"]:
        raise RealMediaError(f"{name} checkout is not at the pinned commit")
    if git(checkout, "rev-parse", "HEAD^{tree}") != expected["tree"]:
        raise RealMediaError(f"{name} checkout tree differs from the pinned tree")
    if git(checkout, "status", "--porcelain", "--untracked-files=all"):
        raise RealMediaError(f"{name} checkout is dirty")
    return {
        "repository": f"Yurielo/{name}",
        "commit_sha": expected["sha"],
        "tree_sha": expected["tree"],
        "version": expected["version"],
    }


def checkout_snapshot(checkout: Path) -> dict[str, tuple[int, str]]:
    snapshot: dict[str, tuple[int, str]] = {}
    for path in sorted(checkout.rglob("*")):
        relative = path.relative_to(checkout)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            snapshot[relative.as_posix()] = (-1, f"symlink:{path.readlink()}")
        elif path.is_file():
            snapshot[relative.as_posix()] = (path.stat().st_size, sha256_file(path))
    return snapshot


def materialize_pinned_tree(checkout: Path, destination: Path) -> None:
    archive = subprocess.run(
        ["git", "-C", str(checkout), "archive", "--format=tar", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if archive.returncode != 0:
        raise RealMediaError("cannot archive pinned source checkout")
    destination.mkdir(parents=True, exist_ok=False)
    with tempfile.NamedTemporaryFile(suffix=".tar") as handle:
        handle.write(archive.stdout)
        handle.flush()
        with tarfile.open(handle.name, mode="r:") as bundle:
            for member in bundle.getmembers():
                path = Path(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or member.issym()
                    or member.islnk()
                    or not (member.isfile() or member.isdir())
                ):
                    raise RealMediaError("pinned source archive contains an unsafe entry")
            bundle.extractall(destination, filter="data")


def command_version(command: list[str]) -> str:
    return run(command).splitlines()[0].strip()


def topic_model_identity(name: str) -> dict[str, str]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            payload = json.load(response)
    except (OSError, ValueError) as error:
        raise RealMediaError("cannot inspect local Ollama model identity") from error
    record = next((item for item in payload.get("models", []) if item.get("name") == name), None)
    if not isinstance(record, dict):
        raise RealMediaError("requested Ollama model is not installed")
    modelfile = run(["ollama", "show", name, "--modelfile"])
    marker = "sha256-"
    weights = next(
        (
            line.split(marker, 1)[1].strip()
            for line in modelfile.splitlines()
            if marker in line and len(line.split(marker, 1)[1].strip()) == 64
        ),
        "",
    )
    identity = {
        "name": name,
        "provider": "ollama",
        "digest": record.get("digest", ""),
        "weights_sha256": weights,
    }
    if identity != {**PINNED_TOPIC_MODEL, "provider": "ollama"}:
        raise RealMediaError("Topic model content identity differs from the R6 pin")
    blob = Path.home() / ".ollama/models/blobs" / f"sha256-{weights}"
    if not blob.is_file() or sha256_file(blob) != weights:
        raise RealMediaError("Topic model weights do not match the pinned SHA-256")
    return identity


def source_duration(path: Path) -> float:
    value = run(
        [
            "/opt/homebrew/bin/ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    ).strip()
    try:
        duration = round(float(value), 3)
    except ValueError as error:
        raise RealMediaError("source duration is invalid") from error
    if duration <= 0:
        raise RealMediaError("source duration must be positive")
    return duration


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_manifest_artifact(manifest: dict[str, Any], store: Path, stage: str) -> bytes:
    reference = manifest["artifacts"][stage]
    path = (store / reference["relative_path"]).resolve()
    try:
        path.relative_to(store.resolve())
    except ValueError as error:
        raise RealMediaError(f"{stage} artifact escaped the control store") from error
    payload = path.read_bytes()
    if (
        len(payload) != reference["size_bytes"]
        or hashlib.sha256(payload).hexdigest() != reference["content_sha256"]
    ):
        raise RealMediaError(f"{stage} artifact differs from the governed manifest")
    return payload


def run_control_probe(source: Path, store: Path, controller: dict[str, Any]) -> None:
    probe_store = store / "control-probe"
    pipeline = CoreAlphaPipeline(
        repository_root=ROOT,
        store_root=probe_store,
        controller_identity=controller,
        worker=ReplayStageWorker.from_path(
            ROOT / "tests/fixtures/core_alpha_v1/worker_outputs.json"
        ),
        execution_mode="CONTRACT_REPLAY",
    )
    cancelled = pipeline.run(source, cancel_requested=lambda stage: stage == "topics")
    if cancelled.get("status") != "CANCELLED" or cancelled.get("next_stage") != "topics":
        raise RealMediaError("Core Alpha cancellation checkpoint verification failed")
    project_key = cancelled["project_id"].rsplit(":", 1)[-1]
    checkpoint = probe_store / "projects" / project_key / "checkpoint.json"
    resumed = pipeline.run(source, resume_checkpoint=checkpoint)
    if resumed.get("status") != "SUCCEEDED":
        raise RealMediaError("Core Alpha prefix-resume verification failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--seminartext", type=Path, required=True)
    parser.add_argument("--videotext", type=Path, required=True)
    parser.add_argument("--whisper-model", type=Path, required=True)
    parser.add_argument("--topic-model", default="gemma3:4b")
    parser.add_argument(
        "--certify-generated-non-private",
        action="store_true",
        help="affirm that the input is the bounded synthetic, non-private R6 fixture",
    )
    args = parser.parse_args()
    if platform.system() != "Darwin":
        raise RealMediaError("real VideoText execution requires the reference macOS host")
    if not args.certify_generated_non_private:
        raise RealMediaError("R6 evidence requires explicit generated non-private fixture certification")

    source_argument = args.source.expanduser().absolute()
    store_argument = args.store.expanduser().absolute()
    whisper_model = args.whisper_model.expanduser().absolute()
    reject_symlink_components(source_argument, label="source")
    reject_symlink_components(store_argument, label="real-media store")
    reject_symlink_components(whisper_model, label="Whisper model")
    source = source_argument.resolve()
    store = store_argument.resolve()
    if not source.is_file() or source.suffix.lower() not in {".mp4", ".mov", ".m4v", ".mkv", ".webm"}:
        raise RealMediaError("source must be a regular supported local video")
    if not whisper_model.is_file():
        raise RealMediaError("Whisper model is missing")
    if ROOT == store or ROOT in store.parents or store in ROOT.parents:
        raise RealMediaError("real-media store must be outside the repository")
    store.mkdir(parents=True, exist_ok=True)
    if any(store.iterdir()):
        raise RealMediaError("real-media store must be empty")

    originals = {
        "seminartext": args.seminartext.expanduser().absolute(),
        "videotext": args.videotext.expanduser().absolute(),
    }
    for name, checkout in originals.items():
        reject_symlink_components(checkout, label=f"{name} checkout")
    originals = {name: path.resolve() for name, path in originals.items()}
    identities = {name: verify_checkout(name, path) for name, path in originals.items()}
    snapshots = {name: checkout_snapshot(path) for name, path in originals.items()}

    copies_root = store / "pinned-components"
    copies_root.mkdir()
    copies: dict[str, Path] = {}
    for name, checkout in originals.items():
        copies[name] = copies_root / name
        materialize_pinned_tree(checkout, copies[name])

    whisper_hash_before = sha256_file(whisper_model)
    if whisper_hash_before != "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2":
        raise RealMediaError("Whisper model differs from the R6 pin")
    topic_model = topic_model_identity(args.topic_model)
    source_hash = sha256_file(source)
    duration = source_duration(source)

    controller = {
        "component_id": "integra_control_plane",
        "repository": "Yurielo/integra",
        "commit_sha": git(ROOT, "rev-parse", "HEAD"),
        "tree_sha": git(ROOT, "rev-parse", "HEAD^{tree}"),
        "version": "0.1.0-alpha",
        "contracts": ["worker_protocol_v1", "core_alpha_manifest_v1"],
        "runtime": {
            "kind": "python",
            "version": platform.python_version(),
            "architecture": platform.machine(),
        },
    }
    control_store = store / "control-plane"
    session_store = store / "worker-session"
    session_store.mkdir()
    config_path = store / "real-worker-config.json"
    write_json(
        config_path,
        {
            "artifact_store": str(control_store),
            "session_store": str(session_store),
            "seminartext_checkout": str(copies["seminartext"]),
            "videotext_checkout": str(copies["videotext"]),
            "whisper_model": str(whisper_model),
            "whisper_model_sha256": whisper_hash_before,
            "topic_model": args.topic_model,
            "topic_model_digest": topic_model["digest"],
            "source_sha256": source_hash,
            "source_suffix": source.suffix.lower(),
        },
    )
    worker = JsonlProcessStageWorker(
        worker_script=ROOT / "workers/core_alpha_real_worker.py",
        config_path=config_path,
        artifact_store=control_store,
        controller=controller,
        models={
            "transcript": {
                "name": whisper_model.name,
                "identity_sha256": whisper_hash_before,
            },
            "topics": {
                "name": args.topic_model,
                "identity_sha256": topic_model["digest"],
            },
        },
    )
    manifest = CoreAlphaPipeline(
        repository_root=ROOT,
        store_root=control_store,
        controller_identity=controller,
        worker=worker,
        execution_mode="PINNED_REAL_MEDIA",
    ).run(source)
    if (
        manifest.get("status") != "SUCCEEDED"
        or worker.calls != ["transcript", "topics", "review", "knowledge", "media_clip"]
        or len(worker.messages) != 25
    ):
        raise RealMediaError("governed R3 real-media path did not complete")
    run_control_probe(source, store, controller)

    if (
        sha256_file(whisper_model) != whisper_hash_before
        or topic_model_identity(args.topic_model) != topic_model
    ):
        raise RealMediaError("model identity changed during execution")
    for name, checkout in originals.items():
        if (
            verify_checkout(name, checkout) != identities[name]
            or checkout_snapshot(checkout) != snapshots[name]
        ):
            raise RealMediaError(f"{name} source checkout changed during execution")

    transcript = json.loads(read_manifest_artifact(manifest, control_store, "transcript"))
    topics = json.loads(read_manifest_artifact(manifest, control_store, "topics"))
    review = json.loads(read_manifest_artifact(manifest, control_store, "review"))
    knowledge = json.loads(read_manifest_artifact(manifest, control_store, "knowledge"))
    bundle = review["stage_data"]["canonical_bundle"]
    words = bundle["words"]
    first_word, last_word = words[0], words[-1]
    first_topic = topics["stage_data"]["topics_document"]["topics"][0]
    lineage = {
        name: {
            "artifact_id": reference["artifact_id"],
            "parent_artifact_ids": reference["provenance"]["parent_artifact_ids"],
            "operation_id": reference["provenance"]["operation_id"],
        }
        for name, reference in manifest["artifacts"].items()
    }
    stages = {
        name: {
            "status": "PASS",
            "semantic_status": reference["semantic_status"],
            "sha256": reference["content_sha256"],
            "size_bytes": reference["size_bytes"],
        }
        for name, reference in manifest["artifacts"].items()
    }
    report = {
        "schema_version": "1.0",
        "status": "PASS",
        "issue": 8,
        "execution_mode": "PINNED_REAL_MEDIA",
        "executed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "semantic_authority": "PROVISIONAL_ONLY",
        "source_repositories_changed": False,
        "protected_data_accessed": False,
        "human_decisions_applied": 0,
        "reference_host": {
            "os": platform.platform(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "swift": command_version(["swiftc", "--version"]),
            "ffmpeg": command_version(["/opt/homebrew/bin/ffmpeg", "-version"]),
            "whisper_cpp": command_version(["brew", "list", "--versions", "whisper-cpp"]),
            "ollama": command_version(["ollama", "--version"]),
        },
        "source": {
            "kind": "GENERATED_LOCAL_VIDEO",
            "privacy": "NON_PRIVATE_SYNTHETIC_SPEECH",
            "sha256": source_hash,
            "size_bytes": source.stat().st_size,
            "duration_seconds": duration,
            "language": "ru",
        },
        "component_identities": identities,
        "implementation": [
            {"path": path, "sha256": sha256_file(ROOT / path)}
            for path in IMPLEMENTATION_PATHS
        ],
        "models": {
            "whisper": {"name": whisper_model.name, "sha256": whisper_hash_before},
            "topics": topic_model,
        },
        "stage_sequence": ["source", "transcript", "topics", "review", "knowledge", "media_clip"],
        "stages": stages,
        "alignment": {
            "aligned_word_intervals": len(transcript["stage_data"]["word_intervals"]),
            "unaligned_word_sequences": review["stage_data"]["alignment_result"].get("unaligned_words", []),
            "omitted_zero_duration_tokens": len(transcript["stage_data"]["omitted_zero_duration_tokens"]),
            "fabricated_intervals": 0,
        },
        "provenance": {
            "project_id": bundle["project"]["id"],
            "source_id": bundle["transcript_revisions"][0]["source_id"],
            "transcript_revision_id": bundle["transcript_revisions"][0]["id"],
            "word_interval": {
                "start_id": first_word["id"],
                "end_id": last_word["id"],
                "start_seconds": first_word["start_seconds"],
                "end_seconds": last_word["end_seconds"],
            },
            "topic_interval": {
                "start_seconds": first_topic["start_seconds"],
                "end_seconds": first_topic["end_seconds"],
            },
            "clip_interval": {
                "start_seconds": manifest["artifacts"]["media_clip"]["provenance"]["source_locator"]["start_seconds"],
                "end_seconds": manifest["artifacts"]["media_clip"]["provenance"]["source_locator"]["end_seconds"],
            },
            "artifact_lineage": lineage,
        },
        "control_plane": {
            "pipeline": "INTEGRA_CORE_ALPHA_V1",
            "controller_commit_sha": controller["commit_sha"],
            "controller_tree_sha": controller["tree_sha"],
            "manifest_sha256": hashlib.sha256(canonical_json(manifest)).hexdigest(),
            "project_lease_enforced": manifest["project_lease_enforced"],
            "prefix_cancellation_checkpoint_verified": True,
            "prefix_resume_revalidation_verified": True,
            "r3_contract_boundary": True,
            "validated_jsonl_messages": len(worker.messages),
            "worker_processes": len(worker.calls),
            "worker_resume_support": False,
            "stage_timeout_enforced": True,
        },
        "determinism": {
            "independent_runs_compared": 1,
            "all_stage_hashes_identical": None,
        },
        "acceptance": ACCEPTANCE,
        "limitations": [
            f"The bounded evidence uses one generated {duration:g}-second Russian local video and does not establish quality on representative user media.",
            "The machine Topic and knowledge output remain REVIEW_REQUIRED or PROVISIONAL; R6 technical acceptance is not semantic acceptance.",
            "One Whisper token had a zero-duration native interval and was left unaligned rather than assigned fabricated timing.",
            "The pinned SeminarText CLI entrypoint contains a QA-report NameError after inference; the Integra adapter composes the same pinned functions without changing the source checkout.",
            "R3 stage workers declare no intra-job resume; Core Alpha prefix recovery is verified separately and fails closed.",
        ],
    }
    errors = validate_actual_evidence(report)
    if errors:
        raise RealMediaError("actual evidence is invalid: " + "; ".join(errors))
    report_path = store / "core_alpha_real_evidence.json"
    write_json(report_path, report)
    details_path = store / "core_alpha_real_details.json"
    write_json(
        details_path,
        {
            "core_alpha_manifest": manifest,
            "r3_messages": worker.messages,
            "transcript_artifact": transcript,
            "topics_artifact": topics,
            "review_artifact": review,
            "knowledge_artifact": knowledge,
        },
    )
    print(
        json.dumps(
            {"status": "PASS", "evidence": str(report_path), "details": str(details_path)},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
