"""Package the separately accepted exact source-owned K2 admission contract."""
from pathlib import Path
import json
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integra_core.knowledge_admission_runtime import preflight


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


if __name__ == "__main__":
    main()
