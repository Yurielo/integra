#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
output_root="${1:-$repo_root/macos}"
source_icon="$repo_root/macos/Assets.xcassets/AppIcon.appiconset/Integra_app_icon.png"
source_contents="$repo_root/macos/Assets.xcassets/AppIcon.appiconset/Contents.json"
expected_source_sha256=9de0c4871eb80ce057f2d977c00b5b1f8f8f6f2ebdb4003912f8b3e39f654dce

test -f "$source_icon"
test "$(shasum -a 256 "$source_icon" | awk '{print $1}')" = "$expected_source_sha256"

appiconset="$output_root/Assets.xcassets/AppIcon.appiconset"
resources="$output_root/Resources"
mkdir -p "$appiconset" "$resources"
if [ "$source_icon" != "$appiconset/Integra_app_icon.png" ]; then
  cp "$source_icon" "$appiconset/Integra_app_icon.png"
  cp "$source_contents" "$appiconset/Contents.json"
fi

render() {
  name="$1"
  pixels="$2"
  sips -z "$pixels" "$pixels" "$source_icon" --out "$appiconset/$name" >/dev/null
}

render icon_16x16.png 16
render icon_16x16@2x.png 32
render icon_32x32.png 32
render icon_32x32@2x.png 64
render icon_128x128.png 128
render icon_128x128@2x.png 256
render icon_256x256.png 256
render icon_256x256@2x.png 512
render icon_512x512.png 512
render icon_512x512@2x.png 1024

iconset_root="$(mktemp -d)"
trap 'rm -rf "$iconset_root"' EXIT
iconset="$iconset_root/Integra.iconset"
mkdir -p "$iconset"
cp "$appiconset"/icon_*.png "$iconset/"
iconutil --convert icns --output "$resources/Integra.icns" "$iconset"
echo "$resources/Integra.icns"
