#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
output_root="${1:-$repo_root/build}"
app="$output_root/Integra.app"

rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
xcrun swiftc -parse-as-library -O -framework AppKit -framework AVKit -framework AVFoundation \
  "$repo_root/macos/IntegraApp.swift" -o "$app/Contents/MacOS/Integra"
cp "$repo_root/macos/Info.plist" "$app/Contents/Info.plist"
cp "$repo_root/macos/Resources/bridge.py" "$app/Contents/Resources/bridge.py"
cp "$repo_root/macos/Resources/source_first_workflow.json" "$app/Contents/Resources/source_first_workflow.json"
cp "$repo_root/macos/Resources/deferred_features.json" "$app/Contents/Resources/deferred_features.json"
rsync -a --exclude '__pycache__' --exclude '*.pyc' "$repo_root/integra_core/" "$app/Contents/Resources/integra_core/"
chmod 755 "$app/Contents/MacOS/Integra" "$app/Contents/Resources/bridge.py"
plutil -lint "$app/Contents/Info.plist" >/dev/null
echo "$app"
