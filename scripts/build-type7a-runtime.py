#!/usr/bin/env python3
"""Build an isolated conditional-MODIFY runtime; no baseline replacement."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.type7a_runtime import build  # noqa: E402

if len(sys.argv) != 2:
    raise SystemExit("usage: build-type7a-runtime.py out/runs/FRESH-BUILD")
print(build(sys.argv[1]), flush=True)
