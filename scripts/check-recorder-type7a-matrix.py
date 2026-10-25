#!/usr/bin/env python3
"""Run the unchanged matrix with explicit native panel selection before capture."""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab import flex_session  # noqa: E402
from lab.project import ROOT, read_json, require, sha256, write_json  # noqa: E402
from lab.type7a_matrix import recording_session  # noqa: E402

if len(sys.argv) != 2:
    raise SystemExit("usage: check-recorder-type7a-matrix.py out/runs/FRESH-MATRIX")
out = Path(sys.argv[1]).resolve()
contract = read_json(ROOT / "machines/sharc-type7a/corrected-matrix.json")
script = ROOT / contract["source"]
require(sha256(script) == contract["source_sha256"], "Original matrix drift")
original, events, targets_verified = flex_session.Session, [], False
flex_session.Session = recording_session(original, events)
sys.argv = [str(script), str(out)]
try:
    runpy.run_path(str(script), run_name="__main__")
    report = read_json(out / "report.json")
    require(all(report["checks"][f"record-{i}"]["track"] == 0 for i in range(1, 8)),
            "Native USE did not target selected T1")
    targets_verified = True
finally:
    flex_session.Session = original
    if out.is_dir():
        write_json(out / "stimulus.json", dict(contract=contract, events=events,
                   native_panel_only=True, host_assignment=False, assertions_unchanged=True,
                   native_targets_verified=targets_verified))
