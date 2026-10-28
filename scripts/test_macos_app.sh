#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
if [ "${1:-}" != "--owned-workspace" ]; then
  exec python3 -B "$repo_root/scripts/build_macos_candidate.py" \
    --native-tests --purpose macos-app-test --timeout-seconds 3600
fi
test_root="${INTEGRA_OWNED_WORKSPACE:?test must run inside an owned workspace}"
app="$($repo_root/scripts/build_macos_app.sh "$test_root/candidate")"

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
  env -u INTEGRA_SEMINARTEXT_CHECKOUT PATH="$test_root:$PATH" PYTHONPATH="$app/Contents/Resources" python3 -c 'from integra_core.seminartext_runtime import preflight; value=preflight(); assert value["origin"] == "BUNDLED_PERSONAL_RUNTIME"; assert value["commit_sha"] == "13644d262776aacdf36221b9a9fc7ebd0a7c0737"'
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

test -f "$app/Contents/Resources/scripts/seminar_library_preview.py"
cmp "$repo_root/schemas/seminar_library_preview_v1.schema.json" "$app/Contents/Resources/schemas/seminar_library_preview_v1.schema.json"
echo "INTEGRA_BUNDLED_SEMINAR_LIBRARY_RESOURCES: PASS"
INTEGRA_CANDIDATE_APP="$app" python3 "$repo_root/tests/native_seminar_library_probe.py" "$app" "$test_root/native-seminar-library"

INTEGRA_CANDIDATE_APP="$app" python3 "$repo_root/tests/native_workflow_probe.py" "$app" "$test_root/native-workflow"
INTEGRA_CANDIDATE_APP="$app" python3 "$repo_root/tests/native_shutdown_probe.py" "$app" "$test_root/native-shutdown"
INTEGRA_CANDIDATE_APP="$app" python3 "$repo_root/tests/native_asr_retry_probe.py" "$app" "$test_root/native-asr-retry"
INTEGRA_CANDIDATE_APP="$app" python3 "$repo_root/tests/native_operations_probe.py" "$app" "$test_root/native-operations"

test -z "$(find "$app" -type l -print -quit)"
test -f "$app/Contents/Resources/integra_core/publishing.py"
test -f "$app/Contents/Resources/runtime/seminartext/runtime.json"
test -f "$app/Contents/Resources/runtime/booktext/runtime.json"
echo "INTEGRA_MACOS_LAUNCH_TEST: PASS"
