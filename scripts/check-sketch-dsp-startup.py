#!/usr/bin/env python3
"""Bounded OS1.16 DSP application-entry comparison, without a prepared snapshot.

Uses the existing public-register reset-value model. This is not ROM execution,
paired CPU/SHARC boot, a ready-state qualification or a physical-memory proof.
"""

# ruff: noqa: E402
import argparse
import hashlib
import json
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
p.add_argument("build", type=Path)
p.add_argument("output", type=Path)
a = p.parse_args()
provenance = doctor()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
# isort: off
from lab.runtime import LIB, STOCK_BLOB, STOCK_MAIN
from lab.sketch_device_validation import DeviceBuild
from lab.sketch_dsp_device import audit

import sharc_harness as harness
import sharc_transpile_run as native
import sharcldr
from sharc_core.values import Const
# isort: on

device = DeviceBuild(a.build, STOCK_MAIN.read_bytes())
placement = audit(device.blob)
# Same bounded reset seeds as probe-dsp-startup.py, from public ADI HWR
# figures 6-7/13/28, 32-7; tables A-15/16, A-73..76, A-80..82.
# These are initial register values, not a substitute for peripheral semantics.
resets = {0x31089400: 0, 0x31089404: 0, 0x3108B840: 0, 0x310CA2EC: 0, 0x310CA2E8: 0}
resets.update(
    {
        base + off: 0
        for base in (0x31004000, 0x31004080, 0x31004100)
        for off in (0, 0x18, 0x24, 0x30, 0x38)
    }
)
resets.update({0x310C92EC: 0, 0x310C92E8: 0})
resets.update({base + 0x0C: 0x101 for base in (0x31005000, 0x31005100, 0x31005200)})
resets.update({0x31089800 + 8 * sid: 0 for sid in range(256)})
resets.update(
    {base + off: 0 for base in (0x310C9300, 0x310CA300) for off in range(0, 24, 4)}
)
report = dict(
    status="running",
    scope=__doc__,
    captures=0,
    hardware=False,
    paired_cold_start=False,
    instruction_bound=250_000_000,
    device=device.identity,
    placement=placement,
    source_hashes=provenance["source_hashes"],
    native_library_sha256=sha256(LIB),
    reset_values={hex(k): v for k, v in resets.items()},
    arms={},
)
try:
    for label, raw in (("stock", STOCK_BLOB.read_bytes()), ("device", device.blob)):
        memory = sharcldr.LoadedMemory.from_stream(raw)
        require(
            sharcldr.entry_points(memory.blocks) == [0x120230, 0x1C1338],
            "DSP entry drift",
        )
        runner = harness._make_runner(memory, "dt2-1.16", 0x1C1338, {})
        runner.state.stack_model = runner.state.bank_model = True
        runner.state.mmrs.update({k: Const(v) for k, v in resets.items()})
        core = native.NativeCore(native.pack_image(memory), str(LIB))
        core.set_option(native.OPT_BLOCKS, 0)
        core.set_option(native.OPT_RUNTIME_DECODE, 1)
        native.to_native(core, runner.state)
        for option in (
            native.OPT_INSTRUCTION_CLOCK,
            native.OPT_SOFTWARE_INTERRUPTS,
            native.OPT_CORE_TIMER,
            native.OPT_PERIPHERAL_MODEL,
        ):
            core.set_option(option, 1)
        instructions = core.run(report["instruction_bound"])
        require(not core.halt_reason, f"{label}: {core.halt_reason}")
        require(instructions == report["instruction_bound"], "Short startup execution")
        state = core.export_state()
        write_json(out / f"{label}-state.json", state)
        record = dict(
            instructions=instructions,
            pc=core.pc(),
            halt=core.halt_reason,
            state_sha256=hashlib.sha256(
                json.dumps(state, sort_keys=True).encode()
            ).hexdigest(),
        )
        if label == "device":
            regions = []
            for lo, hi in placement["loaded_regions"]:
                if lo < 0x20080000 or lo >= 0x20100000:
                    continue
                expected = memory.read(lo, hi - lo)
                observed = bytes(core.peek(at, 1) for at in range(lo, hi))
                require(
                    observed == expected, f"Startup overwrote device DSP arena {lo:#x}"
                )
                regions.append(
                    dict(start=lo, end=hi, sha256=hashlib.sha256(observed).hexdigest())
                )
            record["arenas_unchanged"] = regions
        report["arms"][label] = record
        write_json(out / "report.json", report)
        print(label, json.dumps(record), flush=True)
        del core
    stock, candidate = (report["arms"][name] for name in ("stock", "device"))
    require(
        stock["state_sha256"] == candidate["state_sha256"],
        "Stock startup state differs",
    )
    require(source_hashes() == provenance["source_hashes"], "Startup source drift")
    report.update(status="passed-bounded-startup", stock_state_exact=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
