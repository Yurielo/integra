#!/bin/bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
output="${1:?Output directory is required}"
checkout="${INTEGRA_VIDEOTEXT_BUILD_CHECKOUT:-$repo_root/.runtime-components/videotext-pinned}"
test "$(git -C "$checkout" rev-parse HEAD)" = "2e098d1705b6815628bee1e023f4742718eabf02"
test -z "$(git -C "$checkout" status --porcelain -- Sources)"
test "$(shasum -a 256 "$checkout/Sources/videotext/Services/SRTService.swift" | awk '{print $1}')" = "417017a6a3becc395e88e2554e8d7c2dca51b09de9743e8c5c0cf81ac9ba6205"
mkdir -p "$output"
xcrun swiftc -parse-as-library -O -framework SwiftUI -framework AppKit -framework AVKit -framework AVFoundation -framework UserNotifications \
  -o "$output/translation-worker" $(find "$checkout/Sources/videotext" -name '*.swift' ! -path '*/App/*' ! -path '*/UI/*' | sort) \
  "$repo_root/workers/videotext_translation_worker.swift"
python3 - "$output" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
identity = {
    "component": "videotext", "commit_sha": "2e098d1705b6815628bee1e023f4742718eabf02",
    "translation_adapter_sha256": "83e55d3cb82522cb431ee20617510b0c39f79ae0fa5309daedf5c7ff9911a577",
    "srt_service_sha256": "417017a6a3becc395e88e2554e8d7c2dca51b09de9743e8c5c0cf81ac9ba6205",
    "worker_sha256": hashlib.sha256((root / "translation-worker").read_bytes()).hexdigest(),
    "personal_use_only": True,
}
(root / "runtime.json").write_text(json.dumps(identity, sort_keys=True) + "\n", encoding="utf-8")
PY
