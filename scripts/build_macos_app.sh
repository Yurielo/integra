#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
output_root="${1:-$repo_root/build}"
app="$output_root/Integra.app"
seminartext_checkout="${INTEGRA_SEMINARTEXT_BUILD_CHECKOUT:-$repo_root/.runtime-components/seminartext-pinned}"
seminartext_commit="a94936cd77cde13561c97c804ece1ac1134e01a6"
seminartext_module="$seminartext_checkout/seminartext_modules/seminartext_topics.py"
seminartext_sha256="d8a14e83b877024c3e016a33e594af17d512741a77735ff3d8c7d1262628c8db"

test "$(git -C "$seminartext_checkout" rev-parse HEAD)" = "$seminartext_commit"
test -f "$seminartext_module"
test "$(shasum -a 256 "$seminartext_module" | awk '{print $1}')" = "$seminartext_sha256"

rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
xcrun swiftc -parse-as-library -O -framework AppKit -framework AVKit -framework AVFoundation \
  "$repo_root/macos/IntegraApp.swift" -o "$app/Contents/MacOS/Integra"
cp "$repo_root/macos/Info.plist" "$app/Contents/Info.plist"
cp "$repo_root/macos/Resources/Integra.icns" "$app/Contents/Resources/Integra.icns"
cp "$repo_root/macos/Resources/bridge.py" "$app/Contents/Resources/bridge.py"
cp "$repo_root/macos/Resources/source_first_workflow.json" "$app/Contents/Resources/source_first_workflow.json"
cp "$repo_root/macos/Resources/deferred_features.json" "$app/Contents/Resources/deferred_features.json"
mkdir -p "$app/Contents/Resources/workers"
cp "$repo_root/workers/seminartext_topics_worker.py" "$app/Contents/Resources/workers/seminartext_topics_worker.py"
mkdir -p "$app/Contents/Resources/runtime/seminartext/seminartext_modules"
cp "$seminartext_module" "$app/Contents/Resources/runtime/seminartext/seminartext_modules/seminartext_topics.py"
printf '{"component":"seminartext","commit_sha":"%s","entrypoint_sha256":"%s","personal_use_only":true}\n' "$seminartext_commit" "$seminartext_sha256" > "$app/Contents/Resources/runtime/seminartext/runtime.json"
rsync -a --exclude '__pycache__' --exclude '*.pyc' "$repo_root/integra_core/" "$app/Contents/Resources/integra_core/"
chmod 755 "$app/Contents/MacOS/Integra" "$app/Contents/Resources/bridge.py" "$app/Contents/Resources/workers/seminartext_topics_worker.py"
plutil -lint "$app/Contents/Info.plist" >/dev/null
echo "$app"
