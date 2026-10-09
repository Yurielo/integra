#!/bin/bash
set -euo pipefail
trap 'printf "INTEGRA_MACOS_BUILD: FAIL at line %s\n" "$LINENO" >&2' ERR

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
output_root="${1:-$repo_root/build}"
app="$output_root/Integra.app"
python3 - "$output_root" <<'PY'
"""Reject accidental full-size candidates in unowned temporary directories."""
import json
import os
from pathlib import Path
import sys
import tempfile

output = Path(sys.argv[1]).expanduser().resolve()
temporary = {Path("/private/tmp"), Path("/tmp"), Path(tempfile.gettempdir())}
for key in ("TMPDIR", "TMP", "TEMP"):
    if os.environ.get(key):
        temporary.add(Path(os.environ[key]).resolve())

def within(path, root):
    try:
        path.relative_to(root.resolve())
        return True
    except ValueError:
        return False

if any(within(output, root) for root in temporary):
    for ancestor in (output, *output.parents):
        marker = ancestor / ".integra-owned-workspace.json"
        if not marker.is_file() or marker.is_symlink():
            continue
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if value.get("artifact_type") == "integra.disposable_workspace" and value.get("root") == str(ancestor.resolve()):
            break
    else:
        raise SystemExit("refusing to materialize Integra.app in an unowned temporary directory; use scripts/temp_workspace_lifecycle.py or a durable output root")
PY
python3 - "$repo_root" "$output_root" <<'PY'
import os
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from scripts.candidate_retention import require_build_lease
try:
    require_build_lease(Path(os.environ.get('INTEGRA_RETENTION_ARCHIVE_ROOT',
        str(Path.home() / 'Library/Application Support/Integra/Build Archive'))), output=Path(sys.argv[2]))
except (OSError, ValueError) as error:
    raise SystemExit(str(error))
PY
seminartext_checkout="${INTEGRA_SEMINARTEXT_BUILD_CHECKOUT:-$repo_root/.runtime-components/seminartext-pinned}"
seminartext_commit="13644d262776aacdf36221b9a9fc7ebd0a7c0737"
seminartext_cli_sha256="30d8c1bd6f5ca717391b168cba71228a030009feaec4eb443bb1e76dab230a6c"
seminartext_version_sha256="e1d49c569ae09b2ede16e2d83820a3809b35eb6c44c13ba9b5330598d6b8f43c"
seminartext_module="$seminartext_checkout/seminartext_modules/seminartext_topics.py"
seminartext_sha256="d8a14e83b877024c3e016a33e594af17d512741a77735ff3d8c7d1262628c8db"
seminartext_evidence_module="$seminartext_checkout/seminartext_modules/evidence_foundation.py"
seminartext_evidence_sha256="6adcf15e9767c36ad2d0dfe3a6a995d90c41b5f1671b4c9434a4b48f590e3856"
seminartext_evidence_validator="$seminartext_checkout/schemas/validate_canonical_evidence_v1.py"
seminartext_evidence_validator_sha256="889e6cdf3dc2dd7504f76923c04e2d8d1eceabdb828d0c110ddc1059b107860e"
alignment_packages="${INTEGRA_WORD_ALIGNMENT_SITE_PACKAGES:-$repo_root/.runtime-word-alignment/lib/python3.13/site-packages}"
alignment_model="${INTEGRA_WORD_ALIGNMENT_MODEL_DIR:-/Users/yurielokhin/.cache/huggingface/hub/models--jonatasgrosman--wav2vec2-large-xlsr-53-russian/snapshots/2329100508896c6d9b157019803ab5601e6f3406}"
alignment_python="${INTEGRA_WORD_ALIGNMENT_PYTHON:-/opt/homebrew/opt/python@3.13/bin/python3.13}"
alignment_sha256="d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c"
videotext_checkout="${INTEGRA_VIDEOTEXT_BUILD_CHECKOUT:-$repo_root/.runtime-components/videotext-pinned}"
videotext_commit="2e098d1705b6815628bee1e023f4742718eabf02"
booktext_checkout="${INTEGRA_BOOKTEXT_BUILD_CHECKOUT:-$repo_root/.runtime-components/booktext-pinned}"
booktext_commit="46396649214275eb18054b670a842bace02d02e1"
booktext_entrypoint="$booktext_checkout/booktext.py"
booktext_entrypoint_sha256="32ecbb3f9a46e0648f4f701a3935487d0be91799334b27128161a51a1f99f05f"
booktext_vision="$booktext_checkout/vision/VisionOCR.swift"
booktext_vision_sha256="3b5a25577a58713cb4cb3a7e81d3883bdf822ce9df6ef0aa4b60d56186e92753"

