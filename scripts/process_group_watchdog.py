#!/usr/bin/env python3
"""Bound one owned process group without leaving a shell/sleep orphan."""
import os
import signal
import sys
import time

pid, seconds = int(sys.argv[1]), float(sys.argv[2])
time.sleep(seconds)
try:
    os.kill(pid, 0)
    os.killpg(pid, signal.SIGTERM)
except ProcessLookupError:
    pass
