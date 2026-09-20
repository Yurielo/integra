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
fake_ollama="$test_root/ollama"
printf '#!/bin/sh\nprintf "NAME ID SIZE MODIFIED\\ngemma3:4b id size now\\n"\n' > "$fake_ollama"
chmod 755 "$fake_ollama"
(
  cd "$test_root"
  PATH="$test_root:$PATH" PYTHONPATH="$app/Contents/Resources" python3 -c 'from pathlib import Path; import hashlib, json; from integra_core.seminartext_runtime import preflight; value=preflight(); runtime=Path("runtime/seminartext/runtime.json"); manifest=json.loads(runtime.read_text()); cli=Path("runtime/seminartext/seminartext"); assert value["origin"] == "BUNDLED_PERSONAL_RUNTIME"; assert value["commit_sha"] == "970bde598ddd649599295139986933e0e06cb9c0"; assert manifest["entrypoint_sha256"] == "f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a"; assert hashlib.sha256(cli.read_bytes()).hexdigest() == manifest["entrypoint_sha256"]'
)
echo "INTEGRA_BUNDLED_SEMINARTEXT_PREFLIGHT: PASS"
(
  cd "$test_root"
  PYTHONPATH="$app/Contents/Resources" /opt/homebrew/opt/python@3.13/bin/python3.13 -c 'from integra_core.word_timeline_runtime import preflight; value=preflight(); assert value["capability"] == "word_timeline"'
)
echo "INTEGRA_BUNDLED_WORD_TIMELINE_PREFLIGHT: PASS"
(
  cd "$test_root"
  PYTHONPATH="$app/Contents/Resources" python3 -c 'from integra_core.booktext_runtime import preflight; value=preflight(); assert value["component"] == "booktext"; assert len(value["model_sha256"]) == 64'
)
echo "INTEGRA_BUNDLED_BOOKTEXT_PREFLIGHT: PASS"
python3 "$app/Contents/Resources/bridge.py" obsidian-preview | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["state"] == "DRY_RUN_REQUIRES_PACKAGE" and x["writes_performed"] is False and x["external_actions_performed"] is False and x["cloud_verified"] is False and len(x["domain_contract_sha256"]) == 64'
python3 "$app/Contents/Resources/bridge.py" onedrive-preview | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["writes_performed"] is False and x["cloud_verified"] is False'

marker="$test_root/launched.txt"
INTEGRA_APP_DATA_ROOT="$test_root/app-data" INTEGRA_LAUNCH_PROBE="$marker" "$app/Contents/MacOS/Integra"
grep -q '^LAUNCHED visible=true workflow=source-first title=Integra' "$marker"

close_marker="$test_root/closed.txt"
INTEGRA_APP_DATA_ROOT="$test_root/app-data" INTEGRA_CLOSE_PROBE="$close_marker" "$app/Contents/MacOS/Integra"
grep -q '^TERMINATED_AFTER_LAST_WINDOW_CLOSED$' "$close_marker"
echo "INTEGRA_MACOS_CLOSE_TEST: PASS"

python3 "$repo_root/tests/native_workflow_probe.py" "$app" "$test_root/native-workflow"
python3 "$repo_root/tests/native_shutdown_probe.py" "$app" "$test_root/native-shutdown"
python3 "$repo_root/tests/native_asr_retry_probe.py" "$app" "$test_root/native-asr-retry"
python3 "$repo_root/tests/native_operations_probe.py" "$app" "$test_root/native-operations"

test -z "$(find "$app" -type l -print -quit)"
test -f "$app/Contents/Resources/integra_core/publishing.py"
test -f "$app/Contents/Resources/runtime/seminartext/runtime.json"
test -f "$app/Contents/Resources/runtime/booktext/runtime.json"
echo "INTEGRA_MACOS_LAUNCH_TEST: PASS"
