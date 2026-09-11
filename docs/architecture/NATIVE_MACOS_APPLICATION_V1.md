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
time-locator, and reverse-route identities. The application also creates and
opens governed local projects, persists local integrity jobs, and imports a
fully validated publication package chosen by the user. Obsidian and OneDrive
first run the accepted preview service; a separate confirmation is required
before the accepted publisher writes its managed subtree. OneDrive receipts
always retain `cloud_verified: false`.

## Closed bridge

The bundle contains the accepted `integra_core` Python domain services. The
native process invokes only `/usr/bin/python3` with the fixed bundled
`bridge.py` path and one of twelve allowlisted operations. Every response is
canonicalized and hashed by the bundled domain protocol service. It does not invoke a
shell, accept arbitrary commands, access the network, or translate unavailable
behavior into success. User-selected paths are accepted only by closed project
and publication operations and are revalidated by the domain services. Mutable
project state is confined to Application Support (or an explicit test root).
Publication still requires a current Project Lease, exact package validation,
the managed target lock, and the accepted collision/recovery gates.

Deferred capabilities are read from a separate immutable resource. The registry
has `actions_available: false`; the UI disables and hides the action control on
that surface and labels every item `Later / Unavailable`.

## Build and launch evidence

`scripts/test_macos_app.sh` builds a fresh application in a temporary directory,
runs the native self-test, validates both package-required preview responses,
launches the AppKit lifecycle, proves that a visible nine-section window was
created, records the launch evidence, and exits. Python integration tests also
create/open a persisted local project, run and inspect a persisted integrity
job, and publish valid Obsidian and OneDrive packages into temporary targets.

The separately generated `build/Integra.app` is an unsigned local development
artifact and is ignored by Git. R13 owns minimum deployment hardening, bundle
identity finalization, entitlements, dependency/licensing review, reproducible
package evidence, backup/rollback, crash recovery, and update readiness.

## Safety and limits

- No private/protected data, credentials, account, Graph API, network access,
  real Vault, real OneDrive sync root, or live external write is used.
- The R12 bundle is not signed, notarized, distributed, released, or declared a
  production package.
- Project and publication integration tests use only temporary directories and
  generated public fixtures. A user must explicitly choose any real target.
- The R12 local bundle depends on `/usr/bin/python3`; bundling/removing that
  host-runtime dependency is an R13 packaging requirement.
