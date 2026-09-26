#!/bin/bash
# Build a retained Candidate only at an explicit non-temporary destination.
# Disposable candidate checks belong in with_temp_artifact_root.sh instead.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
[[ "${1:-}" == "--output" && -n "${2:-}" ]] || { echo "usage: $0 --output RETAINED_ROOT" >&2; exit 2; }
output_root="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$2")"
temporary_base="$(python3 -c 'import os, tempfile; print(os.path.realpath(os.environ.get("TMPDIR") or tempfile.gettempdir()))')"
case "$output_root" in
  "$temporary_base"|"$temporary_base"/*) echo "retained Candidate output must not be under temporary storage" >&2; exit 2;;
esac
app="$($repo_root/scripts/build_macos_app.sh "$output_root")"
"$app/Contents/MacOS/Integra" --self-test
python3 "$repo_root/scripts/candidate_manifest.py" validate "$app"
echo "$app"
