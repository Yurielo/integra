#!/bin/bash
# Run one command with a marker-bound disposable scratch root.  The root is
# deleted on normal exit, failure, SIGINT, or SIGTERM; SIGKILL is recovered by
# the conservative marker/liveness reaper on a later governed invocation.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
purpose=""
if [[ "${1:-}" == "--purpose" ]]; then purpose="${2:-}"; shift 2; fi
[[ -n "$purpose" && "${1:-}" == "--" ]] || { echo "usage: $0 --purpose NAME -- command [args...]" >&2; exit 2; }
shift
root="$(python3 "$repo_root/scripts/temp_artifact_lifecycle.py" create --purpose "$purpose" --owner-pid "$$")"
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  python3 "$repo_root/scripts/temp_artifact_lifecycle.py" cleanup --root "$root" --allow-live-owner >/dev/null || true
  exit "$status"
}
trap cleanup EXIT
child_pid=""
interrupt() {
  local status="$1"
  if [[ -n "$child_pid" ]]; then
    kill -TERM "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
  fi
  exit "$status"
}
trap 'interrupt 130' INT
trap 'interrupt 143' TERM
INTEGRA_TEMP_ARTIFACT_ROOT="$root" "$@" &
child_pid="$!"
set +e
wait "$child_pid"
status="$?"
set -e
child_pid=""
exit "$status"
