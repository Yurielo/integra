# READY_APP_V1 dependency notices

Integra READY_APP_V1 contains repository-authored Python services and a native
Swift/AppKit launcher. It invokes Apple-provided `/usr/bin/python3` only after
packaging preflight proves that the interpreter and required standard-library
modules are available.

No model weights, codecs, FFmpeg binaries, VideoText source, Microsoft SDK, or
cloud credential is bundled. The personal-use local candidate includes only the
exact pinned, standard-library SeminarText Topic Engine module required for
local Topic drafts. It is copied into the `.app` at build time only after the
source commit and module SHA-256 are verified. This is not a public
redistribution or release artifact.
