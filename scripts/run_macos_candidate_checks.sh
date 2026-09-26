#!/bin/bash
# Ephemeral build + native identity checks.  The complete scratch root is
# marker-owned and removed on completion, failure, SIGINT, or SIGTERM.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
# The expected 3 GiB bundle allowance covers the measured 2.1 GiB Candidate
# plus compiler/package overhead; the 5 GiB reserve protects the host and is
# intentionally configurable for governed CI/dev environments.
expected_bytes="${INTEGRA_CANDIDATE_EXPECTED_BYTES:-3221225472}"
reserve_bytes="${INTEGRA_CANDIDATE_SAFETY_RESERVE_BYTES:-5368709120}"
timeout_seconds="${INTEGRA_CANDIDATE_TIMEOUT_SECONDS:-1800}"
exec "$repo_root/scripts/with_temp_artifact_root.sh" --purpose macos-candidate-check --timeout-seconds "$timeout_seconds" --required-bytes "$expected_bytes" --reserve-bytes "$reserve_bytes" -- bash -c '
  set -euo pipefail
  app="$("$0/scripts/build_macos_app.sh" "$INTEGRA_TEMP_ARTIFACT_ROOT")"
  "$app/Contents/MacOS/Integra" --self-test
  python3 "$0/scripts/candidate_manifest.py" validate "$app"
' "$repo_root"
