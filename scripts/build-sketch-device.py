#!/usr/bin/env python3
"""Build isolated Sketch/BUF MAIN and boot-safe DSP placement, without a SYX."""

# ruff: noqa: E402
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(
        str(config["python"]), [str(config["python"]), "-B", __file__, *sys.argv[1:]]
    )
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument(
    "--arm-diagnostics", action="store_true", help="show first failing ARM guard"
)
p.add_argument(
    "--clock-fix",
    action="store_true",
    help="qualify the stock normal16 clock by semantic fields; requires --arm-diagnostics",
)
p.add_argument(
    "--operation-diagnostics",
    action="store_true",
    help="trace the sample operation behind BUSY; requires --arm-diagnostics, separate from --clock-fix",
)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance = doctor()
from lab.runtime import STOCK_MAIN
from lab.sketch_device import build
from lab.sketch_dsp_device import build as build_dsp

report = dict(
    status="building",
    hardware_ready=False,
    hardware_uploaded=False,
    source_hashes=provenance["source_hashes"],
    dependencies=provenance["dependencies"],
)
try:
    image, meta = build(
        STOCK_MAIN.read_bytes(),
        arm_diagnostics=a.arm_diagnostics,
        clock_fix=a.clock_fix,
        operation_diagnostics=a.operation_diagnostics,
    )
    require(
        build(
            STOCK_MAIN.read_bytes(),
            arm_diagnostics=a.arm_diagnostics,
            clock_fix=a.clock_fix,
            operation_diagnostics=a.operation_diagnostics,
        )
        == (image, meta),
        "Sketch build repeat differs",
    )
    (out / "SKETCH_MAIN.bin").write_bytes(image)
    write_json(out / "native-patches.json", meta)
    blob, dsp = build_dsp(out / "dsp")
    require(
        sha256(out / "dsp/RETIRE_BLOB.bin") == dsp["blob_sha256"], "DSP output changed"
    )
    require(source_hashes() == provenance["source_hashes"], "Build source drift")
    report.update(
        status="local-build-complete",
        cpu=dict(path="SKETCH_MAIN.bin", **meta),
        dsp=dict(path="dsp/RETIRE_BLOB.bin", bytes=len(blob), **dsp),
    )
    print(
        {
            k: meta[k]
            for k in ("reservation_bytes", "payload_bytes", "main_bytes", "sha256")
        }
    )
finally:
    write_json(out / "manifest.json", report)
