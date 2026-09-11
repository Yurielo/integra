#!/usr/bin/env python3
"""Deterministic video probe used only by the R9C contract tests."""

from pathlib import Path
import sys


def main() -> int:
    if sys.argv[1:] == ["-version"]:
        print("ffprobe version integra-cross-navigation-fixture-1.0")
        return 0
    if len(sys.argv) < 2:
        return 2
    payload = Path(sys.argv[-1]).read_bytes()
    if not payload.startswith(b"INTEGRA_TEST_VIDEO\0"):
        return 1
    print("codec_type=video")
    print("codec_type=audio")
    print("duration=2.000000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
