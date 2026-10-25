#!/usr/bin/env python3
# ruff: noqa: E402
"""One native Sketch capture from empty BUF, with independent recorder DEST.

CPU/UI evidence only. Recorder input, LP0 peer and cadence are modeled; no DSP
execution, host commit, synthesized YES or direct firmware call is permitted.
"""

import argparse
import functools
import hashlib
import json
import math
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, require, source_hashes

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored runs")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance, sources = doctor(), source_hashes()
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import m68k_const as k

from lab import buf_next_bar as b
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab import sketch as s
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab.runtime import STOCK_MAIN
from lab.sketch_ui import SketchUI


class CpuPeer:
    calls = 0
    inner = None

    def __init__(self):
        self.pages = []

    def exchange(self, tx):
        self.calls += 1
        self.inner.exchange(tx)
        return bytes(len(tx))

    def publish(self, pages):
        self.pages.extend(pages)

    def request(self):
        raise AssertionError("One publication has no obsolete generation to retire")


report = dict(
    status="running",
    scope=__doc__,
    provenance=provenance,
    sources=sources,
    checks=[],
    calls=[],
    destination_writes=[],
    screenshots=[],
    capture_limit=1,
)
session = None
phase = "setup"
rendered = bitmap = None
try:
    pcm = b"".join(
        struct.pack(
            ">hh", round(9000 * math.sin(i * 0.09)), round(7000 * math.sin(i * 0.13))
        )
        for i in range(48000 * 4)
    )
    peer = CpuPeer()
    session = Session(
        Take(pcm, True),
        out,
        adapter_factory=functools.partial(
            SketchUI, sketch_enabled=True, arm_enabled=True, peer=peer
        ),
    )
    from emu import panel

    fw = session.flex.fw
    session.emu._dwell_chunks = 0
    ips = session.runtime["timers"].sources[0].ips
    parts = s.payload(STOCK_MAIN.read_bytes(), arm_enabled=True)

    def wait(ms=90):
        session.advance(max(1, round(ips * ms / 1000) - session.gui.BUDGET))

    def edge(key, kind, ms=90):
        code = next(
            c for c, label in session.emu.button_names.items() if label.upper() == key
        )
        session.emu.inbox.append((kind, code, None))
        wait(ms)

    def tap(key):
        edge(key, "press")
        edge(key, "release")

    def chord(mod, key):
        edge(mod, "press")
        tap(key)
        edge(mod, "release")

    def get(off):
        return fw.u32(b.STATE + off)

    def rec():
        ctrl = fw.u32(b.STATE + b.CTRL)
        return fw.u32(fw.u32(ctrl + 16) + 0xA4) if ctrl else 0

    def state():
        return dict(
            phase=get(b.PHASE),
            result=get(b.RESULT),
            recorder=rec(),
            normal_dest=fw.u32(w.DEST),
            target=get(b.DEST),
            preference=fw.u32(s.STATE + s.BUF),
            lease=fw.u32(w.STATE + 12),
            arms=get(b.ARMS),
            starts=get(b.STARTS),
            uses=get(b.USES),
            ui_action=fw.u32(s.STATE + s.ACTION),
            request=fw.u32(s.STATE + s.ARM_RESULT),
        )

    def check(label, value):
        require(value, label + ": " + str(state()))
        report["checks"].append(label)

    def until(label, predicate, steps=180):
        for _ in range(steps):
            if predicate():
                print(label, phase, state(), flush=True)
                return
            session.advance()
        raise AssertionError(label + ": timeout " + str(state()))

    def assignments():
        kit = fw.u32(0x80004704)
        return [fw.read(kit + i * 0x450 + 0x80, 2).hex() for i in range(16)]

    def snapshot():
        return fw.read(n.GEN, 8 * 64) + fw.read(n.SNAP, 8 * 64)

    def rlen():
        view = fw.u32(s.STATE + s.VIEW)
        wrapper = fw.u32(view + s.SETTINGS)
        return fw.u32(fw.u32(wrapper + 16) + 0x1BA)

    def select(knob, target, getter):
        for _ in range(40):
            current = getter()
            if current == target:
                return
            session.turn(knob, 10 if current < target else -10)
            wait()
        raise AssertionError(f"{knob} failed to select {target}")

    def draw_observe(uc, pc, *_):
        global bitmap, rendered
        if pc == s.DRAW:
            bitmap = fw.u32(uc.reg_read(k.UC_M68K_REG_A7) + 8)
        elif bitmap:
            rendered = panel.read(fw.m, bitmap + 16)

    for pc in (s.DRAW, s.DRAW + len(parts[s.DRAW]) - 2):
        fw.uc.hook_add(UC_HOOK_CODE, draw_observe, begin=pc, end=pc)

    def screen(name):
        wait(120)
        require(rendered is not None and fw.u32(s.STATE + s.VIEW), "No Sketch frame")
        panel.write_png(rendered, str(out / f"{name}.png"))
        (out / f"{name}.frame").write_bytes(rendered)
        report["screenshots"].append(dict(name=name, state=state()))

    def observe(uc, pc, *_):
        require(not fw.direct, "Host direct operation")
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        report["calls"].append(dict(stage=phase, pc=hex(pc), caller=hex(fw.u32(sp))))
        if pc == b.START:
            require(
                sum(row["pc"] == hex(b.START) for row in report["calls"]) <= 1,
                "Capture cap",
            )
        if pc in (q.SUBMIT, n.FREEZE, 0x40043A30):
            raise AssertionError("Unexpected FREEZE/save job")
        if pc == b.ARM_ONLY:
            require(
                s.ARM_SUBMIT <= fw.u32(sp) < s.ARM_SUBMIT + len(parts[s.ARM_SUBMIT]),
                "Sketch did not call the real shared ARM service",
            )
        if pc == 0x401AFDD4:
            require(phase == "set-normal-destination", "Sketch constructed SamplerView")

    for pc in (
        b.ARM_ONLY,
        b.ARM_SITE,
        b.START,
        b.STOP,
        b.DISCARD,
        b.QUEUE,
        b.WORKER,
        b.DONE,
        q.SUBMIT,
        n.FREEZE,
        0x40043A30,
        0x401AFDD4,
    ):
        fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc)

    def dest_write(uc, _access, at, size, value, *_):
        report["destination_writes"].append(
            dict(stage=phase, value=value, pc=hex(uc.reg_read(k.UC_M68K_REG_PC)))
        )
        require(phase == "set-normal-destination", "Sketch wrote normal recorder DEST")

    fw.uc.hook_add(UC_HOOK_MEM_WRITE, dest_write, begin=w.DEST, end=w.DEST + 3)
    initial_assignments = assignments()
    check(
        "start with NORMAL and uninitialized empty BUFs",
        fw.u32(w.DEST) == fw.u32(w.STATE + 64) == fw.u32(w.STATE + 80) == 0,
    )
    tap("SONG")
    select("A", 2, lambda: fw.u32(s.STATE + s.BUF))
    phase = "stopped-refusal"
    chord("FUNC", "SONG")
    check(
        "stopped transport refuses without starting or reserving",
        get(b.ARMS) == 0 and fw.u32(w.STATE + 64) == 0,
    )
    edge("SONG", "press", 850)
    edge("SONG", "release")
    check(
        "held SONG remains dry",
        fw.u32(s.STATE + s.ACTION) == 4 and fw.u32(n.STATE + 4) == 0,
    )
    tap("SONG")
    # The prepared master is 128 steps; use existing original controls for the
    # supported normal-16-step clock. No recorder page or destination writes.
    tap("RECORD")
    chord("FUNC", "PLAY")
    chord("FUNC", "PAGE")
    tap("PAGE")
    tap("NO")
    tap("SRC")
    tap("RECORD")
    tap("PLAY")
    until("normal clock", lambda: get(b.VALID) == 1)
    tap("SONG")
    phase = "length-refusal"
    check("prepared recorder length is MAX", rlen() == 8)
    chord("FUNC", "SONG")
    check(
        "MAX length refuses without recording",
        fw.u32(s.STATE + s.ARM_RESULT) == b.ARM_LENGTH & 0xFFFFFFFF
        and get(b.ARMS) == 0
        and fw.u32(w.STATE + 64) == 0,
    )
    screen("01-length-refusal")
    select("D", 4, rlen)
    # Request early within a bar so waiting feedback can be observed separately.
    until("mid-bar", lambda: int.from_bytes(fw.read(0x43164F98, 2), "big") == 3)
    phase = "capture"
    chord("FUNC", "SONG")
    check(
        "empty BUF 2 armed while recorder DEST remains NORMAL",
        get(b.PHASE) == 1
        and get(b.DEST) == 2
        and get(b.NORMAL_DEST) == fw.u32(w.DEST) == 0,
    )
    screen("02-armed")
    check(
        "accepted action waits for the bar on its admitted BUF",
        fw.u32(s.STATE + s.ACTION) == s.ARM_WAITING
        and fw.u32(s.STATE + s.ARM_BUF) == 2,
    )
    until("native recording", lambda: get(b.PHASE) == 2)
    screen("03-recording")
    check(
        "periodic feedback follows native recording without another key",
        fw.u32(s.STATE + s.ACTION) == s.ARM_RECORDING,
    )
    until("automatic publication", lambda: get(b.USES) == 1 and get(b.OWN) == 0, 240)
    check(
        "one native START STOP and publication",
        get(b.STARTS) == get(b.STOPS) == get(b.USES) == fw.u32(w.STATE + 80) == 1,
    )
    check("no track assignment changed", assignments() == initial_assignments)
    check(
        "normal DEST preserved through publication",
        fw.u32(w.DEST) == 0 and not report["destination_writes"],
    )
    logical = fw.u32(w.STATE + 100)
    check(
        "BUF 2 alone becomes ready",
        fw.u32(0x405B1368 + logical * 16 + 8) > 0
        and all(
            fw.u32(0x405B1368 + fw.u32(w.STATE + 96 + i * 4) * 16 + 8) == 0
            for i in (0, 2, 3)
        ),
    )
    captured = session.flex.input.completed
    require(
        captured and len(captured) // 4 == fw.u32(w.STATE + 28),
        "Native recorded length",
    )
    report["capture"] = dict(
        frames=len(captured) // 4,
        input_sha256=hashlib.sha256(captured).hexdigest(),
        logical_slot=logical,
        cache_header=fw.read(0x405B1368 + logical * 16, 16).hex(),
        native_pages=len(peer.pages),
    )
    screen("04-published")
    check(
        "ready feedback requires actual native publication",
        fw.u32(s.STATE + s.ACTION) == s.ARM_READY and fw.u32(s.STATE + s.ARM_BUF) == 2,
    )
    roots = snapshot()
    header = fw.read(0x405B1368 + logical * 16, 16)
    # Independently choose BUF 3 in the original recorder. Sketch still targets
    # its BUF 2 preference. Cancel that second request before it records.
    phase = "set-normal-destination"
    tap("SAMPLING")
    select("C", 3, lambda: session.flex.destination)
    tap("SRC")
    tap("SONG")
    until(
        "mid-bar for cancel", lambda: int.from_bytes(fw.read(0x43164F98, 2), "big") == 3
    )
    phase = "cancel"
    chord("SONG", "FUNC")
    check(
        "reverse chord arms preference independently of recorder BUF 3",
        get(b.PHASE) == 1
        and get(b.DEST) == 2
        and get(b.NORMAL_DEST) == fw.u32(w.DEST) == 3,
    )
    tap("NO")
    until("NO cancellation", lambda: get(b.OWN) == get(b.PHASE) == 0, 40)
    check(
        "NO preserves committed BUF and assignments",
        get(b.USES) == 1
        and get(b.STARTS) == 1
        and get(b.CANCELS) == 1
        and snapshot() == roots
        and fw.read(0x405B1368 + logical * 16, 16) == header
        and assignments() == initial_assignments,
    )
    check("normal recorder BUF 3 survives cancellation", fw.u32(w.DEST) == 3)
    tap("SONG")
    screen("05-after-cancel")
    check(
        "reopening after NO shows cancellation instead of old ARM acceptance",
        fw.u32(s.STATE + s.ACTION) == s.ARM_CANCELLED,
    )
    # Retain the repeat-admission check as a separate no-capture transaction.
    until(
        "mid-bar for busy", lambda: int.from_bytes(fw.read(0x43164F98, 2), "big") == 3
    )
    chord("FUNC", "SONG")
    chord("FUNC", "SONG")
    check(
        "second chord refuses without toggling capture",
        get(b.ARMS) == 3 and get(b.CANCELS) == 1 and fw.u32(s.STATE + s.ACTION) == 9,
    )
    tap("NO")
    until("busy request cancellation", lambda: get(b.OWN) == get(b.PHASE) == 0, 40)
    tap("SONG")
    wait(120)
    check(
        "later BUSY message is not overwritten by the older recording",
        fw.u32(s.STATE + s.ACTION) == 9
        and get(b.STARTS) == get(b.USES) == 1
        and get(b.CANCELS) == 2
        and snapshot() == roots
        and assignments() == initial_assignments,
    )
    check(
        "no stock ARM or synthesized YES path",
        not any(row["pc"] == hex(b.ARM_SITE) for row in report["calls"]),
    )
    check("sources stable", sources == source_hashes())
    report.update(
        status="pass", final=state(), fault_pages=len(session.emu._faulted_pages)
    )
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if session:
        report["final"] = state()
    raise
finally:
    if session:
        session.close()
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(
    json.dumps(
        {key: report[key] for key in ("status", "checks", "capture", "fault_pages")},
        indent=2,
    )
)
