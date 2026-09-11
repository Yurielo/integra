# Native macOS Application v1

Status: `ACCEPTED`

Issue: `#28`; dependency: accepted `ONEDRIVE_PUBLICATION_V1`.

## Delivered application

R12 supplies a native AppKit application compiled directly with the installed
Apple Swift command-line toolchain. `scripts/build_macos_app.sh` deterministically
creates `build/Integra.app` without requiring a full Xcode project. The bundle
is launchable on the reference arm64 Mac and contains its Info.plist, native
executable, closed Python bridge, reference workflow, and deferred registry.

The application exposes these required surfaces in one navigable sidebar:

- Projects & Sources;
- Transcript & Topics;
- Knowledge;
- Media;
- exact bidirectional navigation and source locators;
- Operations & Diagnostics;
- Obsidian export;
- filesystem-backed OneDrive publication;
- read-only Deferred Features.

The deterministic reference project presents accepted contract truth without
private input. Knowledge remains `PROVISIONAL`; navigation shows stable entity,
time-locator, and reverse-route identities. Obsidian and OneDrive controls run
allowlisted dry-run reference previews that explicitly report no writes, no
external actions, and `cloud_verified: false`.

## Closed bridge

The native process invokes only `/usr/bin/python3` with the fixed bundled
`bridge.py` path and one of four allowlisted operations. It does not invoke a
shell, accept arbitrary paths or commands, access the network, mutate project
state, or translate unavailable behavior into success. JSON decoding is typed
and failure remains visible. The bridge packages the deterministic reference
projection of the accepted Python/domain contracts for UI and launch testing;
live project orchestration remains subject to the same service leases and
publication target gates.

Deferred capabilities are read from a separate immutable resource. The registry
has `actions_available: false`; the UI disables and hides the action control on
that surface and labels every item `Later / Unavailable`.

## Build and launch evidence

`scripts/test_macos_app.sh` builds a fresh application in a temporary directory,
runs the native self-test, validates both publication preview responses, launches
the AppKit lifecycle, creates the window, records a deterministic launch marker,
and exits. Python integration tests verify the exact required surface inventory,
locator visibility, bridge allowlist, publication non-mutation, and deferred
action boundary.

The separately generated `build/Integra.app` is an unsigned local development
artifact and is ignored by Git. R13 owns minimum deployment hardening, bundle
identity finalization, entitlements, dependency/licensing review, reproducible
package evidence, backup/rollback, crash recovery, and update readiness.

## Safety and limits

- No private/protected data, credentials, account, Graph API, network access,
  real Vault, real OneDrive sync root, or live external write is used.
- The R12 bundle is not signed, notarized, distributed, released, or declared a
  production package.
- The reference workflow proves the usable UI journey and contract boundary;
  user-selected live project and publication orchestration remains gated and is
  not simulated as successful.
