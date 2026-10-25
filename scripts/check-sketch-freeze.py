#!/usr/bin/env python3
# ruff: noqa: E402
"""Two native Sketch takes: held-SONG FREEZE pins A across BUF replacement B.

CPU/UI evidence only. Recorder input, LP0 peer and cadence are modeled; no DSP
execution, host commit, synthesized YES or direct firmware call is permitted.
"""

import argparse
import functools
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

from lab import buf_freeze as bf
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
        raise AssertionError(
            "Frozen A and current B must leave no obsolete generation to retire"
        )


report = dict(
    status="running",
    scope=__doc__,
    provenance=provenance,
    sources=sources,
    checks=[],
    calls=[],
    destination_writes=[],
    screenshots=[],
    capture_limit=2,
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
            SketchUI,
            sketch_enabled=True,
            arm_enabled=True,
            freeze_enabled=True,
            peer=peer,
        ),
    )
    from emu import panel

    fw = session.flex.fw
    session.emu._dwell_chunks = 0
    ips = session.runtime["timers"].sources[0].ips
    parts = s.payload(STOCK_MAIN.read_bytes(), arm_enabled=True, freeze_enabled=True)

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
            freeze_result=fw.u32(s.STATE + s.FREEZE_RESULT),
            freezes=fw.u32(n.STATE + 4),
            freeze_jobs=fw.u32(q.STATE + 36),
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
                sum(row["pc"] == hex(b.START) for row in report["calls"]) <= 2,
                "Capture cap",
            )
        if pc in (q.SUBMIT, n.FREEZE, 0x40043A30):
            raise AssertionError("Unexpected FREEZE/save job")
        if pc == bf.SUBMIT:
            require(
                s.FREEZE_SUBMIT
                <= fw.u32(sp)
                < s.FREEZE_SUBMIT + len(parts[s.FREEZE_SUBMIT]),
                "FREEZE must come from native Sketch action",
            )
        if pc == b.ARM_ONLY:
            require(
                s.ARM_SUBMIT <= fw.u32(sp) < s.ARM_SUBMIT + len(parts[s.ARM_SUBMIT]),
                "Sketch did not call the real shared ARM service",
            )
        if pc == 0x401AFDD4:
            require(phase == "set-normal-destination", "Sketch constructed SamplerView")

    for pc in (
        bf.SUBMIT,
        q.WORKER,
        q.BODY,
        q.DONE,
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
    tap("SONG")
    select("A", 2, lambda: fw.u32(s.STATE + s.BUF))
    phase = "empty"
    edge("SONG", "press", 850)
    edge("SONG", "release")
    check(
        "empty FREEZE refuses without setup or job",
        fw.u32(s.STATE + s.ACTION) == 15
        and fw.u32(q.STATE + 36) == 0
        and fw.u32(w.STATE + 64) == 0,
    )
    screen("01-empty-refusal")
    tap("SONG")
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
    select("D", 4, rlen)
    phase = "take-A"
    chord("FUNC", "SONG")
    until("take A recording", lambda: get(b.PHASE) == 2)
    edge("SONG", "press", 850)
    edge("SONG", "release")
    check(
        "recording FREEZE refuses without competing job",
        fw.u32(s.STATE + s.ACTION) == 14 and fw.u32(q.STATE + 36) == 0,
    )
    until("take A published", lambda: get(b.USES) == 1 and get(b.OWN) == 0, 240)
    logical = fw.u32(w.STATE + 100)
    header_a = fw.read(0x405B1368 + logical * 16, 16)
    report["take_A"] = dict(header=header_a.hex(), frames=fw.u32(w.STATE + 28))
    check(
        "take A published only to BUF 2 with normal DEST",
        fw.u32(w.DEST) == 0 and assignments() == initial_assignments,
    )
    phase = "freeze-A"
    attempts = fw.u32(s.STATE + s.FREEZES)
    edge("SONG", "press", 1600)  # Hold/repeat traffic must submit exactly once.
    edge("SONG", "release")
    until("FREEZE A completion", lambda: fw.u32(q.STATE + 32) == 1)
    wait(240)
    check(
        "one held cycle queues and completes one native FREEZE",
        fw.u32(q.STATE + 36) == fw.u32(n.STATE + 4) == 1
        and fw.u32(s.STATE + s.FREEZES) == attempts + 1
        and fw.u32(s.STATE + s.ACTION) == 13,
    )
    check(
        "FREEZE latch names BUF 2 and exact generation A",
        fw.u32(bf.STATE + bf.BUFFER) == 2
        and fw.read(bf.STATE + bf.KEY, 16) == header_a
        and fw.read(n.SNAP + 16, 16) == header_a,
    )
    snapshot_a = fw.read(n.SNAP, 64)
    frozen_slot = fw.u32(n.SNAP + 36)
    frozen_header = fw.read(0x405B1368 + frozen_slot * 16, 16)
    frozen_ref = fw.read(fw.u32(w.STATE + 68) + frozen_slot * 16, 16)
    frozen_name = fw.read(0x405B6368 + frozen_slot * 16, 16)
    check(
        "snapshot has distinct logical identity and shares original allocation",
        frozen_ref[:4] != header_a[:4]
        and frozen_header == header_a
        and fw.u32(q.STATE + 12) == frozen_slot
        and fw.u32(w.STATE + 12) == fw.u32(bf.STATE + bf.ACTIVE) == 0,
    )
    check(
        "freeze does not change recorder DEST or track assignments",
        not report["destination_writes"] and assignments() == initial_assignments,
    )
    screen("02-freeze-ready")
    tap("YES")
    screen("03-frozen-A-list")
    tap("YES")
    select("A", 3, lambda: fw.u32(s.STATE + s.BUF))
    edge("SONG", "press", 850)
    edge("SONG", "release")
    check(
        "empty selected BUF refuses without freezing selected track or prior BUF",
        fw.u32(s.STATE + s.ACTION) == 15
        and fw.u32(q.STATE + 36) == 1
        and fw.read(n.SNAP, 64) == snapshot_a,
    )
    select("A", 2, lambda: fw.u32(s.STATE + s.BUF))
    # Change modeled input only; the original native recorder still chooses
    # START/STOP and the original worker publishes B. No host commit.
    session.flex.input.source = Take(bytes(48000 * 4 * 4), True)
    phase = "replace-B"
    chord("FUNC", "SONG")
    until("take B published", lambda: get(b.USES) == 2 and get(b.OWN) == 0, 240)
    header_b = fw.read(0x405B1368 + logical * 16, 16)
    report["take_B"] = dict(header=header_b.hex(), frames=fw.u32(w.STATE + 28))
    check(
        "replacement uses a fresh generation",
        header_b[:4] != header_a[:4] and fw.u32(w.STATE + 80) == 2,
    )
    check(
        "frozen A identity association name and project reference survive B",
        fw.read(n.SNAP, 64) == snapshot_a
        and fw.read(0x405B1368 + frozen_slot * 16, 16) == frozen_header
        and fw.read(fw.u32(w.STATE + 68) + frozen_slot * 16, 16) == frozen_ref
        and fw.read(0x405B6368 + frozen_slot * 16, 16) == frozen_name,
    )
    check(
        "two native captures preserve every track assignment and normal DEST",
        get(b.STARTS) == get(b.STOPS) == get(b.USES) == 2
        and assignments() == initial_assignments
        and fw.u32(w.DEST) == 0
        and not report["destination_writes"],
    )
    screen("04-replacement-B")
    tap("YES")
    screen("05-frozen-A-after-B")
    report["freeze"] = dict(
        slot=frozen_slot,
        name=frozen_name.hex(),
        descriptor=snapshot_a.hex(),
        header=frozen_header.hex(),
        native_contexts=session.flex.freeze_contexts,
    )
    report["capture"] = dict(count=2, native_pages=len(peer.pages))
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
