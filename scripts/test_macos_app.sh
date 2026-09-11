#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf "$test_root"' EXIT
app="$($repo_root/scripts/build_macos_app.sh "$test_root")"

"$app/Contents/MacOS/Integra" --self-test
python3 "$app/Contents/Resources/bridge.py" obsidian-preview | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x == {"cloud_verified": False, "external_actions_performed": False, "ok": True, "operation": "obsidian-preview", "schema_version": "1.0", "state": "DRY_RUN_REFERENCE_ONLY", "target": "Obsidian managed Vault subtree", "writes_performed": False}'
python3 "$app/Contents/Resources/bridge.py" onedrive-preview | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["writes_performed"] is False and x["cloud_verified"] is False'

marker="$test_root/launched.txt"
INTEGRA_LAUNCH_PROBE="$marker" "$app/Contents/MacOS/Integra"
test "$(cat "$marker")" = "LAUNCHED"
test -z "$(find "$app" -type l -print -quit)"
echo "INTEGRA_MACOS_LAUNCH_TEST: PASS"
