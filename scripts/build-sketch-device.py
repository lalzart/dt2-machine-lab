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
p.add_argument(
    "--buf-selector", action="store_true", help="opt-in BUF 1-4 quick sample rows"
)
p.add_argument(
    "--performance-controls",
    action="store_true",
    help="Sketch BAR/NOW and page-button exits; requires --clock-fix",
)
p.add_argument(
    "--navigation-fixes",
    action="store_true",
    help="preserve ordinary backing rows and exit Sketch on TRK+trig",
)
p.add_argument(
    "--fixed-buf-slots",
    action="store_true",
    help="fix BUF 1-4 to H124-H127; requires --navigation-fixes",
)
p.add_argument(
    "--startup-capture",
    action="store_true",
    help="capture early and defer publication until project loading completes",
)
p.add_argument(
    "--copy-shortcuts",
    action="store_true",
    help="Sketch FUNC+REC COPY and FUNC+STOP PASTE using the existing snapshot worker",
)
p.add_argument(
    "--stopped-recording",
    action="store_true",
    help="FUNC+SONG free capture and finish while stopped",
)
p.add_argument(
    "--recording-led",
    action="store_true",
    help="SONG red during actual BUF capture; requires --stopped-recording",
)
p.add_argument(
    "--monitor-labels",
    action="store_true",
    help="show stock MON values as POST/PRE instead of OFF/ON",
)
p.add_argument(
    "--freeze-h-slots",
    action="store_true",
    help="place immutable snapshots at H123..H116, refusing occupied rows",
)
p.add_argument(
    "--sketchbook-save",
    action="store_true",
    help="experimental native DSP readback and individual /Sketchbook export; requires --freeze-h-slots",
)
p.add_argument(
    "--managed-buffers",
    action="store_true",
    help="volatile per-BUF settings and status; requires the full Sketchbook profile",
)
p.add_argument(
    "--assign-popup",
    action="store_true",
    help="optional stock-style prompt after BUF publication; requires --managed-buffers",
)
p.add_argument("--buf-loading", action="store_true")
p.add_argument("--early-buf-setup", action="store_true")
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
        buf_selector=a.buf_selector,
        performance_controls=a.performance_controls,
        navigation_fixes=a.navigation_fixes,
        fixed_buf_slots=a.fixed_buf_slots,
        startup_capture=a.startup_capture,
        copy_shortcuts=a.copy_shortcuts,
        stopped_recording=a.stopped_recording,
        recording_led=a.recording_led,
        monitor_labels=a.monitor_labels,
        freeze_h_slots=a.freeze_h_slots,
        sketchbook_save=a.sketchbook_save,
        managed_buffers=a.managed_buffers,
        assign_popup=a.assign_popup,
        buf_loading=a.buf_loading,
        early_buf_setup=a.early_buf_setup,
    )
    require(
        build(
            STOCK_MAIN.read_bytes(),
            arm_diagnostics=a.arm_diagnostics,
            clock_fix=a.clock_fix,
            operation_diagnostics=a.operation_diagnostics,
            buf_selector=a.buf_selector,
            performance_controls=a.performance_controls,
            navigation_fixes=a.navigation_fixes,
            fixed_buf_slots=a.fixed_buf_slots,
            startup_capture=a.startup_capture,
            copy_shortcuts=a.copy_shortcuts,
            stopped_recording=a.stopped_recording,
            recording_led=a.recording_led,
            monitor_labels=a.monitor_labels,
            freeze_h_slots=a.freeze_h_slots,
            sketchbook_save=a.sketchbook_save,
            managed_buffers=a.managed_buffers,
            assign_popup=a.assign_popup,
            buf_loading=a.buf_loading,
            early_buf_setup=a.early_buf_setup,
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
    dsp_path = "dsp/RETIRE_BLOB.bin"
    if a.sketchbook_save:
        from lab.sketchbook_dsp import build as build_readback

        blob, dsp = build_readback(blob, dsp, out / "sketchbook-dsp")
        dsp_path = "sketchbook-dsp/SKETCHBOOK_BLOB.bin"
    require(source_hashes() == provenance["source_hashes"], "Build source drift")
    report.update(
        status="local-build-complete",
        cpu=dict(path="SKETCH_MAIN.bin", **meta),
        dsp=dict(path=dsp_path, bytes=len(blob), **dsp),
    )
    print(
        {
            k: meta[k]
            for k in ("reservation_bytes", "payload_bytes", "main_bytes", "sha256")
        }
    )
finally:
    write_json(out / "manifest.json", report)
