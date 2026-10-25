#!/usr/bin/env python3
"""Run a lab script explicitly with one isolated conditional-MODIFY runtime."""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.type7a_runtime import activate  # noqa: E402

if len(sys.argv) < 4 or sys.argv[2] != "--":
    raise SystemExit("usage: with-type7a-runtime.py BUILD -- SCRIPT [ARG ...]")
activate(sys.argv[1])
script, sys.argv = sys.argv[3], sys.argv[3:]
runpy.run_path(script, run_name="__main__")
