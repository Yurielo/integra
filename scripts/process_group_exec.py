#!/usr/bin/env python3
"""Exec a command in a fresh process group (portable replacement for setsid)."""
import os
import sys

if len(sys.argv) < 2:
    raise SystemExit("usage: process_group_exec.py command [args...]")
os.setsid()
os.execvp(sys.argv[1], sys.argv[1:])
