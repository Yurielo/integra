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


def _with_packaged_review_runtime(resources):
    """Expose the already-packaged review dependencies to K2 preflight.

    K2 admission and K1 review intentionally share the same pinned
    ``jsonschema`` closure.  During assembly that closure exists only under
    the fresh app Resources tree, not under the source checkout.  Binding it
    for the packaging preflight preserves the normal runtime lookup without
    copying or relaxing either contract.
    """
    site_packages = resources / "runtime/review-python/site-packages"
    if not site_packages.is_dir():
        raise ValueError("packaged review runtime is unavailable")
    previous = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(site_packages) + (os.pathsep + previous if previous else "")
    return previous


def main():
    resources = Path(sys.argv[1])
    previous_pythonpath = _with_packaged_review_runtime(resources)
    try:
        pin = preflight()
    finally:
        if previous_pythonpath is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = previous_pythonpath
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
