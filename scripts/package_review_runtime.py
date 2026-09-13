"""Package pinned review contracts and offline hash-locked dependencies."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

FILES = {
    "seminartext_modules/human_review_workflow.py": "7187819a19360fe023c9ddcc3a723ca638a1b1b74769c02c41829cd344da72dc",
    "seminartext_modules/project_knowledge_bridge.py": "39bc3191cbfa07e32b9a2526ede428289fd020e93f9bd13539321ebb39165a5f",
    "schemas/validate_canonical_knowledge_v1.py": "14869b0d77bed839758afb0455cffcfcba4173495554eddd9159a02309f1c095",
    "schemas/canonical_knowledge_v1.schema.json": "33691770411b4e5fc4e923920619396f7281bcd655202f8f56ddba99b844111b",
    "schemas/canonical_knowledge_lifecycle_v1.json": "c9133fe6ff630dd44475f40d37d731f407ce2f79d1d15613454a1d5c179099bc",
    "schemas/topic_review_workflow_v1.schema.json": "c4ad9201ee217d5d311397cea6daef8d6e6bc75c88e9c7d3ec0d129190bacec1",
    "schemas/topic_review_workflow_v2.schema.json": "7dede105b8339f46c100c8bed07ad93ace01811e8c26d3a27d204cd6692012b0",
    "schemas/project_knowledge_input_v1.schema.json": "bd9a77e8f99f7a53de8daf9c4c697b049f4f28b10ee6b2e3e00fbd85584cb58b",
    "schemas/canonical_evidence_v1.schema.json": "08bab4381ba435a059a1b58ea5dbedadd57112a18421ea7ef84a10ddb52d44b8",
}


def main():
    checkout, resources = map(Path, sys.argv[1:])
    root = Path(__file__).resolve().parents[1]
    if sys.version_info[:2] != (3, 14):
        raise SystemExit("Review runtime packaging requires Python 3.14")
    for relative, expected in FILES.items():
        source = checkout / relative
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise SystemExit(f"Pinned review component mismatch: {relative}")
        target = resources / "runtime/seminartext" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    target = resources / "runtime/review-python/site-packages"
    wheels = Path(os.environ.get("INTEGRA_REVIEW_WHEELS", root / ".runtime-components/review-wheels"))
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "--no-compile",
        "--no-deps", "--require-hashes", "--only-binary=:all:", "--find-links", str(wheels),
        "--target", str(target), "-r", str(root / "scripts/review-runtime-requirements.txt")],
        check=True, stdout=sys.stderr)
    subprocess.run([sys.executable, "-c", "import jsonschema; from jsonschema import Draft202012Validator; Draft202012Validator({}).validate({})"],
        env={**os.environ, "PYTHONPATH": str(target), "PYTHONDONTWRITEBYTECODE": "1"}, check=True)


if __name__ == "__main__":
    main()
