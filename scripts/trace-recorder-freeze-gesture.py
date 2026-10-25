#!/usr/bin/env python3
# ruff: noqa: E402
"""Read-only stock key-order/chord audit; installs no FREEZE gesture."""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
args = p.parse_args()
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
# isort: off
from lab.recorder_normal import StockRecorderPeer
from lab.flex_recorder import Take
from lab.flex_session import Session
from unicorn import UC_HOOK_CODE, m68k_const as k
# isort: on

sources = source_hashes()
report = dict(
    status="running",
    events=[],
    stages=[],
    binding_installed=False,
    source_hashes=sources,
)
session = None
try:
    session = Session(
        Take(bytes(2400 * 4), True), out, adapter_factory=StockRecorderPeer
    )
    fw = session.flex.fw
    current_stage = ["initial"]

    def observe(uc, pc, *_):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        event = fw.u32(sp + 4)
        key = fw.u32(event + 12)
        if key in (43, 50):
            report["events"].append(
                dict(
                    stage=current_stage[0],
                    key=key,
                    flags=fw.u32(event + 16),
                    caller=hex(fw.u32(sp)),
                    tick=session.flex.tick(),
                )
            )

    fw.uc.hook_add(UC_HOOK_CODE, observe, begin=0x401146A4, end=0x401146A4)

    def stage(name):
        current_stage[0] = name
        session.advance()
        session.screenshot(name)
        report["stages"].append(name)

    stage("01-src")
    session.button("SAMPLING", "press")
    stage("02-sampling-held")
    session.tap("ENCODER C")
    stage("03-c-push-while-sampling-held")
    session.button("SAMPLING", "release")
    stage("04-sampling-released")
    session.tap("SRC")
    session.chord("FUNC", "SAMPLING")
    stage("05-original-func-sampling")
    require(source_hashes() == sources, "Source drift")
    report["status"] = "observed"
finally:
    if session:
        session.close()
    write_json(out / "report.json", report)