test "$(git -C "$seminartext_checkout" rev-parse HEAD)" = "$seminartext_commit"
test "$(shasum -a 256 "$seminartext_checkout/seminartext" | awk '{print $1}')" = "$seminartext_cli_sha256"
test "$(shasum -a 256 "$seminartext_checkout/SEMINARTEXT_VERSION" | awk '{print $1}')" = "$seminartext_version_sha256"
test -f "$seminartext_module"
test "$(shasum -a 256 "$seminartext_module" | awk '{print $1}')" = "$seminartext_sha256"
test -f "$seminartext_evidence_module"
test "$(shasum -a 256 "$seminartext_evidence_module" | awk '{print $1}')" = "$seminartext_evidence_sha256"
test -f "$seminartext_evidence_validator"
test "$(shasum -a 256 "$seminartext_evidence_validator" | awk '{print $1}')" = "$seminartext_evidence_validator_sha256"
test -d "$alignment_packages/whisperx"
test -f "$alignment_model/pytorch_model.bin"
test "$(shasum -a 256 "$alignment_model/pytorch_model.bin" | awk '{print $1}')" = "$alignment_sha256"
test -x "$alignment_python"
"$alignment_python" --version | grep -q '^Python 3.13\.'
test "$(git -C "$videotext_checkout" rev-parse HEAD)" = "$videotext_commit"
test "$(git -C "$booktext_checkout" rev-parse HEAD)" = "$booktext_commit"
test -f "$booktext_entrypoint"
test "$(shasum -a 256 "$booktext_entrypoint" | awk '{print $1}')" = "$booktext_entrypoint_sha256"
test -f "$booktext_vision"
test "$(shasum -a 256 "$booktext_vision" | awk '{print $1}')" = "$booktext_vision_sha256"

rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
xcrun swiftc -parse-as-library -O -framework AppKit -framework AVKit -framework AVFoundation \
  "$repo_root/macos/IntegraApp.swift" -o "$app/Contents/MacOS/Integra"
