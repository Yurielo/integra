"""Verify the bundled AppKit library list and detail on synthetic manifests."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_seminar_library import SeminarLibraryTests


def main():
    app, root = map(lambda value: Path(value).resolve(), sys.argv[1:])
    root.mkdir(parents=True, exist_ok=False)
    fixture = SeminarLibraryTests("test_multi_product_read_only_deterministic_preview")
    fixture.setUp()
    try:
        specs = fixture.fixtures()
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in fixture.root.rglob("*") if path.is_file() and not path.is_symlink()}
        rows = [{"owner": owner, "path": str(path)} for owner, path in specs]
        for screen in ("list", "detail"):
            marker, screenshot = root / f"{screen}.json", root / f"{screen}.png"
            app_data = root / f"{screen}-app-data"
            environment = {key: value for key, value in os.environ.items() if not key.startswith("INTEGRA_")}
            environment.update(INTEGRA_APP_DATA_ROOT=str(app_data),
                               INTEGRA_LIBRARY_PROBE_MANIFESTS=json.dumps(rows),
                               INTEGRA_LIBRARY_PROBE_RESULT=str(marker),
                               INTEGRA_UI_SNAPSHOT=str(screenshot), PYTHONDONTWRITEBYTECODE="1")
            process = subprocess.Popen([str(app / "Contents/MacOS/Integra"), f"--ui-probe-library-{screen}"],
                                       env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if marker.is_file() and screenshot.is_file() and screenshot.stat().st_size > 1000:
                        break
                    if process.poll() is not None:
                        raise AssertionError(f"native library process exited: {process.stderr.read().decode()}")
                    time.sleep(.1)
                else:
                    raise AssertionError(f"native {screen} view did not render")
                # The initial empty sidebar state may have queued its own screenshot.
                time.sleep(.7)
                result = json.loads(marker.read_bytes())
                assert result["screen"] == screen and result["project_count"] == 4, result
                assert result["source_count"] == 7 and result["artifact_count"] == 4, result
                assert screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), screenshot
                assert not app_data.exists(), "library preview created an application data directory"
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)
        assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}
        print("INTEGRA_NATIVE_SEMINAR_LIBRARY_PROJECT_DETAIL: PASS", flush=True)
    finally:
        fixture.tearDown()


if __name__ == "__main__":
    main()
