#!/usr/bin/env python3
"""Dependency-free ffprobe contract fixture used only by the test suite."""

from __future__ import annotations

import struct
import sys
from pathlib import Path


def main() -> int:
    if sys.argv[1:] == ["-version"]:
        print("ffprobe version integra-test-fixture-1.0")
        return 0
    if not sys.argv or len(sys.argv) < 2:
        return 2
    payload = Path(sys.argv[-1]).read_bytes()
    if len(payload) < 44 or payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        return 1
    byte_rate = struct.unpack_from("<I", payload, 28)[0]
    marker = payload.find(b"data", 36)
    if byte_rate <= 0 or marker < 0 or marker + 8 > len(payload):
        return 1
    data_size = struct.unpack_from("<I", payload, marker + 4)[0]
    if marker + 8 + data_size > len(payload):
        return 1
    print("codec_type=audio")
    print(f"duration={data_size / byte_rate:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
