#!/usr/bin/env python3
# ruff: noqa: E402
"""Bounded native Sketch panel/gesture check. Never starts a recording."""

import argparse
import functools
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, require, source_hashes

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--disabled", action="store_true")
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored runs")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance = doctor()
frozen_sources = source_hashes()
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import m68k_const as k

from lab import buf_freeze as bf
from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab import sketch as s
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab.runtime import STOCK_MAIN
from lab.sketch_ui import SketchUI


class PanelPeer:
    calls = 0
    inner = None

    def exchange(self, tx):
        self.calls += 1
        return self.inner.exchange(tx)

    def request(self):
        raise AssertionError("Dry UI requested retirement")

    def publish(self, pages):
        raise AssertionError("Dry UI published PCM")


report = dict(
    status="running",
    provenance=provenance,
    disabled=a.disabled,
    checks=[],
    events=[],
    calls={},
)
session = None
try:
    session = Session(
        Take(bytes(48000 * 4), True),
        out,
        adapter_factory=functools.partial(
            SketchUI, sketch_enabled=not a.disabled, peer=PanelPeer()
        ),
    )
    fw = session.flex.fw
    session.emu._dwell_chunks = 0
    ips = session.runtime["timers"].sources[0].ips

    def wait(ms=100):
        session.advance(max(1, round(ips * ms / 1000) - session.gui.BUDGET))

    def edge(key, kind, ms=120):
        code = next(
            c for c, name in session.emu.button_names.items() if name.upper() == key
        )
        session.emu.inbox.append((kind, code, None))
        wait(ms)

    def tap(key):
        edge(key, "press")
        edge(key, "release")

    def check(label, predicate):
        require(predicate, label)
        report["checks"].append(label)

    def get(field):
        return fw.u32(s.STATE + field)

    rendered = None
    drawing_bitmap = None

    def draw_observe(uc, pc, *_):
        global rendered, drawing_bitmap
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        if pc == s.DRAW:
            drawing_bitmap = fw.u32(sp + 8)
        elif drawing_bitmap:
            from emu import panel

            rendered = panel.read(fw.m, drawing_bitmap + 16)

    if not a.disabled:
        draw_end = s.DRAW + len(s.payload(STOCK_MAIN.read_bytes())[s.DRAW]) - 2
        fw.uc.hook_add(UC_HOOK_CODE, draw_observe, begin=s.DRAW, end=s.DRAW)
        fw.uc.hook_add(UC_HOOK_CODE, draw_observe, begin=draw_end, end=draw_end)

    def screenshot(name):
        from emu import panel

        wait(160)
        raw = (
            rendered
            if not a.disabled and fw.u32(s.STATE + s.VIEW)
            else session.emu._panel_latch
        )
        require(raw is not None, "No native frame")
        panel.write_png(raw, str(out / f"{name}.png"))
        (out / f"{name}.frame").write_bytes(raw)
        report.setdefault("screenshots", []).append(
            dict(
                name=name,
                after_sketch_draw=bool(not a.disabled and fw.u32(s.STATE + s.VIEW)),
                pixels=sum(byte.bit_count() for byte in raw),
            )
        )

    hooks = []

    def trace_key(uc, pc, *_):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        if pc == 0x40114624:
            code, flags = fw.u32(sp + 8), fw.u32(sp + 12)
        else:
            event = fw.u32(sp + 8)
            code, flags = fw.u32(event + 12), fw.u32(event + 16)
        if code in (24, 17, 10, 12, 21):
            report["events"].append(
                dict(pc=hex(pc), key=code, flags=flags, tick=fw.u32(0x47DDEC1C))
            )

    for pc in (0x40114624, s.INPUT):
        hooks.append(fw.uc.hook_add(UC_HOOK_CODE, trace_key, begin=pc, end=pc))
    forbidden = {
        nb.ARM_ONLY: "shared BUF ARM admission",
        bf.SUBMIT: "shared BUF FREEZE admission",
        nb.ARM_SITE: "recorder-arm",
        nb.START: "recorder-start",
        nb.STOP: "recorder-stop",
        nb.DISCARD: "recorder-discard",
        q.SUBMIT: "freeze-submit",
        w.WORKER: "buf-worker",
        n.FREEZE: "freeze",
        0x4002D438: "assignment-refresh",
        0x40043A30: "save-project",
        0x401AFDD4: "sampler-factory",
        0x400856D0: "song-popup",
        0x40081BEA: "song-editor",
    }

    def observe(uc, pc, *_):
        name = forbidden[pc]
        report["calls"][name] = report["calls"].get(name, 0) + 1
        # SAMPLING later is intentional; Song popup is expected opt-out.
        allowed = (name == "sampler-factory" and report.get("normal_check")) or (
            a.disabled and name == "song-popup"
        )
        require(allowed, f"Unexpected side effect: {name}")

    for pc in forbidden:
        hooks.append(fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc))
    if not a.disabled:

        def action(uc, access, at, size, value, *_):
            if at == s.STATE + s.ACTION:
                report["events"].append(
                    dict(
                        action=value,
                        buffer=get(s.LATCH),
                        pc=hex(uc.reg_read(k.UC_M68K_REG_PC)),
                    )
                )

        hooks.append(
            fw.uc.hook_add(
                UC_HOOK_MEM_WRITE,
                action,
                begin=s.STATE + s.ACTION,
                end=s.STATE + s.ACTION + 3,
            )
        )
    wait(200)
    screenshot("00-stock")
    if a.disabled:
        tap("SONG")
        screenshot("01-stock-song")
        check(
            "opt-out preserves stock Song factory",
            report["calls"].get("song-popup") == 1,
        )
        check(
            "opt-out leaves Sketch unmapped",
            bytes(fw.read(0x4005DC58, 6))
            == bytes.fromhex("4ef9") + (0x10F01000).to_bytes(4, "big"),
        )
    else:
        backend_before = {
            hex(at): fw.read(at, size).hex()
            for at, size in (
                (w.STATE, 256),
                (q.STATE, 128),
                (n.STATE, 128),
                (nb.STATE, 128),
            )
        }
        edge("SONG", "press")
        check("tap defers navigation until release", get(s.VIEW) == 0)
        edge("SONG", "release")
        check("tap creates independent native View", get(s.VIEW) != 0)
        screenshot("01-sketch-empty")
        wrapper = fw.u32(get(s.VIEW) + s.SETTINGS)
        data = fw.u32(wrapper + 16)

        def settings_values():
            return [fw.u32(data + offset) for offset in (0x1AE, 0x1BE, 0x1BA, 0x1B6)]

        shared_before = settings_values()
        original_buf = get(s.BUF)
        for _ in range(4):
            session.turn("A", 10)
        check("encoder A selects a remembered BUF", get(s.BUF) > original_buf)
        selected = get(s.BUF)
        check("Sketch BUF leaves normal recorder DEST alone", fw.u32(w.DEST) == 0)
        check(
            "opening/BUF selection preserve shared recorder settings",
            settings_values() == shared_before,
        )

        def turn_to(encoder, index, target, delta):
            for _ in range(16):
                if settings_values()[index] == target:
                    return
                session.turn(
                    encoder, delta if settings_values()[index] < target else -delta
                )
                wait(100)
            raise AssertionError(
                f"{encoder} did not reach {target}: {settings_values()}"
            )

        turn_to("B", 0, 18, 127)
        turn_to("C", 1, 1, 10)
        turn_to("D", 2, 4, 10)
        turn_to("E", 3, 1, 20)
        check(
            "B/C/D/E edit shared SRC/CHAN/LEN/MON through native setters",
            settings_values() == [18, 1, 4, 1],
        )
        report["shared_settings"] = settings_values()
        screenshot("02-selected")
        tap("SONG")
        check("tap closes through native destruction", get(s.VIEW) == 0)
        tap("SONG")
        check("selection survives native view recreation", get(s.BUF) == selected)
        tap("YES")
        screenshot("03-frozen-list")
        check("YES opens secondary read-only frozen list", get(s.PAGE) == 1)
        tap("YES")
        # Both chord orders, hold milestone/repeats, and releases.
        for first, second in (("FUNC", "SONG"), ("SONG", "FUNC")):
            before = get(s.ARMS)
            view = get(s.VIEW)
            edge(first, "press")
            edge(second, "press", 300)
            edge(second, "release")
            edge(first, "release")
            check(
                f"{first} first arms once without navigation",
                get(s.ARMS) == before + 1
                and get(s.VIEW) == view
                and get(s.OWN) == 0
                and get(s.FUNC_OWN) == 0,
            )
        screenshot("04-dry-arm")
        before = get(s.FREEZES)
        edge("SONG", "press", 850)
        check("native hold milestone freezes once", get(s.FREEZES) == before + 1)
        wait(300)
        edge("SONG", "release")
        check(
            "held release never toggles navigation",
            get(s.VIEW) != 0 and get(s.FREEZES) == before + 1 and get(s.OWN) == 0,
        )
        screenshot("05-dry-freeze-empty")
        edge("SONG", "press")
        tap("STOP")
        edge("SONG", "release")
        check(
            "STOP cancels pending navigation and passes through",
            get(s.ACTION) == 7 and get(s.VIEW) != 0 and get(s.OWN) == 0,
        )
        tap("NO")
        check("NO closes Sketch", get(s.VIEW) == 0)
        report["normal_check"] = True
        tap("SAMPLING")
        screenshot("06-normal-recorder")
        check("normal recorder DEST remains NORMAL", fw.u32(w.DEST) == 0)
        check(
            "normal recorder creates its original SamplerView",
            report["calls"].get("sampler-factory") == 1,
        )
        check("no capture PCM", session.flex.input.captured == 0)
        backend_after = {
            hex(at): fw.read(at, size).hex()
            for at, size in (
                (w.STATE, 256),
                (q.STATE, 128),
                (n.STATE, 128),
                (nb.STATE, 128),
            )
        }
        check(
            "dry actions preserve transaction state; STOP/NO reach cancellation",
            all(
                backend_before[key] == value
                for key, value in backend_after.items()
                if key != hex(nb.STATE)
            )
            and bytes.fromhex(backend_after[hex(nb.STATE)])[: nb.CANCEL]
            == bytes.fromhex(backend_before[hex(nb.STATE)])[: nb.CANCEL]
            and bytes.fromhex(backend_after[hex(nb.STATE)])[nb.CANCEL + 4 :]
            == bytes.fromhex(backend_before[hex(nb.STATE)])[nb.CANCEL + 4 :]
            and fw.u32(nb.STATE + nb.CANCEL) == 1,
        )
        report.update(
            selected_buf=selected,
            draws=get(s.DRAWS),
            arms=get(s.ARMS),
            freezes=get(s.FREEZES),
        )
    check("source files stable for complete run", frozen_sources == source_hashes())
    report.update(
        status="pass",
        fault_pages=len(session.emu._faulted_pages),
        instructions=session.emu.stats["instrs"],
    )
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if session:
        report["native_state"] = (
            {
                name: session.flex.fw.u32(s.STATE + getattr(s, name))
                for name in (
                    "BUF",
                    "VIEW",
                    "OWN",
                    "FUNC_OWN",
                    "ARMS",
                    "FREEZES",
                    "ACTION",
                    "DRAWS",
                )
            }
            if not a.disabled
            else {}
        )
    raise
finally:
    if session:
        session.close()
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
