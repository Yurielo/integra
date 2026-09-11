#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf "$test_root"' EXIT
app="$($repo_root/scripts/build_macos_app.sh "$test_root")"

"$app/Contents/MacOS/Integra" --self-test
python3 "$app/Contents/Resources/bridge.py" obsidian-preview | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["state"] == "DRY_RUN_REQUIRES_PACKAGE" and x["writes_performed"] is False and x["external_actions_performed"] is False and x["cloud_verified"] is False and len(x["domain_contract_sha256"]) == 64'
python3 "$app/Contents/Resources/bridge.py" onedrive-preview | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["writes_performed"] is False and x["cloud_verified"] is False'

marker="$test_root/launched.txt"
INTEGRA_LAUNCH_PROBE="$marker" "$app/Contents/MacOS/Integra"
grep -q '^LAUNCHED visible=true workflow=source-first title=Integra' "$marker"
test -z "$(find "$app" -type l -print -quit)"
test -f "$app/Contents/Resources/integra_core/publishing.py"
echo "INTEGRA_MACOS_LAUNCH_TEST: PASS"
