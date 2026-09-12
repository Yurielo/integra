# READY_APP_V1 dependency notices

Integra READY_APP_V1 contains repository-authored Python services and a native
Swift/AppKit launcher. It invokes Apple-provided `/usr/bin/python3` only after
packaging preflight proves that the interpreter and required standard-library
modules are available.

No codecs, FFmpeg binaries, VideoText source, Microsoft SDK, or cloud credential
is bundled. The personal-use local candidate includes the exact pinned,
standard-library SeminarText Topic Engine module required for local Topic drafts,
and a local Word Timeline runtime: WhisperX 3.8.6 with the pinned
`jonatasgrosman/wav2vec2-large-xlsr-53-russian` model revision
`2329100508896c6d9b157019803ab5601e6f3406` (weights SHA-256
`d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c`).
Both runtimes are copied into the `.app` at build time only after their pinned
inputs are verified. This is a local personal-use candidate, not a public
redistribution or release artifact.
