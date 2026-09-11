#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
test_root="$(mktemp -d)"
cleanup() {
  rm -rf "$test_root"
}
trap cleanup EXIT
app="$($repo_root/scripts/build_macos_app.sh "$test_root")"

test "$(plutil -extract CFBundleIconFile raw "$app/Contents/Info.plist")" = "Integra.icns"
cmp "$repo_root/macos/Resources/Integra.icns" "$app/Contents/Resources/Integra.icns"
xcrun swiftc -framework AppKit "$repo_root/tests/macos_icon_probe.swift" -o "$test_root/macos-icon-probe"
"$test_root/macos-icon-probe" finder "$app" "$test_root/finder-icon.png"
INTEGRA_APP_DATA_ROOT="$test_root/app-data" /usr/bin/open -n "$app"
INTEGRA_ICON_PROBE_TERMINATE=1 "$test_root/macos-icon-probe" running app.integra.ready "$app" "$test_root/running-icon.png"
test -s "$test_root/finder-icon.png"
test -s "$test_root/running-icon.png"
finder_width="$(sips -g pixelWidth "$test_root/finder-icon.png" 2>/dev/null | awk '/pixelWidth/{print $2}')"
finder_height="$(sips -g pixelHeight "$test_root/finder-icon.png" 2>/dev/null | awk '/pixelHeight/{print $2}')"
running_width="$(sips -g pixelWidth "$test_root/running-icon.png" 2>/dev/null | awk '/pixelWidth/{print $2}')"
running_height="$(sips -g pixelHeight "$test_root/running-icon.png" 2>/dev/null | awk '/pixelHeight/{print $2}')"
test "$finder_width" = "$finder_height"
test "$running_width" = "$running_height"
test "$finder_width" -ge 512
test "$running_width" -ge 512

"$app/Contents/MacOS/Integra" --self-test
python3 "$app/Contents/Resources/bridge.py" obsidian-preview | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["state"] == "DRY_RUN_REQUIRES_PACKAGE" and x["writes_performed"] is False and x["external_actions_performed"] is False and x["cloud_verified"] is False and len(x["domain_contract_sha256"]) == 64'
python3 "$app/Contents/Resources/bridge.py" onedrive-preview | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["writes_performed"] is False and x["cloud_verified"] is False'

marker="$test_root/launched.txt"
INTEGRA_LAUNCH_PROBE="$marker" "$app/Contents/MacOS/Integra"
grep -q '^LAUNCHED visible=true workflow=source-first title=Integra' "$marker"
test -z "$(find "$app" -type l -print -quit)"
test -f "$app/Contents/Resources/integra_core/publishing.py"
echo "INTEGRA_MACOS_LAUNCH_TEST: PASS"
