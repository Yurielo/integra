# READY_APP_V1 dependency notices

Integra READY_APP_V1 contains repository-authored Python services and a native
Swift/AppKit launcher. It invokes Apple-provided `/usr/bin/python3` only after
packaging preflight proves that the interpreter and required standard-library
modules are available.

No model weights, codecs, FFmpeg binaries, SeminarText source, VideoText source,
Microsoft SDK, or cloud credential is bundled. Pinned external products remain
separate executables and are not redistributed by this local candidate.
