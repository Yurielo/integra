#!/bin/bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
output_root="${1:-$repo_root/build/READY_APP_V1}"
python_bin=/usr/bin/python3
test -x "$python_bin"
"$python_bin" -c 'import json,hashlib,pathlib,sqlite3,uuid'
app="$($repo_root/scripts/build_macos_app.sh "$output_root")"
cp "$repo_root/macos/Integra.entitlements" "$app/Contents/Resources/Integra.entitlements"
cp "$repo_root/docs/THIRD_PARTY_NOTICES.md" "$app/Contents/Resources/THIRD_PARTY_NOTICES.md"
xattr -cr "$app"
codesign --force --sign - --entitlements "$repo_root/macos/Integra.entitlements" "$app"
codesign --verify --deep --strict "$app"
"$app/Contents/MacOS/Integra" --self-test
echo "$app"
