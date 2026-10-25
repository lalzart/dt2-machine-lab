#!/usr/bin/env python3
# ruff: noqa: E402
"""Observe actual OS1.16 sequencer interrupt entries. No recorder arming hook."""

import argparse
import functools
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, require, source_hashes, write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--no-sequencer-irqs", action="store_true")
a = p.parse_args()
provenance = doctor()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored output")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from unicorn import UC_HOOK_CODE

from lab import pattern_clock
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab.recorder_worker_native import NativeWorkerUI

if a.no_sequencer_irqs:
    pattern_clock.install = functools.partial(
        pattern_clock.install, sequencer_irqs=False
    )
sources = source_hashes()
write_json(out / "sources.json", sources)
for name in sources:
    target = out / "frozen-sources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
report = dict(
    status="running", provenance=provenance, no_sequencer_irqs=a.no_sequencer_irqs
)
session = None
try:
    session = Session(Take(bytes(4800 * 4), True), out, adapter_factory=NativeWorkerUI)
    fw = session.flex.fw
    session.tap("RECORD")
    session.chord("FUNC", "PLAY")
    session.chord("FUNC", "PAGE")
    session.tap("PAGE")
    session.tap("NO")
    for step in (1, 5, 9, 13):
        session.tap(f"TRIG {step}")
    session.tap("SRC")
    session.tap("RECORD")
    counts, observations = Counter(), []
    sites = (0x400D5A50, 0x400D5AEC, 0x400D7A2E)
    from lab.runtime import STOCK_MAIN

    main = STOCK_MAIN.read_bytes()
    for pc in sites:
        expected = main[pc - 0x40000400 : pc - 0x40000400 + 8]
        require(fw.read(pc, 8) == expected, "Clock hook byte drift")

    def observe(_uc, pc, *_):
        counts[hex(pc)] += 1
        if len(observations) < 2048:
            observations.append(
                dict(
                    pc=hex(pc),
                    tick=fw.u32(0x40966500),
                    guard=fw.u32(0x43158F88),
                    counter=int.from_bytes(fw.read(0x43164F98, 2), "big"),
                    pattern=fw.u32(0x4316501C),
                )
            )

    for pc in sites:
        fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc)
    session.recorder.frames.clear()
    session.recorder.ticks.clear()
    session.recorder.recording = True
    session.tap("PLAY")
    for _ in range(45):
        session.advance(10_000_000)
    session.tap("STOP")
    session.tap("STOP")
    events = [
        dict(index=i, tick=session.recorder.ticks[i])
        for i, frame in enumerate(session.recorder.frames)
        if int.from_bytes(frame[0x22:0x24], "big") & 1
    ]
    if a.no_sequencer_irqs:
        require(len(events) <= 1, "Negative clock control unexpectedly sequenced")
    else:
        require(len(events) >= 5, "Native sequence did not advance")
        require(counts["0x400d7a2e"] > 0, "No native source-57 entry")
    report.update(
        counts=dict(counts),
        events=events,
        observations=observations,
        irq_delivery=dict(session.runtime["interrupts"]),
        external_bar_events=0,
    )
    require(source_hashes() == sources, "Source drift")
    report["status"] = "passed"
    print("PASS", out / "report.json", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    if session:
        session.close()
    write_json(out / "report.json", report)
