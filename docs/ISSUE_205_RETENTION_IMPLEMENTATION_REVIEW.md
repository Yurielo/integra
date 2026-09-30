# Issue #205 — independent retention implementation review

Review date: 2026-09-30. Base HEAD: `073ad80bffe0ee6144bc96cf1a3c13ba606b5ceb`.
Implementation is an uncommitted working tree; this is not an exact committed
source approval. Reviewer: independent QA role, delegated by the coordinating
agent. Historical archives, application payloads and CURRENT were not changed.

## Current verdict

**PASS for the bounded implementation reviewed below; all reported blockers
resolved.** The governance helper and complete protected identity binding have passed focused review. The final
full suite and real initial migration evidence belong to the coordinating
agent and are not claimed here.

1. RESOLVED: A crash after atomic source-to-trash rename but before persisting DELETING
   can leave a PREPARED journal with its payload in trash. Resumption previously
   hashed remaining bytes only in DELETING, allowing a same-size/mode/inode
   mutation after interruption to escape detection. Every transaction now
   verifies remaining payload hashes, including PREPARED; the
   precise crash edge has a passing regression.
2. RESOLVED: The final fd-relative unlink previously checked UID/device/inode but did not check
   entry type/mode/link count/size or altered same-inode payload bytes. Keep
   these local safeguards at the destructive file boundary. Final type/mode/
   link count/size/mtime/ctime checks are now present.
3. RESOLVED: Initial PREPARED/source transactions previously skipped remaining payload
   hashes. Mutation between full target verification and `_entries` captures
   changed timestamps as the new baseline. Hash remaining bytes against the
   original bound inventory for initial transactions too. Remaining bytes are
   now always hashed; the mutation-before-journaling regression passes.
4. RESOLVED: `_entries` reloads inventory and captures current metadata hashes.
   Those hashes must remain equal to publisher-bound COMPLETE/inventory
   hashes; changed inventory must not become new journal authority between
   target verification and withdrawal. Captured metadata hashes now match the
   publisher record, `_ownership` checks actual inventory bytes, and the
   metadata-mutation regression passes.

## Reviewed safeguards

- Common publisher catalog, independent atomic copy slots and volume build
  reservations conservatively charge legacy/unknown bytes. Legacy UID or
  COMPLETE alone does not import automatic deletion ownership.
- Captured governance uses immutable main SHA and exhaustive exact open PR
  heads. Only HTTP 404 is treated as an absent proposal; API failures preserve
  data. Missing approved canonical pin enumeration makes the context invalid.
- Protection includes all canonical pending proposals even when omitted from
  local caller inputs. Every required Candidate/bundle/manifest tuple binds
  the selected verified survivor; contradictory tuples fail closed.
- Rollback must be the immediate outgoing accepted Candidate/bundle tuple.
  Recovery requires exact accepted canonical evidence or independently
  verified structured owner confirmation. A local SHA-bound self-assertion
  is insufficient; edited owner comments invalidate the snapshot.
- Cleanup uses a durable PREPARED/DELETING journal, no-replace withdrawal and
  fd-relative filesystem operations. Historical deletion is rejected even
  when passed a free-form authority string.
- Native builder output must be strictly below its reserved owned workspace;
  a validated admission lease cannot authorize an archived or durable output,
  or overwrite an existing Integra.app. The marker is validated before work.
- Post-publication crash recovery requires the journaled prepublication inode
  and fresh archive verification. A no-replace collision preserves the foreign
  destination and releases only the unused owned publication slot.

The explicit governance transaction should be one freshly authorized,
fully verified immutable package withdrawal. Resumption is a new transaction
and must refresh canonical authority and fully verify selected survivors.
Per-file network polling is unnecessary under that documented boundary;
local content and filesystem safety checks remain necessary.

## Verification performed by this reviewer

`python3 -B -m unittest discover -s tests -p 'test*retention*.py' -q`:
40 PASS (24 retention fixtures and 16 mocked governance tests).

`python3 -B -m unittest tests.test_retention_governance -q`: 16 PASS.

`git diff --check`: PASS at the reviewed working tree state.

These tests use isolated tiny fixtures or mocked official API responses. No
real Candidate build, archive cleanup, payload hashing or GitHub write was
performed during this implementation review. They are not evidence that
historical migration or CURRENT promotion is authorized.

## Exact reviewed working-tree content

SHA-256 values below bind this review; subsequent source changes need a
proportionate review. The package-transaction contract is documented in
`docs/BOUNDED_CANDIDATE_RETENTION.md` and reviewed together with implementation.

| File | SHA-256 |
| --- | --- |
| scripts/candidate_retention.py | ee4ff6d9cde2e39204cb2a25539cc19a301aaa933296f31d68bf934fc8b08bc0 |
| scripts/retention_cleanup.py | d719d0b7b4e9a334829770b1ecd1da36c791967d2ef1806adc101e5dbb82844a |
| scripts/retention_governance.py | 8d5d2e22787c2a7ef88e359f344fefbbf116726185ce782330d572da89adbe39 |
| scripts/build_macos_app.sh | b905ba56beed4a8f5fdea5819d05de1bd1498634d235c6e0cbc321063e48e6b8 |
| tests/test_candidate_retention.py | 79263f0507da44b74a099c713fe2841a441393c5ca32c93e6bc4946369b98b7f |
| tests/test_retention_governance.py | 644f28f32df78d7a22140ce0e5f59f0a3808f0bd1bff7294c09da0a1895297b0 |
| docs/BOUNDED_CANDIDATE_RETENTION.md | 85cbe01c63daac7e2fd2176d5efe555d965f8468ff915b21a01479d589b441c3 |

The absence of canonical approved pins, unresolved protected selectors,
historical ownership and a permitted fresh Candidate remains a real fail-closed
delivery gate. This implementation review does not resolve that gate or
authorize historical deletion, acceptance, promotion, or merge.
