"""Exact SeminarText-owned K2 contract, isolated from the existing Process pin.

The bridge uses the already-supported review Python. Canonical creation and
validation execute in the pinned source product, never an Integra compiler.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from contextlib import contextmanager

from .seminartext_topic_review_runtime import _environment, _python

PIN_PATH = Path(__file__).resolve().parents[1] / "state/knowledge_admission_component_v1.json"
BUNDLED_RUNTIME_ROOT = Path(__file__).resolve().parents[1] / "runtime/knowledge-admission"


def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _pin():
    path = PIN_PATH if PIN_PATH.is_file() else BUNDLED_RUNTIME_ROOT / "runtime.json"
    if path.is_symlink():
        raise ValueError("unsafe Knowledge admission pin")
    pin = json.loads(path.read_bytes())
    if digest(pin) != "a745b5d17bb2c99eec489a43026c25f97a04dc919414b40d1bf17243883e719e":
        raise ValueError("Knowledge admission governed pin digest changed")
    if pin.get("component") != "seminartext" or pin.get("capability") != "reviewed_knowledge_admission":
        raise ValueError("wrong Knowledge admission component")
    if pin.get("commit_sha") != "61ee27de67174377afa0f4955b3cb5abeecb4f03" or pin.get("tree_sha") != "066a4029d791585410afd0aa45de974638b5e1ff":
        raise ValueError("Knowledge admission pin is not the accepted source revision")
    return pin


def preflight():
    pin = _pin()
    configured = os.environ.get("INTEGRA_KNOWLEDGE_ADMISSION_CHECKOUT")
    runtime = Path(configured) if configured else BUNDLED_RUNTIME_ROOT
    if runtime.is_symlink() or not runtime.is_dir():
        raise ValueError("Knowledge admission runtime unavailable")
    runtime = runtime.resolve(strict=True)
    if configured:
        for ref, key in (("HEAD", "commit_sha"), ("HEAD^{tree}", "tree_sha")):
            value = subprocess.run(["git", "-C", str(runtime), "rev-parse", ref], check=True,
                                   capture_output=True, text=True, timeout=10).stdout.strip()
            if value != pin[key]:
                raise ValueError("Knowledge admission source differs from exact accepted pin")
    else:
        if json.loads((runtime / "runtime.json").read_bytes()) != pin:
            raise ValueError("Knowledge admission runtime pin changed")
    for relative, expected in pin["files"].items():
        path = runtime / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(runtime):
            raise ValueError("unsafe Knowledge admission source file")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Knowledge admission runtime bytes differ: " + relative)
    for directory in ("schemas", "seminartext_modules"):
        if (runtime / directory / "__init__.py").exists():
            raise ValueError("unbound admission package initialization code")
    check = subprocess.run([_python(), "-c", "import jsonschema"], env=_environment(),
                           capture_output=True, text=True, timeout=15)
    if check.returncode:
        raise ValueError("Knowledge admission requires the supported review runtime")
    return {**pin, "state": "READY", "runtime": str(runtime),
            "origin": "EXTERNAL_PINNED_CHECKOUT" if configured else "BUNDLED_PINNED_RUNTIME"}


_RUNNER = '''import json,sys
sys.path.insert(0, sys.argv[1])
from seminartext_modules import reviewed_knowledge_admission as owner
request=json.load(sys.stdin)
operation=request['operation']; args=request['arguments']
if operation == 'compile_revision':
    result=owner.compile_revision(args['bundle'].encode('utf-8'),args['reviewed'].encode('utf-8'),args['package'],args['decisions'],parent=args.get('parent'))
elif operation == 'validate_revision':
    owner.validate_revision(args['revision'],args['bundle'].encode('utf-8')); result=None
elif operation == 'persist_revision':
    owner.persist_revision(args['destination'],args['revision']); result=None
else: raise ValueError('unsupported admission operation')
print(json.dumps(result,ensure_ascii=False))
'''


@contextmanager
def exact_owner_snapshot():
    """Execute only the hash-verified closure, never unbound checkout files."""
    pin = preflight()
    with tempfile.TemporaryDirectory(prefix="integra-knowledge-owner-") as directory:
        snapshot = Path(directory)
        for relative, expected in pin["files"].items():
            payload = (Path(pin["runtime"]) / relative).read_bytes()
            if hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError("Knowledge admission source changed while snapshotting")
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        yield snapshot


class _Owner:
    def __init__(self):
        pin = preflight()
        self.CONTRACT_ID = pin["contract"]["id"]
        self.CONTRACT_SHA256 = pin["contract"]["sha256"]

    canonical_bytes = staticmethod(canonical_bytes)
    digest = staticmethod(digest)

    def _call(self, operation, **arguments):
        # Never put an entire source checkout on sys.path: an unbound dependency
        # shadow or bytecode file could execute even with all pinned .py hashes
        # intact. Copy only verified import-closure bytes to a fresh namespace.
        with exact_owner_snapshot() as snapshot:
            result = subprocess.run([_python(), "-c", _RUNNER, str(snapshot)],
                                    input=json.dumps({"operation": operation, "arguments": arguments}, ensure_ascii=False),
                                    capture_output=True, text=True, timeout=120, env=_environment())
        if result.returncode:
            raise ValueError((result.stderr or "SeminarText admission failed").strip()[-1000:])
        return json.loads(result.stdout)

    def compile_revision(self, bundle_payload, reviewed_payload, package, decisions, *, parent=None):
        return self._call("compile_revision", bundle=bundle_payload.decode("utf-8"),
                          reviewed=reviewed_payload.decode("utf-8"), package=package, decisions=decisions, parent=parent)

    def validate_revision(self, revision, bundle_payload):
        return self._call("validate_revision", revision=revision, bundle=bundle_payload.decode("utf-8"))

    def persist_revision(self, destination, revision):
        return self._call("persist_revision", destination=str(destination), revision=revision)


def owner():
    return _Owner()
