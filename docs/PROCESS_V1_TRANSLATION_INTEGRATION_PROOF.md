# Process v1 translation integration proof

Status: technical proposal evidence only. It is not a Process v1 owner
acceptance, does not change `CURRENT`, and does not close any Completion Board
row before its frozen packaged and owner gates are met.

## Exact product source and Candidate

| Item | Value |
| --- | --- |
| Product source A | `43378a9c26ddc755d1f309c7c6c8ad7e93484651` / tree `0fe9f29ab1bc9f03acce5bc46b1f95e0470599ef` |
| Candidate | `candidate-v1-9c969dab6d8aab30458bd202dd792d709e1faea8db207306e3ccb46c886c1e98` |
| Candidate bundle digest | `e6ab2fd5867acc58837a08bf65cce5d176a26ad5885253fec9774733d36aa1a0` |
| Candidate manifest SHA-256 | `202410de6ec447dd5dcd429a6ad5dc715241bf4e6f26175c57ea685b86f150d5` |
| Candidate path | `/private/tmp/integra-185-translation-final-candidate.M1Bjos/Integra.app` |

The Candidate was built once from a clean product source A with the existing
pinned SeminarText, VideoText, BookText, review and Word Alignment inputs. It
is not a replacement for the canonical build and was not installed or deployed.

## What changed

The existing pinned VideoText translation route is now connected to the normal
Process plan and persisted result path:

1. a user selects **Перевод** and a supported target language;
2. the exact target is part of the plan identity and each applicable source
   plan;
3. the existing VideoText worker still produces its validated JSON provenance;
4. Integra materializes a separate readable, source-linked `translation.txt`;
5. the Process results surface exposes the readable result, while the JSON
   remains under technical data.

No translation model, component pin, Knowledge/Evidence authority, BookText,
or Studio code changed.

## Validation

| Gate | Result | Evidence |
| --- | --- | --- |
| Focused Process translation, results-surface, capability, runtime and ASR-reuse tests | PASS | `56` passed; `19` explicit runtime-dependent skips |
| Native UI typecheck | PASS | `swiftc -parse-as-library -typecheck macos/IntegraApp.swift` |
| Candidate manifest | PASS | Exact manifest copied in `docs/evidence/PROCESS_V1_TRANSLATION_CANDIDATE_MANIFEST.json` |
| Packaged bridge plan | PASS | The bridge inside the exact Candidate accepted `translation_target_language=ru`, retained it in the plan identity and applicable source plan, and scheduled `media_preparation → transcript → translation`. |
| Real bundled VideoText translation | PASS | The Candidate's bundled worker translated `Привет. Это проверка перевода в Integra.` to `Hello. This is a translation check in Integra.` with `source_language=ru`, `target_language=en`, and `MACHINE_TRANSLATION_REVIEW_REQUIRED`. JSON SHA-256 `baf78016de53f53765a547a9f5ccf88a3b548327b00c4a6221353a7eb9f8da09`; TXT SHA-256 `614befb5da1afce575d749c901dbf6614185022fa684646cbb09fe44b37a768e`. |

## Explicit non-claim: Topic translation

`Topic translation` remains a frozen Process v1 MUST and stays `NOT_DONE` on
the Completion Board. The current bundled SeminarText runtime exposes Topics
but not the historical S15 translation route. A bounded direct VideoText probe
for generated Topic labels did not return inside the probe window, whereas the
normal transcript translation did. This proposal therefore deliberately does
not add a second unverified model invocation or claim the Topic translation
outcome. It requires a later, independently evidenced integration decision.

## Remaining acceptance boundary

This evidence supports only technical proposal validation for transcript
translation, target-language choice and readable translated TXT. It does not
claim Process v1 `USER_ACCEPTED`, does not transition the Completion Board, and
does not contain any owner decision.