cp "$repo_root/macos/Info.plist" "$app/Contents/Info.plist"
cp "$repo_root/macos/Resources/Integra.icns" "$app/Contents/Resources/Integra.icns"
cp "$repo_root/macos/Resources/bridge.py" "$app/Contents/Resources/bridge.py"
cp "$repo_root/macos/Resources/source_first_workflow.json" "$app/Contents/Resources/source_first_workflow.json"
cp "$repo_root/macos/Resources/deferred_features.json" "$app/Contents/Resources/deferred_features.json"
mkdir -p "$app/Contents/Resources/workers"
cp "$repo_root/workers/seminartext_topics_worker.py" "$app/Contents/Resources/workers/seminartext_topics_worker.py"
cp "$repo_root/workers/seminartext_word_alignment_worker.py" "$app/Contents/Resources/workers/seminartext_word_alignment_worker.py"
cp "$repo_root/workers/videotext_translation_worker.swift" "$app/Contents/Resources/workers/videotext_translation_worker.swift"
cp "$repo_root/workers/videotext_media_worker.swift" "$app/Contents/Resources/workers/videotext_media_worker.swift"
cp "$repo_root/workers/booktext_ocr_worker.py" "$app/Contents/Resources/workers/booktext_ocr_worker.py"
mkdir -p "$app/Contents/Resources/runtime/videotext"
bash "$repo_root/scripts/build_videotext_worker.sh" "$app/Contents/Resources/runtime/videotext"
mkdir -p "$app/Contents/Resources/runtime/booktext"
cp "$booktext_entrypoint" "$app/Contents/Resources/runtime/booktext/booktext.py"
xcrun swiftc -parse-as-library -O -framework Vision "$booktext_vision" -o "$app/Contents/Resources/runtime/booktext/visionocr"
printf '{"component":"booktext","commit_sha":"%s","entrypoint_sha256":"%s","vision_sha256":"%s","personal_use_only":true}\n' "$booktext_commit" "$booktext_entrypoint_sha256" "$booktext_vision_sha256" > "$app/Contents/Resources/runtime/booktext/runtime.json"
mkdir -p "$app/Contents/Resources/runtime/seminartext/seminartext_modules"
cp "$seminartext_checkout/seminartext" "$app/Contents/Resources/runtime/seminartext/seminartext"
cp "$seminartext_checkout/SEMINARTEXT_VERSION" "$app/Contents/Resources/runtime/seminartext/SEMINARTEXT_VERSION"
cp "$seminartext_module" "$app/Contents/Resources/runtime/seminartext/seminartext_modules/seminartext_topics.py"
cp "$seminartext_evidence_module" "$app/Contents/Resources/runtime/seminartext/seminartext_modules/evidence_foundation.py"
mkdir -p "$app/Contents/Resources/runtime/seminartext/schemas"
cp "$seminartext_evidence_validator" "$app/Contents/Resources/runtime/seminartext/schemas/validate_canonical_evidence_v1.py"
# This script's stdout is the sole machine-readable app path. Keep packaging
# diagnostics on stderr so callers can safely capture that path.
python3 "$repo_root/scripts/package_review_runtime.py" "$seminartext_checkout" "$app/Contents/Resources" >&2
python3 "$repo_root/scripts/package_knowledge_admission_runtime.py" "$app/Contents/Resources" >&2
printf '{"component":"seminartext","commit_sha":"%s","entrypoint_sha256":"%s","evidence_foundation_sha256":"%s","evidence_validator_sha256":"%s","personal_use_only":true}\n' "$seminartext_commit" "$seminartext_cli_sha256" "$seminartext_evidence_sha256" "$seminartext_evidence_validator_sha256" > "$app/Contents/Resources/runtime/seminartext/runtime.json"
mkdir -p "$app/Contents/Resources/runtime/word-alignment/site-packages" "$app/Contents/Resources/runtime/word-alignment/model"
rsync -aL --exclude '__pycache__' --exclude '*.pyc' "$alignment_packages/" "$app/Contents/Resources/runtime/word-alignment/site-packages/"
rsync -aL "$alignment_model/" "$app/Contents/Resources/runtime/word-alignment/model/"
printf '{"component":"seminartext","capability":"word_timeline","model_revision":"2329100508896c6d9b157019803ab5601e6f3406","weights_sha256":"%s","personal_use_only":true}\n' "$alignment_sha256" > "$app/Contents/Resources/runtime/word-alignment/runtime.json"
rsync -a --exclude '__pycache__' --exclude '*.pyc' "$repo_root/integra_core/" "$app/Contents/Resources/integra_core/"
chmod 755 "$app/Contents/MacOS/Integra" "$app/Contents/Resources/bridge.py" "$app/Contents/Resources/workers/seminartext_topics_worker.py" "$app/Contents/Resources/workers/seminartext_word_alignment_worker.py" "$app/Contents/Resources/workers/booktext_ocr_worker.py" "$app/Contents/Resources/runtime/videotext/translation-worker" "$app/Contents/Resources/runtime/booktext/visionocr"
python3 "$repo_root/scripts/candidate_manifest.py" generate --app "$app" --source-root "$repo_root" --word-python "$alignment_python" >/dev/null
plutil -lint "$app/Contents/Info.plist" >/dev/null
echo "$app"
