# Process V1 Topic Translation Proof

This evidence covers only Excel #22 / S15.  It is a proposed baseline, not a
CURRENT promotion, user-routing change, deployment, or authorization to begin
another outcome.

## Scope

The normal Process result can create a separate `TOPIC_TRANSLATION`
continuation from completed machine Topics.  It translates only the S15
`title` and `summary` fields using the already governed VideoText Russian to
English route.  The source Topic snapshot remains authoritative for original
wording, identity, count, ordering, timing, source spans and detail.

The derivative records source project/run/topic hashes, requested and executed
language, runtime identity, output hashes and any persisted Process Topic
Review lineage.  Reopening verifies those bindings and never reruns a
provider.  Invalid source evidence, incomplete provider output, provider
issues, changed timing or changed parent run fail closed.

## Candidate

- Source: `ac954f85858962345402f4649be5b9a1e8c3e0dd`
- Candidate: `candidate-v1-8be1ad5ca090afd08b869761046e6f4c56727e11dbf6ae968f6ad6f227d2b173`
- Bundle digest: `c4dc155349dc73f2177fa8e8ee29709cc494662a999c2c4a6800e2b992c3907b`
- Pinned provider: VideoText `2e098d1705b6815628bee1e023f4742718eabf02`
- Translation adapter SHA-256: `83e55d3cb82522cb431ee20617510b0c39f79ae0fa5309daedf5c7ff9911a577`
- Candidate archive: verified at the durable local Build Archive path in the
  adjacent archive receipt.

## Executed Evidence

- Native candidate manifest and archive integrity: PASS.
- Native app launch and controlled shutdown: PASS.
- Real packaged `qwen3:8b` translation of two saved Russian topics: PASS.
- Saved translation reopening without provider re-execution: PASS.
- Focused #18/#19/#20/#22/#24/#25 regressions: 34 passed, 8 declared skips.
- Full noninteractive repository regression: 826 passed, 92 declared skips.

The declared skips require source components intentionally absent from this
clean worktree.  The packaged E2E itself used the pinned bundled VideoText
worker and a locally available `qwen3:8b` model.

## Deliberately Unchanged

`CURRENT` remains the existing #25 baseline.  SeminarText remains pinned and
unchanged.  Process Topic Review remains the authority for review state;
Knowledge, Studio, Stage B, arbitrary target-language support, another Topics
engine, installation and deployment are outside this proposal.
