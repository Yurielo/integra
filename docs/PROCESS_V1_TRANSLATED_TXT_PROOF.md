# Process V1 Translated TXT Proof

Scope: Excel #20 / V06 only. This delivery turns a previously verified
translation result into a normal, managed UTF-8 text artifact. It does not
create a new translation route or weaken the accepted `ru` to `en` boundary.

## User-visible result

The normal Process Results surface presents `Перевод` as a regular result card
with the persisted target language and the existing `Открыть` and
`Экспортировать...` controls. It opens and exports `translation.txt`; the raw
provider JSON is retained as technical data rather than used as the ordinary
reading surface.

For new translation runs, the worker verifies the provider JSON, writes
Integra-owned provenance, then derives `translation.txt` from its ordered cue
text. The file is UTF-8, paragraph separated, and atomically published before
its output pointer is added to the completed result.

## Reopen and recovery contract

Completed #18/#19-era runs that already contain `translation.json` and
`translation_provenance.json` recover a managed TXT on re-open only if the
saved run/source id, transcript JSON hash, SRT hash, translation JSON hash, and
`ru`/`en` requested and executed language facts all match. The recovery is
local and does not invoke the translation provider. Any missing, unsafe,
ambiguous, or mismatched evidence fails closed without publishing a TXT.

## Candidate evidence

Candidate `candidate-v1-a6d470e1e68163ed119bda229acffb2754b404f2d64310a93cc5dbbab19e5583`
was built from source `9f7122bb1d823e82db93eaede08e6a90c98775b6` and has a
byte-verified permanent archive. The packaged bridge reopened a real prior
`ru` to `en` translation, materialized a 51-byte UTF-8 TXT with digest
`215ff874d7580fefff1265ecc06661ab4d7aab406b85e0395d78a71c1ebfb269`, then
reopened it again without a provider call. The exported copy had the same
bytes and digest. Focused tests also prove hash mismatch rejection and that a
TXT materialization failure never publishes a successful translation output.

## Limits

The result remains machine translation marked review-required. This outcome
does not add translated SRT, topic translation, broader multilingual support,
provider substitution, a Process routing change, Stage B, Knowledge, Studio,
installation, or deployment.
