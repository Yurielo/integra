#!/bin/bash
# Run one command with a marker-bound disposable scratch root.  The root is
# deleted on normal exit, failure, SIGINT, or SIGTERM; SIGKILL is recovered by
# the conservative marker/liveness reaper on a later governed invocation.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
purpose=""; timeout_seconds=""; required_bytes=""; reserve_bytes=""
if [[ "${1:-}" == "--purpose" ]]; then purpose="${2:-}"; shift 2; fi
while [[ "${1:-}" != "--" ]]; do
  case "${1:-}" in
    --timeout-seconds) timeout_seconds="${2:-}"; shift 2;;
    --required-bytes) required_bytes="${2:-}"; shift 2;;
    --reserve-bytes) reserve_bytes="${2:-}"; shift 2;;
    *) echo "usage: $0 --purpose NAME [--timeout-seconds N] [--required-bytes N --reserve-bytes N] -- command [args...]" >&2; exit 2;;
  esac
done
[[ -n "$purpose" && "${1:-}" == "--" ]] || { echo "usage: $0 --purpose NAME -- command [args...]" >&2; exit 2; }
shift
create_args=(create --purpose "$purpose" --owner-pid "$$")
[[ -n "$required_bytes" ]] && create_args+=(--required-bytes "$required_bytes" --reserve-bytes "${reserve_bytes:-0}")
root="$(python3 "$repo_root/scripts/temp_artifact_lifecycle.py" "${create_args[@]}")"
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  python3 "$repo_root/scripts/temp_artifact_lifecycle.py" cleanup --root "$root" --allow-live-owner >/dev/null || true
  exit "$status"
}
trap cleanup EXIT
child_pid=""; watchdog_pid=""
stop_tree() {
  [[ -n "$child_pid" ]] || return 0
  kill -TERM -- "-$child_pid" 2>/dev/null || true
  for _ in 1 2 3 4 5; do kill -0 "$child_pid" 2>/dev/null || return 0; sleep 1; done
  kill -KILL -- "-$child_pid" 2>/dev/null || true
}
interrupt() {
  local status="$1"
  stop_tree
  [[ -n "$watchdog_pid" ]] && kill "$watchdog_pid" 2>/dev/null || true
  [[ -n "$child_pid" ]] && wait "$child_pid" 2>/dev/null || true
  exit "$status"
}
trap 'interrupt 130' INT
trap 'interrupt 143' TERM
INTEGRA_TEMP_ARTIFACT_ROOT="$root" python3 "$repo_root/scripts/process_group_exec.py" "$@" &
child_pid="$!"
if [[ -n "$timeout_seconds" ]]; then
  python3 "$repo_root/scripts/process_group_watchdog.py" "$child_pid" "$timeout_seconds" &
  watchdog_pid="$!"
fi
set +e
wait "$child_pid"
status="$?"
set -e
child_pid=""
[[ -n "$watchdog_pid" ]] && kill "$watchdog_pid" 2>/dev/null || true
exit "$status"
