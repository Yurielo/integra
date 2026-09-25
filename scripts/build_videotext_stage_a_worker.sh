#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
output="${1:?Output directory is required}"
checkout="${INTEGRA_VIDEOTEXT_STAGE_A_CHECKOUT:?Set INTEGRA_VIDEOTEXT_STAGE_A_CHECKOUT to the clean VideoText checkout}"
commit="c4d851c9b39b2aeb696a12aa357d1ae0df350cd3"

test -d "$checkout/.git"
test "$(git -C "$checkout" rev-parse HEAD)" = "$commit"
test -z "$(git -C "$checkout" status --porcelain --untracked-files=all)"
test "$(shasum -a 256 "$checkout/Sources/videotext/Adapters/SegmentedWhisperTranscriber.swift" | awk '{print $1}')" = "81a3c551e4aeb622c636213e011aaec980c43a24f301781691d79c0d8dfd65e3"
test "$(shasum -a 256 "$checkout/Sources/videotext/Services/TranscriptionQualityService.swift" | awk '{print $1}')" = "ee6ccf1c604cfd057bdf97314e1c2f05497e8b5f638d29adc3baf828ec69f5a0"

mkdir -p "$output"
xcrun swiftc -parse-as-library -O -framework SwiftUI -framework AppKit -framework AVKit -framework AVFoundation -framework UserNotifications \
  -o "$output/videotext-stage-a-worker" \
  $(find "$checkout/Sources/videotext" -name '*.swift' ! -path '*/App/*' ! -path '*/UI/*' | sort) \
  "$repo_root/workers/videotext_stage_a_transcript_worker.swift"
python3 - "$output" "$commit" <<'PY'
import hashlib, json, sys
from pathlib import Path
root, commit = Path(sys.argv[1]), sys.argv[2]
tracked = {
    "segmented_whisper_transcriber_sha256": "81a3c551e4aeb622c636213e011aaec980c43a24f301781691d79c0d8dfd65e3",
    "transcription_quality_service_sha256": "ee6ccf1c604cfd057bdf97314e1c2f05497e8b5f638d29adc3baf828ec69f5a0",
}
worker = root / "videotext-stage-a-worker"
identity = {"schema_version": "1.0", "component": "videotext", "commit_sha": commit,
            "capability": "stage_a_transcript", "seminartext_dependency": False,
            "worker_sha256": hashlib.sha256(worker.read_bytes()).hexdigest(), **tracked}
(root / "runtime.json").write_text(json.dumps(identity, sort_keys=True) + "\n", encoding="utf-8")
PY
