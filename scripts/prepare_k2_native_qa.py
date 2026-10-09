"""Prepare an isolated native QA copy of the existing generated speech demo.

Test decisions apply ONLY inside the fresh QA copy. They are not Product Owner
semantic decisions and do not change the original Process project or CURRENT.
No provider, media processing, or model is invoked.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid


PROJECT_UUID = "c0b7a120-c257-4514-b077-7b6a6fce0c15"
IDENTITY = {
    "project_id": "urn:integra:project:" + PROJECT_UUID,
    "source_id": "urn:integra:source:f8f2239a-599c-5f4a-98de-ae7f60436efa",
    "run_id": "urn:integra:run:e95bfc37-7134-4ad5-b675-93de9cf8bf4c",
}


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("QA source copy must contain no symlinks")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    args = parser.parse_args()
    managed = Path.home() / "Library/Application Support/Integra"
    original = managed / "projects" / PROJECT_UUID
    project = json.loads((original / "project.json").read_bytes())
    if project.get("name") != "generated-russian-speech.mp4" or project.get("project_id") != IDENTITY["project_id"]:
        raise ValueError("only the known generated speech demo is permitted")
    before = inventory(original)
    qa = managed / "Validation" / ("k2-native-" + str(uuid.uuid4()))
    destination = qa / "projects" / PROJECT_UUID
    destination.parent.mkdir(parents=True, exist_ok=False)
    shutil.copytree(original, destination)
    resources = args.app.resolve(strict=True) / "Contents/Resources"
    manifest = json.loads((resources / "candidate-manifest.json").read_bytes())
    environment = dict(os.environ, INTEGRA_APP_DATA_ROOT=str(qa), PYTHONDONTWRITEBYTECODE="1")
    for name in ("INTEGRA_SEMINARTEXT_CHECKOUT", "INTEGRA_KNOWLEDGE_ADMISSION_CHECKOUT", "PYTHONPATH"):
        environment.pop(name, None)

    def bridge(operation, request):
        output = subprocess.run(["/usr/bin/python3", str(resources / "bridge.py"), operation],
                                input=json.dumps(request), text=True, capture_output=True,
                                env=environment, check=True, timeout=180)
        value = json.loads(output.stdout)
        if not value.get("ok"):
            raise ValueError(value)
        return value["result"]

    opened = bridge("knowledge-open", dict(IDENTITY, create=True))
    decisions = [{"topic_id": item["id"], "action": "ACCEPT",
                  "reason": "ISOLATED SYNTHETIC QA CHOICE over generated demo; not human product semantic acceptance"}
                 for item in opened["topics"]]
    reviewed = bridge("knowledge-save", dict(IDENTITY, expected_state_sha256=opened["state_sha256"],
                      decisions=decisions, reviewer_id="synthetic-qa-k1-reviewer"))
    if reviewed["status"] != "REVIEWED_FRAGMENTS_V2" or inventory(original) != before:
        raise ValueError("QA preparation failed or original project changed")
    receipt = {"qa_only": True, "real_generated_media": True, "semantic_product_acceptance": False,
               "upstream_processing": False, "original_unchanged": True, "original_inventory": before,
               "data_root": str(qa), "candidate_id": manifest["candidate_id"], "identity": IDENTITY,
               "notebook": reviewed}
    (qa / "qa-setup.json").write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({key: value for key, value in receipt.items() if key not in {"notebook", "original_inventory"}}, sort_keys=True))


if __name__ == "__main__":
    main()
