"""Private, fixed implementation provider for the isolated Process pilot."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import time

from .candidate_identity import validate_bundle
from .shutdown_runtime import terminate_owned_subprocess_tree

COMMIT = "2e098d1705b6815628bee1e023f4742718eabf02"
SERVICE_HASH = "417017a6a3becc395e88e2554e8d7c2dca51b09de9743e8c5c0cf81ac9ba6205"


class PilotFailure(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def preflight(resources):
    resources = Path(resources)
    if resources.is_symlink() or not resources.is_dir():
        raise PilotFailure("RUNTIME_UNAVAILABLE")
    try:
        candidate = validate_bundle(resources.parent.parent)
        runtime_root = resources / "runtime/videotext"
        worker = runtime_root / "translation-worker"
        manifest = runtime_root / "runtime.json"
        identity = json.loads(manifest.read_bytes())
        declared = candidate["identity"]["components"]["videotext"]
        if (runtime_root.is_symlink() or worker.is_symlink() or manifest.is_symlink()
                or not os.access(worker, os.X_OK) or identity != declared
                or identity.get("component") != "videotext"
                or identity.get("commit_sha") != COMMIT
                or identity.get("srt_service_sha256") != SERVICE_HASH
                or identity.get("worker_sha256") != digest(worker)):
            raise ValueError("identity")
        return {"executor_id": "integra.timed-transcript-normalizer.v1",
                "provider": "videotext", "provider_commit": COMMIT,
                "service_sha256": SERVICE_HASH, "worker_sha256": digest(worker),
                "worker": str(worker.resolve()), "runtime_manifest_sha256": digest(manifest),
                "candidate_id": candidate["candidate_id"],
                "bundle_digest": candidate["bundle"]["digest"]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise PilotFailure("RUNTIME_IDENTITY_MISMATCH") from error


def run(runtime, source, target, *, cancelled, timeout_seconds, max_output_bytes):
    worker = Path(runtime["worker"])
    if worker.is_symlink() or digest(worker) != runtime["worker_sha256"]:
        raise PilotFailure("RUNTIME_IDENTITY_MISMATCH")
    request_path = target.parent / "provider-request.json"
    request_path.write_text(json.dumps({"schema_version": "1.0", "operation": "normalize",
        "input_srt": str(source.resolve()), "output_srt": str(target.resolve())}), encoding="utf-8")
    process = None
    output = bytearray()
    started = time.monotonic()
    with selectors.DefaultSelector() as selector:
        try:
            if cancelled():
                raise PilotFailure("CANCELLED")
            process = subprocess.Popen([str(worker), "--subtitle-request", str(request_path)],
                cwd=target.parent, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, start_new_session=True,
                env={"PATH": "/usr/bin:/bin", "HOME": str(target.parent), "LC_ALL": "C"})
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                if cancelled():
                    raise PilotFailure("CANCELLED")
                if time.monotonic() - started >= timeout_seconds:
                    raise PilotFailure("TIMED_OUT")
                if target.exists() and target.stat().st_size > max_output_bytes:
                    raise PilotFailure("OUTPUT_LIMIT")
                for key, _ in selector.select(.02):
                    block = os.read(key.fileobj.fileno(), min(8192, max_output_bytes + 1))
                    if not block:
                        selector.unregister(key.fileobj)
                    else:
                        output.extend(block)
                        if len(output) > max_output_bytes:
                            raise PilotFailure("OUTPUT_LIMIT")
            while process.poll() is None:
                if cancelled():
                    raise PilotFailure("CANCELLED")
                if time.monotonic() - started >= timeout_seconds:
                    raise PilotFailure("TIMED_OUT")
                time.sleep(.01)
            if process.returncode:
                raise PilotFailure("PROVIDER_FAILED")
            if digest(worker) != runtime["worker_sha256"]:
                raise PilotFailure("RUNTIME_IDENTITY_MISMATCH")
            try:
                result = json.loads(output)
            except (ValueError, UnicodeError) as error:
                raise PilotFailure("INVALID_PROVIDER_RESULT") from error
            required = {"schema_version", "component", "capability", "operation", "cue_count",
                        "output_srt", "skipped_zero_duration_count", "warnings"}
            if (not isinstance(result, dict) or set(result) != required
                    or result["schema_version"] != "1.0" or result["component"] != "videotext"
                    or result["capability"] != "subtitles" or result["operation"] != "normalize"
                    or type(result["cue_count"]) is not int or result["cue_count"] <= 0
                    or result["output_srt"] != str(target.resolve())
                    or type(result["skipped_zero_duration_count"]) is not int
                    or result["skipped_zero_duration_count"] != 0 or result["warnings"] != []):
                raise PilotFailure("INVALID_PROVIDER_RESULT")
            return result
        finally:
            if process is not None:
                try:
                    if process.poll() is None:
                        terminate_owned_subprocess_tree(process.pid)
                        process.wait(timeout=5)
                finally:
                    process.stdout.close()
