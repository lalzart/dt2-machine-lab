#!/usr/bin/env python3
"""Import saved resource measurements and produce a local diagnostic screen."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab.diagnostics import main  # noqa: E402

raise SystemExit(main())
