# TranslateGemma migration Candidate proof

The final bounded migration Candidate is `candidate-v1-15d9b29fd7a57bf13765abb798fa95635e794b693f2db1947eff80b13bc6ab81`, built from clean product-source commit `ee35be3e9174de670166f86ce8e1cfc3aa8e04fa` and retained under bundle digest `c157e30deac94a14a0ae253d71c599ba5fe42d172f796b9a952d92cd21670b15`.

The archived app passed its native self-test and a real packaged Russian-to-English translation using the exact `translategemma:4b-it-q4_K_M` model. Cue IDs, time intervals, and source bytes remained unchanged. Output is explicitly machine-derived and review-required. New production translation paths fail closed on missing or changed TranslateGemma identity, while synthetic compatibility checks prove historical Qwen-bound records remain readable without rewriting provider identity or lineage.

No install, deployment, CURRENT promotion, source-repository mutation, Dataset/Gold access, or semantic acceptance was performed. The Product Board remains `41 DONE / 3 NOT_DONE / 1 BLOCKED`; this migration changes runtime implementation, not Product Outcome count.

Focused causal checks passed (`140 tests`, `21` declared environment skips). The local full suite retained the pre-existing pinned SeminarText review-contract mismatch; the clean GitHub Quality Gate is therefore required as the authoritative cross-platform regression result before owner baseline acceptance.
