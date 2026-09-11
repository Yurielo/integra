# Official macOS application icon

Issue: #78

The canonical approved source is committed unchanged at
`macos/Assets.xcassets/AppIcon.appiconset/Integra_app_icon.png`. Its SHA-256 is
`9de0c4871eb80ce057f2d977c00b5b1f8f8f6f2ebdb4003912f8b3e39f654dce` and
its dimensions are 1254 × 1254 RGB pixels. This is the exact file supplied as
`OneDrive/Integra/Integra_app_icon.png`; OneDrive is not a build or runtime
dependency.

`scripts/generate_macos_app_icon.sh` verifies that canonical hash, resizes the
square source without cropping or aspect-ratio distortion using macOS `sips`,
and compiles the standard icon representations into `macos/Resources/Integra.icns`
with `iconutil`. Run it from the repository root with:

```bash
./scripts/generate_macos_app_icon.sh
```

| AppIcon entry | Pixel output |
|---|---:|
| 16 × 16 @1x | 16 × 16 |
| 16 × 16 @2x | 32 × 32 |
| 32 × 32 @1x | 32 × 32 |
| 32 × 32 @2x | 64 × 64 |
| 128 × 128 @1x | 128 × 128 |
| 128 × 128 @2x | 256 × 256 |
| 256 × 256 @1x | 256 × 256 |
| 256 × 256 @2x | 512 × 512 |
| 512 × 512 @1x | 512 × 512 |
| 512 × 512 @2x | 1024 × 1024 |

Integra uses a direct `swiftc` build and the reference toolchain has no
`actool`, so the committed AppIcon catalog is compiled to the standard macOS
ICNS resource ahead of the application build. `CFBundleIconFile` names
`Integra.icns`, and `scripts/build_macos_app.sh` copies that committed resource
into every clean application bundle.

The native verification renders both `NSWorkspace.icon(forFile:)` (the Finder
representation) and the icon of a live regular-activation-policy
`NSRunningApplication` (the representation supplied to Dock and Cmd+Tab).
