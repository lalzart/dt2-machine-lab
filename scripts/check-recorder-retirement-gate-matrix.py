#!/usr/bin/env python3
"""Compose retirement diagnostics into the unchanged native replacement matrix."""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab import recorder_ack_loop as loop  # noqa: E402
from lab import recorder_retirement as observer  # noqa: E402
from lab import recorder_retirement_gate as gate  # noqa: E402
from lab.project import ROOT, require, write_json  # noqa: E402

if len(sys.argv) != 2:
    raise SystemExit("usage: check-recorder-retirement-gate-matrix.py out/runs/FRESH")
output = Path(sys.argv[1]).resolve()
old_build, old_factory = observer.build, loop.engine_class
events = []


def factory():
    original = old_factory()

    class Engine(original):
        def __init__(self, blob=None):
            self.observe_gate = blob is not None
            super().__init__(blob)

        def block_after_exchange(self):
            n = super().block_after_exchange()
            if self.observe_gate:
                s = gate.state(self)
                require(s[27] == 0, "Gate granted permission in real workflow")
                if s[10]:
                    require(s[28] == 127, "Unknown ownership hidden")
                events.append(s[:35])
            return n

    return Engine


observer.build, loop.engine_class = gate.build, factory
try:
    runpy.run_path(str(ROOT / "scripts/check-recorder-type7a-matrix.py"), run_name="__main__")
finally:
    observer.build, loop.engine_class = old_build, old_factory
    if output.is_dir():
        write_json(output / "retirement-gate.json", dict(
            native_observations=events, no_permission=True, no_reuse=True,
            original_assertions_unchanged=True, original_inputs_unchanged=True))
