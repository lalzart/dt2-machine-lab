#!/usr/bin/env python3
"""Run the existing cold-boot, capture, FREEZE and export proof with managed BUF.

Uses exactly the same checked DSP, stock filesystem and independent PCM oracle.
No project persistence, upload or hardware control is performed.
"""

import runpy
import sys
from pathlib import Path

if "--managed-buffers" not in sys.argv:
    sys.argv.append("--managed-buffers")
runpy.run_path(
    str(Path(__file__).with_name("check-sketchbook-save.py")), run_name="__main__"
)
