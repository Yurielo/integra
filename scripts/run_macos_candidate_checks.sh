#!/bin/bash
# Ephemeral build + native identity checks.  The complete scratch root is
# marker-owned and removed on completion, failure, SIGINT, or SIGTERM.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
exec "$repo_root/scripts/with_temp_artifact_root.sh" --purpose macos-candidate-check -- bash -c '
  set -euo pipefail
  app="$("$1/scripts/build_macos_app.sh" "$INTEGRA_TEMP_ARTIFACT_ROOT")"
  "$app/Contents/MacOS/Integra" --self-test
  python3 "$1/scripts/candidate_manifest.py" validate "$app"
' bash "$repo_root"
