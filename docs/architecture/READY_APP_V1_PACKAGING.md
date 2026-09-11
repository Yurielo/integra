# READY_APP_V1 local candidate packaging

Status: `ACCEPTED`; Issue `#29`; dependency: accepted R12.

`scripts/package_ready_app.sh` performs the fail-closed reference-Mac preflight,
builds `Integra.app`, embeds dependency notices and the declared entitlement,
applies an ad-hoc local code seal, verifies that seal, and runs the native
self-test. Two independent package runs must have identical file-tree hashes.

The candidate identifier is `app.integra.ready`, version `1.0.0` (build 100),
with minimum macOS 13. It is a local candidate, not a Developer-ID-signed or
notarized public release. `/usr/bin/python3` availability and required standard
library imports are explicit installation preconditions.

`scripts/integra_backup.py` creates an immutable copy-first project snapshot
with a complete SHA-256 inventory and verifies it before use. A changed snapshot
fails closed. Existing project data is never overwritten by backup creation;
rollback is performed by selecting a verified snapshot as a separate recovery
source.

Bridge errors redact home and absolute path material. No credentials, private
data, account, live cloud write, signing identity, notarization service, update
feed, or public distribution was used. Accepted Obsidian/OneDrive recovery
contracts remain the crash-recovery boundary; update publication and automatic
rollback remain gated later work.
