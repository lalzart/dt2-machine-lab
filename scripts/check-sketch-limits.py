#!/usr/bin/env python3
# ruff: noqa: E402
"""Two bounded native captures for Sketch concurrency and populated-list checks.

Original sampler/BUF controls perform capture and FREEZE. SONG actions stay dry.
CPU/UI evidence only: recorder input, SSI cadence and LP0 boundary are modeled.
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
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k

from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab import sketch as s
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab.runtime import STOCK_MAIN
from lab.sketch_ui import SketchUI


class CpuPeer:
    """Same control-only boundary as the prior BUF CPU driver; no DSP claims."""

    calls = 0
    inner = None
    published = 0

    def exchange(self, tx):
        self.calls += 1
        self.inner.exchange(tx)
        return bytes(len(tx))

    def publish(self, pages):
        self.published += len(pages)

    def request(self):
        raise AssertionError("These two takes should create no obsolete generation")


report = dict(
    status="running",
    scope=__doc__,
    provenance=provenance,
    sources=sources,
    checks=[],
    calls=[],
    stages=[],
    capture_limit=2,
)
phase = "setup"
session = None
rendered = None
bitmap = None
texts = []
try:
    pcm = b"".join(
        struct.pack(
            ">hh", round(9000 * math.sin(i * 0.09)), round(7000 * math.sin(i * 0.13))
        )
        for i in range(48000 * 8)
    )
    peer = CpuPeer()
    session = Session(
        Take(pcm, True),
        out,
        adapter_factory=functools.partial(SketchUI, sketch_enabled=True, peer=peer),
    )
    fw = session.flex.fw
    from emu import panel

    session.emu._dwell_chunks = 0
    ips = session.runtime["timers"].sources[0].ips

    def wait(ms=100):
        session.advance(max(1, round(ips * ms / 1000) - session.gui.BUDGET))

    def edge(name, kind, ms=90):
        code = next(
            code
            for code, label in session.emu.button_names.items()
            if label.upper() == name
        )
        session.emu.inbox.append((kind, code, None))
        wait(ms)

    def tap(name):
        edge(name, "press")
        edge(name, "release")

    def chord(mod, name):
        edge(mod, "press")
        tap(name)
        edge(mod, "release")

    def until(label, predicate, steps=100):
        for _ in range(steps):
            if predicate():
                print(label, phase, flush=True)
                return
            session.advance()
        raise AssertionError(f"{label}: timeout; state={state()}")

    def check(label, predicate):
        require(predicate, label)
        report["checks"].append(label)

    def slot(track):
        return int.from_bytes(
            fw.read(fw.u32(0x80004704) + track * 0x450 + 0x80, 2), "big"
        )

    def rec():
        ctrl = session.flex.controller
        return fw.u32(fw.u32(ctrl + 16) + 0xA4) if ctrl else 0

    def state():
        return dict(
            stage=phase,
            recorder=rec(),
            buf_phase=fw.u32(nb.STATE + nb.PHASE),
            buf_result=fw.u32(nb.STATE + nb.RESULT),
            clock_valid=fw.u32(nb.STATE + nb.VALID),
            buf_uses=fw.u32(w.STATE + 80),
            freeze_count=fw.u32(n.STATE + 4),
            view=fw.u32(s.STATE + s.VIEW),
            draws=fw.u32(s.STATE + s.DRAWS),
            updates=fw.u32(s.STATE + s.UPDATES),
        )

    def screenshot(label):
        wait(120)
        raw = rendered if fw.u32(s.STATE + s.VIEW) else session.emu._panel_latch
        require(raw is not None, "No native frame")
        panel.write_png(raw, str(out / f"{label}.png"))
        (out / f"{label}.frame").write_bytes(raw)
        report["stages"].append(dict(label=label, **state()))

    def controls():
        wrapper = fw.u32(fw.u32(s.STATE + s.VIEW) + s.SETTINGS)
        data = fw.u32(wrapper + 16)
        return [fw.u32(data + offset) for offset in (0x1AE, 0x1BE, 0x1BA, 0x1B6)]

    def draw_observe(uc, pc, *_):
        global bitmap, rendered
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        if pc == s.DRAW:
            bitmap = fw.u32(sp + 8)
        elif pc == s.TEXT:
            caller = fw.u32(sp)
            if s.DRAW <= caller < s.DRAW + len(parts[s.DRAW]):
                value = (
                    fw.read(fw.u32(sp + 24), 96)
                    .split(b"\0")[0]
                    .decode("ascii", "replace")
                )
                texts.append(dict(stage=phase, text=value, recorder=rec()))
        elif bitmap:
            rendered = panel.read(fw.m, bitmap + 16)

    parts = s.payload(STOCK_MAIN.read_bytes())
    for pc in (s.DRAW, s.DRAW + len(parts[s.DRAW]) - 2, s.TEXT):
        fw.uc.hook_add(UC_HOOK_CODE, draw_observe, begin=pc, end=pc)

    def observe(uc, pc, *_):
        report["calls"].append(
            dict(
                stage=phase,
                pc=hex(pc),
                caller=hex(fw.u32(uc.reg_read(k.UC_M68K_REG_A7))),
            )
        )
        require(not fw.direct, "Host direct operation")
        if pc == nb.START:
            require(
                sum(item["pc"] == hex(nb.START) for item in report["calls"]) <= 2,
                "Capture cap exceeded",
            )
        if pc == 0x40043A30:
            raise AssertionError("Unexpected project save")

    for pc in (
        nb.START,
        nb.STOP,
        nb.DISCARD,
        nb.ARM_SITE,
        q.SUBMIT,
        w.WORKER,
        n.FREEZE,
        0x40043A30,
    ):
        fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc)

    def roots():
        return fw.read(n.GEN, 8 * 64) + fw.read(n.SNAP, 8 * 64)

    def dry_unchanged():
        return (
            len(report["calls"]),
            fw.read(q.STATE, 128),
            fw.read(w.STATE, 256),
            roots(),
        )

    def frozen_headers():
        return [
            fw.read(0x405B1368 + fw.u32(n.SNAP + i * 64 + 36) * 16, 16).hex()
            for i in range(5)
        ]

    tap("SAMPLING")
    for _ in range(16):
        if session.flex.destination == 1:
            break
        session.turn("C", 5)
        wait(80)
    until("empty BUF initialized", lambda: fw.u32(w.STATE + 64) == 1)
    logical = fw.u32(w.STATE + 96)
    check("no seed take before native manual record", fw.u32(w.STATE + 80) == 0)
    phase = "manual-capture"
    tap("YES")
    check("existing recorder started capture", rec() == 2 and session.flex.input.active)
    tap("SRC")
    tap("SONG")
    until("Sketch visible during capture", lambda: fw.u32(s.STATE + s.VIEW) != 0)
    before = controls()
    dest = session.flex.destination
    for knob in ("B", "C", "D", "E"):
        session.turn(knob, 30)
        wait(80)
    check("capture settings are protected in Sketch", controls() == before)
    selected = fw.u32(s.STATE + s.BUF)
    for _ in range(5):
        session.turn("A", 50)
        wait(100)
        if fw.u32(s.STATE + s.BUF) != selected:
            break
    check(
        "Sketch selection does not redirect active recorder",
        session.flex.destination == dest == 1
        and rec() == 2
        and fw.u32(s.STATE + s.BUF) != selected,
    )
    initial = fw.u32(s.STATE + s.DRAWS)
    wait(350)
    check(
        "native update refreshes without keys",
        fw.u32(s.STATE + s.DRAWS) > initial and fw.u32(s.STATE + s.UPDATES) > 0,
    )
    baseline = dry_unchanged()
    chord("FUNC", "SONG")
    edge("SONG", "press", 850)
    edge("SONG", "release")
    check(
        "dry ARM/FREEZE submit no jobs while recording",
        dry_unchanged() == baseline and rec() == 2,
    )
    check("busy feedback is shown", fw.u32(s.STATE + s.ACTION) == 3)
    screenshot("01-sketch-recording")
    check(
        "native recording status drawn",
        any(row["stage"] == phase and "REC:RECORD" in row["text"] for row in texts),
    )
    tap("SONG")
    check("closing Sketch leaves capture running", rec() == 2)
    tap("SAMPLING")
    tap("YES")
    until("native trim completed", lambda: rec() == 4)
    captured = session.flex.input.completed
    require(captured is not None and len(captured) > 0, "No captured PCM")
    phase = "publish-existing-controls"
    tap("YES")
    until(
        "manual BUF published",
        lambda: fw.u32(w.STATE + 80) == 1 and fw.u32(w.STATE + 12) == 0,
        180,
    )
    check("published BUF is ready", fw.u32(0x405B1368 + logical * 16 + 8) > 0)
    report["recorded_pcm_sha256"] = hashlib.sha256(captured).hexdigest()
    report["recorded_frames"] = len(captured) // 4
    # Explicit original sample selector assigns the populated logical BUF to T1.
    phase = "select-buffer"
    tap("SRC")
    chord("TRK", "TRIG 1")
    tap("ENCODER D")
    current = slot(0)
    for _ in range((logical // 128 - current // 128) % 8):
        tap("RIGHT")
    key = "DOWN" if logical % 128 > current % 128 else "UP"
    for _ in range(abs(logical % 128 - current % 128)):
        tap(key)
    tap("YES")
    check("ordinary selector explicitly selects BUF", slot(0) == logical)
    # Use the established native fixture setup; the prepared pattern's master
    # length does not satisfy the existing one-normal-16-step recorder guard.
    tap("RECORD")
    chord("FUNC", "PLAY")
    chord("FUNC", "PAGE")
    tap("PAGE")
    tap("NO")
    tap("SRC")
    tap("RECORD")
    tap("PLAY")
    until("playing transport", lambda: (fw.u32(0x43164F94) | fw.u32(0x43165010)) == 1)
    until("supported native clock", lambda: fw.u32(nb.STATE + nb.VALID) == 1)
    pattern = fw.u32(0x4316501C)
    report["pattern_master"] = fw.read(pattern + 0x1DB74, 12).hex()
    check("normal 16-step fixture", report["pattern_master"] == nb.MASTER.hex())
    assignments = [slot(i) for i in range(16)]
    phase = "freeze-existing-controls"
    for index in range(5):
        before_done = fw.u32(q.STATE + 32)
        chord("SAMPLING", session.emu.button_names[43].upper())
        until(
            f"freeze {index + 1}",
            lambda before_done=before_done: fw.u32(q.STATE + 32) == before_done + 1,
            60,
        )
        check(f"committed snapshot {index + 1}", fw.u32(n.SNAP + index * 64) == 1)
    check(
        "FREEZE leaves assignments exact", [slot(i) for i in range(16)] == assignments
    )
    headers = frozen_headers()
    registry = roots()
    phase = "browse-frozen"
    tap("SONG")
    until("Sketch reopened", lambda: fw.u32(s.STATE + s.VIEW) != 0)
    # Set supported LEN for the second, original next-bar cancellation case.
    for _ in range(24):
        value = controls()[2]
        if value == 4:
            break
        session.turn("D", 10 if value < 4 else -10)
        wait(90)
    check("LEN 16 selected before original ARM", controls()[2] == 4)
    tap("YES")
    screenshot("02-frozen-page-1")
    tap("DOWN")
    screenshot("03-frozen-page-2")
    visible = [
        row["text"]
        for row in texts
        if row["stage"] == phase and row["text"][:3].isdigit()
    ]
    expected = [fw.u32(n.SNAP + i * 64 + 36) for i in range(5)]
    report["visible_frozen_rows"] = visible
    check(
        "both pages display all five native snapshots",
        all(
            any(row.startswith(f"{slot_:03d} ") for row in visible)
            for slot_ in expected
        ),
    )
    check(
        "browsing has no ownership/assignment side effects",
        roots() == registry
        and frozen_headers() == headers
        and [slot(i) for i in range(16)] == assignments,
    )
    tap("YES")
    tap("SONG")
    phase = "next-bar-cancel"
    chord("SAMPLING", "YES")
    check("original next-bar ARM admitted", fw.u32(nb.STATE + nb.PHASE) in (1, 2))
    until(
        "original next-bar capture active",
        lambda: fw.u32(nb.STATE + nb.PHASE) == 2,
        180,
    )
    tap("SONG")
    until("Sketch visible during next-bar", lambda: fw.u32(s.STATE + s.VIEW) != 0)
    screenshot("04-next-bar-recording")
    tap("STOP")
    until(
        "STOP cancels original transaction",
        lambda: fw.u32(nb.STATE + nb.OWN) == 0 and fw.u32(nb.STATE + nb.PHASE) == 0,
        100,
    )
    check(
        "canceled take did not publish",
        fw.u32(w.STATE + 80) == 1 and fw.u32(nb.STATE + nb.CANCELS) == 1,
    )
    check(
        "STOP preserved committed/frozen samples",
        roots() == registry
        and frozen_headers() == headers
        and [slot(i) for i in range(16)] == assignments,
    )
    screenshot("05-after-cancel")
    report.update(
        status="pass",
        final=state(),
        source_stable=sources == source_hashes(),
        snapshots=expected,
        pcm_pages=peer.published,
        starts=sum(item["pc"] == hex(nb.START) for item in report["calls"]),
        fault_pages=len(session.emu._faulted_pages),
    )
    require(report["source_stable"], "Sources changed during run")
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if session:
        report["final"] = state()
    raise
finally:
    if session:
        session.close()
    report["text_trace"] = texts
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(
    json.dumps(
        {
            key: report[key]
            for key in ("status", "checks", "starts", "snapshots", "fault_pages")
        },
        indent=2,
    )
)
