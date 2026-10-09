"""Package the separately accepted exact source-owned K2 admission contract."""
from pathlib import Path
import json
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integra_core.knowledge_admission_runtime import preflight


def package_view_schema(resources):
    """Include the governed read-projection schema at its packaged lookup path."""
    destination = resources / "schemas/knowledge_view_v1.schema.json"
    if destination.exists() or destination.is_symlink():
        raise ValueError("Knowledge view schema requires a fresh owned destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "schemas/knowledge_view_v1.schema.json", destination)


def main():
    resources = Path(sys.argv[1])
    pin = preflight()
    source = Path(pin["runtime"])
    destination = resources / "runtime/knowledge-admission"
    if destination.exists():
        raise ValueError("admission packaging requires a fresh owned destination")
    for relative in pin["files"]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    exact = {key: value for key, value in pin.items() if key not in {"state", "runtime", "origin"}}
    (destination / "runtime.json").write_text(json.dumps(exact, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    package_view_schema(resources)


if __name__ == "__main__":
    main()
