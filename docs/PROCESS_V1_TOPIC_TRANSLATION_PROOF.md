# Process V1 Topic Translation

Scope: Excel #22 / S15 only. A completed Russian machine Topic result can be
translated to the already-proven English target without rerunning ASR or the
Topic Engine. This does not add a translation engine, target-language selector,
Knowledge/Evidence authority, Stage B, installation, or deployment.

The adapter sends only each Topic `title` and `summary` to the pinned VideoText
translation runtime. The immutable source `topics.json` remains untouched.
`translated_topics.json` records the same source digest, stable machine Topic
IDs and ordering; its companion provenance binds source/run, target and output
hash. Partial provider output, source-text substitution, target/runtime drift,
or stale provenance fail closed.

The normal Process view shows the original Russian Topic plus the saved English
translation. Translation is intentionally unavailable after Process Topic
Review: the verified human review is the sole Process authority and cannot be
overlaid by provisional machine translation.

Packaged E2E used Candidate
`candidate-v1-14b3c10e4d779ff8b5a520bf15e2b7087673aec2cd0abd25aac4e1d0ded77892`
and the pinned VideoText commit `2e098d1705b6815628bee1e023f4742718eabf02`.
It produced `Practical Application of the Method` and its English summary from
a persisted Russian Topic, then reopened that saved result without provider
execution. Candidate manifest validation and native launch/quit passed.
