#!/usr/bin/env python3
# ruff: noqa: E402
"""Two-take native Sketch/BUF DSP validation; separate zero-capture page replay.

Recorder input, SSI cadence, LP0 callback delivery and SEC reset are modeled.
No host commit, diagnostic retirement, live SEC clone, firmware/device writes.
"""

import argparse
import functools
import hashlib
import json
import math
import os
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, require, sha256, source_hashes, write_json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument(
    "--preflight",
    action="store_true",
    help="saved BUF pages and runtime; zero recordings",
)
parser.add_argument(
    "--replay", type=Path, help="replay a completed coupled run; zero recordings"
)
parser.add_argument(
    "--device-build", type=Path, help="exact sealed Sketch MAIN/DSP at device addresses"
)
parser.add_argument(
    "--setup-only",
    action="store_true",
    help="CPU-only device-address setup; zero recordings",
)
parser.add_argument(
    "--lengths",
    nargs=2,
    type=int,
    choices=(16, 32, 64),
    default=(16, 16),
    metavar=("TAKE_A_STEPS", "TAKE_B_STEPS"),
    help="native recorder lengths for the two committed takes",
)
parser.add_argument(
    "--cancel-capture",
    action="store_true",
    help="one additional LEN 64 capture, cancelled after its first native bar",
)
a = parser.parse_args()
require(not (a.preflight and a.replay), "Choose one validation mode")
require(
    not (a.device_build and (a.preflight or a.replay)),
    "Device build needs the coupled/setup mode",
)
require(not a.setup_only or a.device_build, "Setup-only is a device-address preflight")
require(
    not a.device_build or (tuple(a.lengths) == (16, 16) and not a.cancel_capture),
    "Multi-bar validation needs a fresh matching device build; use the scratch adapter",
)
require(
    not (a.preflight or a.replay)
    or (tuple(a.lengths) == (16, 16) and not a.cancel_capture),
    "Recording options require a coupled capture run",
)
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored output")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance, sources = doctor(), source_hashes()
from lab.sketch_validation import pages, playback, runtime

Engine, runtime_info = runtime(out)
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import m68k_const as k

from lab import buf_freeze as bf
from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_native_retirement as retirement
from lab import recorder_worker_code as w
from lab import sketch as s
from lab.flex_audio import baseline_pages
from lab.flex_freeze_probe import dump_pages, payload
from lab.flex_recorder import Take
from lab.flex_session import Session, stock_inputs
from lab.runtime import STOCK_MAIN
from lab.sketch_ui import SketchUI
from lab.voice_read import VoiceReader

device = None
ui_factory = SketchUI
ui_options = dict(sketch_enabled=True, arm_enabled=True, freeze_enabled=True)


def address(value):
    return value


if a.device_build:
    from lab.sketch_device_validation import AddressView, DeviceBuild, adapter, address

    device = DeviceBuild(a.device_build, STOCK_MAIN.read_bytes())
    bf, nb, n, q, w, s = map(AddressView, (bf, nb, n, q, w, s))
    ui_factory, ui_options = adapter(device), {}


class SetupComplete(Exception):
    pass


def replay_fixture(folder):
    original = json.loads((folder / "report.json").read_text())
    require(original["status"] == "pass", "Replay needs a completed coupled run")
    history_a, history_b = (
        pages(folder / "pages-A-frozen.bin"),
        pages(folder / "pages-B.bin"),
    )
    result = playback(
        out / "audio",
        stock_inputs(),
        (folder / "wire.bin").read_bytes(),
        original["logical_slot"],
        original["frozen_slot"],
        history_a,
        history_b,
    )
    write_json(
        out / "report.json",
        dict(
            status="pass",
            source=sources,
            fixture_sha256=sha256(folder / "report.json"),
            recordings_performed=0,
            result=result,
            source_stable=sources == source_hashes(),
        ),
    )


if a.replay:
    replay_fixture(a.replay.resolve())
    raise SystemExit(0)
if a.preflight:
    fixture = ROOT / "out/runs/buf-alignment-panel-20261022-04"
    old = json.loads((fixture / "report.json").read_text())
    require(
        old["status"] == "passed-native-buf-alignment-cpu", "Preflight fixture drift"
    )
    history_b = pages(fixture / "pages-2.bin")
    logical = old["cycles"][0]["slot"]
    end = next(
        i + 1
        for i, (tag, data, _) in enumerate(history_b)
        if tag == 0xFFFFFFFF
        and struct.unpack_from(">I", data)[0] == 312
        and struct.unpack_from(">I", data, 16)[0] > 0
    )
    history_a = history_b[:end]
    wire = (fixture / "tx.bin").read_bytes()[-0xABC:]
    engine = Engine()
    engine.publish(baseline_pages(stock_inputs()["lp0"]))
    engine.publish(history_a)
    for _ in range(8):
        engine.core.spi2_exchange(wire)
        engine.block_after_exchange()
    result = playback(
        out / "audio", stock_inputs(), wire, logical, 312, history_a, history_b
    )
    require(sources == source_hashes(), "Preflight source drift")
    write_json(
        out / "report.json",
        dict(
            status="pass",
            recordings_performed=0,
            fixture_sha256=sha256(fixture / "report.json"),
            result=result,
            native_blocks=engine.completed,
            sources=sources,
        ),
    )
    print("Preflight PASS: runtime and saved-page oracles, zero recordings", flush=True)
    raise SystemExit(0)


class Peer:
    def __init__(self, actual, reader):
        self.actual, self.reader, self.inner = actual, reader, None
        self.calls = 0
        self.pages, self.trace, self.publications = [], [], []
        self.pcm = hashlib.sha256()
        self.wire = b""

    def request(self):
        raise AssertionError("Two takes with frozen A must have no obsolete generation")

    def readers(self):
        return [
            (
                self.actual.core.peek(0x2412CC + lane * 0x1D8),
                self.actual.core.peek(0x2412CC + lane * 0x1D8 + 0x1B8, 1),
            )
            for lane in range(32)
        ]

    def publish(self, packets):
        for packet in packets:
            before = self.actual.slot_record(300)
            readers = self.readers()
            self.actual.publish([packet])
            require(readers == self.readers(), "LP0 redirected an existing voice")
            after = self.actual.slot_record(300)
            if before != after and after[2]:
                addresses = {0x8422B9C8 + before[0], 0x8422B9C8 + before[1]}
                retained = [
                    lane
                    for lane, (ptr, active) in enumerate(readers)
                    if active and ptr in addresses
                ]
                self.publications.append(
                    dict(
                        frame=self.calls,
                        descriptor=after,
                        retained_readers=retained,
                        pointers_preserved=True,
                    )
                )
            self.pages.append(packet)

    def exchange(self, tx):
        modeled = self.inner.exchange(tx)
        self.calls += 1
        self.wire = bytes(tx)
        if a.setup_only:
            return modeled  # Fast CPU setup gate, explicitly no native DSP blocks.
        response = self.actual.core.spi2_exchange(tx)
        self.actual.block_after_exchange()
        voice = self.reader.read(self.actual)
        self.pcm.update(voice)
        readers = self.readers()
        peaks = []
        for track in (0, 4, 5):
            samples = [
                value
                for lane in (track * 2, track * 2 + 1)
                if readers[lane][0] and readers[lane][1]
                for value in struct.unpack_from("<64f", voice, lane * 256)
            ]
            require(all(map(math.isfinite, samples)), "Nonfinite active voice PCM")
            peaks.append(max(map(abs, samples), default=0.0))
        self.trace.append(
            dict(
                frame=self.calls - 1,
                trigger=int.from_bytes(tx[0x22:0x24], "big"),
                slots=[
                    int.from_bytes(tx[0xE0 + track * 0x60 : 0xE2 + track * 0x60], "big")
                    for track in (0, 4, 5)
                ],
                peaks=peaks,
                readers=[
                    [readers[track * 2], readers[track * 2 + 1]] for track in (0, 4, 5)
                ],
            )
        )
        return response


report = dict(
    status="running",
    scope=__doc__,
    provenance=provenance,
    sources=sources,
    checks=[],
    calls=[],
    destination_writes=[],
    screenshots=[],
    cycles=[],
    capture_limit=3 if a.cancel_capture else 2,
    requested_lengths=list(a.lengths),
)
if device:
    report["device_build"] = device.identity
for name in sources:
    target = out / "frozen-sources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
session = None
phase = "setup"
rendered = bitmap = None
try:
    if device:
        blob = device.blob
        report["dsp_build"] = device.manifest["dsp"]
    else:
        blob, report["dsp_build"] = retirement.build(out / "dsp")
    actual = Engine(blob)
    actual.publish(baseline_pages(stock_inputs()["lp0"]))
    peer = Peer(actual, VoiceReader(out / "voice-reader"))

    def take(number):
        return Take(
            b"".join(
                struct.pack(
                    ">hh",
                    (i * (37 + number * 16)) % 20001 - 10000,
                    (i * (67 + number * 22)) % 16001 - 8000,
                )
                for i in range(480000 if max(a.lengths) > 16 else 240000)
            ),
            True,
        )

    session = Session(
        take(1),
        out,
        adapter_factory=functools.partial(
            ui_factory,
            **ui_options,
            peer=peer,
        ),
    )
    from emu import panel

    fw = session.flex.fw
    session.emu._dwell_chunks = 0
    ips = session.runtime["timers"].sources[0].ips
    parts = s.payload(STOCK_MAIN.read_bytes(), arm_enabled=True, freeze_enabled=True)
    if device:
        parts = {address(pc): raw for pc, raw in parts.items()}

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
        return fw.u32(nb.STATE + off)

    def rec():
        ctrl = fw.u32(nb.STATE + nb.CTRL)
        return fw.u32(fw.u32(ctrl + 16) + 0xA4) if ctrl else 0

    def state():
        return dict(
            phase=get(nb.PHASE),
            result=get(nb.RESULT),
            recorder=rec(),
            normal_dest=fw.u32(w.DEST),
            target=get(nb.DEST),
            preference=fw.u32(s.STATE + s.BUF),
            lease=fw.u32(w.STATE + 12),
            arms=get(nb.ARMS),
            starts=get(nb.STARTS),
            uses=get(nb.USES),
            ui_action=fw.u32(s.STATE + s.ACTION),
            request=fw.u32(s.STATE + s.ARM_RESULT),
            duration_bars=get(nb.DURATION_BARS),
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
        if pc == nb.START:
            require(
                sum(row["pc"] == hex(nb.START) for row in report["calls"])
                <= report["capture_limit"],
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
        if pc == nb.ARM_ONLY:
            require(
                s.ARM_SUBMIT <= fw.u32(sp) < s.ARM_SUBMIT + len(parts[s.ARM_SUBMIT]),
                "Sketch did not call the real shared ARM service",
            )
        if pc == 0x401AFDD4:
            raise AssertionError("Sketch constructed SamplerView")

    for pc in (
        bf.SUBMIT,
        q.WORKER,
        q.BODY,
        q.DONE,
        nb.ARM_ONLY,
        nb.ARM_SITE,
        nb.START,
        nb.STOP,
        nb.DISCARD,
        nb.QUEUE,
        nb.WORKER,
        nb.DONE,
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
        raise AssertionError("Sketch wrote normal recorder DEST")

    fw.uc.hook_add(UC_HOOK_MEM_WRITE, dest_write, begin=w.DEST, end=w.DEST + 3)

    def track_slot(track):
        return int.from_bytes(
            fw.read(fw.u32(0x80004704) + track * 0x450 + 0x80, 2), "big"
        )

    def select_slot(track, target):
        session.chord("TRK", f"TRIG {track + 1}")
        session.tap("SRC")
        session.tap("ENCODER D")
        current = track_slot(track)
        for _ in range((target // 128 - current // 128) % 8):
            session.tap("RIGHT")
        key = "DOWN" if target % 128 > current % 128 else "UP"
        code = next(
            code
            for code, label in session.emu.button_names.items()
            if label.upper() == key
        )
        for _ in range(abs(target % 128 - current % 128)):
            session.emu.inbox.extend((("press", code, None), ("release", code, None)))
        while session.emu.inbox:
            session.advance()
        session.advance()
        session.tap("YES")
        check(f"native selector T{track + 1} = {target}", track_slot(track) == target)

    def playing():
        return fw.u32(0x43164F94) == 1

    def live_sound(index, slot, after):
        descriptor = actual.slot_record(slot)
        pointers = {0x8422B9C8 + descriptor[0], 0x8422B9C8 + descriptor[1]}
        return any(
            row["slots"][index] == slot
            and row["peaks"][index] > 0
            and any(
                active and pointer in pointers
                for pointer, active in row["readers"][index]
            )
            for row in peer.trace[after:]
        )

    def capture(number):
        global phase
        if a.setup_only:
            device.check(fw)
            check("no old emulator arena access", not session.flex.legacy_accesses)
            check("setup has submitted no captures", get(nb.STARTS) == 0)
            screen("00-device-setup")
            report.update(
                recordings_performed=0,
                live_blocks=actual.completed,
                final=state(),
                fault_pages=len(session.emu._faulted_pages),
            )
            raise SetupComplete()
        phase = f"take-{number}"
        session.flex.input.source = take(number)
        steps = a.lengths[number - 1]
        bars = steps // 16
        select("D", steps.bit_length() - 1, rlen)
        before = get(nb.USES)
        assigned = assignments()
        until(
            "arm away from boundary",
            lambda: 3 <= int.from_bytes(fw.read(0x43164F98, 2), "big") <= 5,
        )
        chord("FUNC", "SONG")
        check(
            f"Sketch admission {number}",
            get(nb.PHASE) == 1
            and get(nb.DEST) == 1
            and fw.u32(w.DEST) == 0
            and get(nb.DURATION_BARS) == bars,
        )
        screen(f"take-{number}-len-{steps}-armed")
        until("recording", lambda: get(nb.PHASE) == 2)
        until(
            "publication",
            lambda: get(nb.USES) == before + 1 and get(nb.PHASE) == 0,
            240 * bars,
        )
        check(
            f"capture {number} preserves assignments",
            assignments() == assigned and playing(),
        )
        pcm = payload(session.flex.pages, logical)
        check(
            f"capture {number} source equals native LP0 PCM",
            pcm == session.flex.input.candidate(0, fw.u32(w.STATE + 28)).pcm,
        )
        (out / f"take-{number}.pcm").write_bytes(pcm)
        trace = session.flex.next_bar_trace
        publication = next(x for x in reversed(trace) if x.get("event") == "publish")
        started = next(x for x in reversed(trace) if x.get("pc") == nb.START)
        stopped = next(x for x in reversed(trace) if x.get("pc") == nb.STOP)
        completed = next(x for x in reversed(trace) if x.get("pc") == 0x400161FE)
        check(
            f"capture {number} stops after exactly {bars} native bars",
            stopped["serial"] - started["serial"] == bars,
        )
        elapsed = (completed["tick"] - session.flex.input.started) & 0xFFFFFFFF
        check(
            f"capture {number} contains its complete sample-clock duration",
            len(pcm) // 4 == elapsed and elapsed <= nb.MAX_CAPTURE_FRAMES,
        )
        row = dict(
            number=number,
            requested_steps=steps,
            native_bars=stopped["serial"] - started["serial"],
            frames=len(pcm) // 4,
            generation=fw.u32(0x405B1368 + logical * 16),
            publication_frame=publication["frame"],
            stop_frame=stopped["frame"],
            capture_complete_tick=completed["tick"],
            publication_tick=publication["tick"],
            capture_to_publish_ms=(
                (publication["tick"] - completed["tick"]) & 0xFFFFFFFF
            )
            / 48,
            pcm_sha256=hashlib.sha256(pcm).hexdigest(),
        )
        report["cycles"].append(row)
        print("Captured", row, flush=True)
        return row

    # Initialize empty BUFs through genuine ARM, then cancel before capture.
    tap("RECORD")
    chord("FUNC", "PLAY")
    chord("FUNC", "PAGE")
    tap("PAGE")
    tap("NO")
    tap("SRC")
    tap("RECORD")
    tap("PLAY")
    until("normal clock", lambda: get(nb.VALID) == 1)
    tap("SONG")
    select("D", 4, rlen)
    until(
        "initialization away from bar",
        lambda: int.from_bytes(fw.read(0x43164F98, 2), "big") == 3,
    )
    phase = "init-cancel"
    chord("FUNC", "SONG")
    tap("NO")
    until("initialization cancelled", lambda: get(nb.PHASE) == get(nb.OWN) == 0)
    check(
        "empty setup cancelled with zero recordings",
        get(nb.STARTS) == 0 and fw.u32(w.STATE + 80) == 0,
    )
    tap("STOP")
    tap("STOP")
    logical = fw.u32(w.STATE + 96)
    report["logical_slot"] = logical
    check(
        "BUF 1 is empty and recorder DEST remains NORMAL",
        logical == 300
        and fw.u32(w.DEST) == 0
        and fw.u32(0x405B1368 + logical * 16 + 8) == 0,
    )
    for track in (0, 4, 5):
        session.chord("TRK", f"TRIG {track + 1}")
        session.tap("SRC")
        if fw.read(fw.u32(0x80004704) + track * 0x450 + 0xD6, 1) != b"\0":
            session.chord("FUNC", "SRC")
            for _ in range(8):
                session.tap("UP")
            session.tap("YES")
            session.tap("YES")
        check(
            f"T{track + 1} ONESHOT fixture",
            fw.read(fw.u32(0x80004704) + track * 0x450 + 0xD6, 1) == b"\0",
        )
    for track in (0, 4):
        select_slot(track, logical)
        session.tap("RECORD")
        for step in (1, 5, 9, 13) if track == 0 else (1, 9):
            session.tap(f"TRIG {step}")
        session.tap("RECORD")
    initial_assignments = assignments()
    tap("PLAY")
    until("normal clock for take A", lambda: get(nb.VALID) == 1)
    tap("SONG")
    capture(1)
    until(
        "live A sounds on both shared tracks",
        lambda: all(
            live_sound(i, logical, report["cycles"][0]["publication_frame"])
            for i in (0, 1)
        ),
    )
    phase = "freeze-A"
    edge("SONG", "press", 850)
    edge("SONG", "release")
    until("native FREEZE completion", lambda: fw.u32(q.STATE + 32) == 1)
    wait(240)
    frozen = fw.u32(q.STATE + 12)
    report["frozen_slot"] = frozen
    check(
        "held SONG freezes exact selected BUF",
        frozen == 312
        and fw.u32(bf.STATE + bf.BUFFER) == 1
        and fw.u32(s.STATE + s.ACTION) == 13,
    )
    snapshot_a = fw.read(n.SNAP, 64)
    history_a = list(session.flex.pages)
    dump_pages(out / "pages-A-frozen.bin", history_a)
    check(
        "FREEZE preserves all assignments and normal DEST",
        assignments() == initial_assignments and fw.u32(w.DEST) == 0,
    )
    screen("01-frozen-A")
    tap("YES")
    screen("02-frozen-list")
    tap("NO")
    select_slot(5, frozen)
    session.tap("RECORD")
    for step in (1, 9):
        session.tap(f"TRIG {step}")
    session.tap("RECORD")
    tap("SONG")
    capture(2)
    check(
        "current B and frozen A preserve identities and shared selectors",
        fw.read(n.SNAP, 64) == snapshot_a
        and track_slot(0) == track_slot(4) == logical
        and track_slot(5) == frozen,
    )
    until(
        "all shared/frozen voices sound after B",
        lambda: all(
            live_sound(i, target, report["cycles"][1]["publication_frame"])
            for i, target in enumerate((logical, logical, frozen))
        ),
        100,
    )
    check(
        "live B publication preserves active old readers",
        len(peer.publications) == 2 and bool(peer.publications[1]["retained_readers"]),
    )
    check(
        "one FREEZE and exactly two native captures",
        fw.u32(q.STATE + 36) == 1
        and get(nb.STARTS) == get(nb.STOPS) == get(nb.USES) == 2,
    )
    if a.cancel_capture:
        phase = "cancel-long-capture"
        select("D", 6, rlen)
        committed, assigned = snapshot(), assignments()
        current_header = fw.read(0x405B1368 + logical * 16, 16)
        frozen_header = fw.read(0x405B1368 + frozen * 16, 16)
        pages_before = len(session.flex.pages)
        until(
            "arm cancellation away from boundary",
            lambda: int.from_bytes(fw.read(0x43164F98, 2), "big") == 3,
        )
        chord("FUNC", "SONG")
        until(
            "cancel candidate recording",
            lambda: get(nb.STARTS) == 3 and get(nb.PHASE) == 2,
        )
        first = get(nb.START_BAR)
        until(
            "cancel after one complete native bar",
            lambda: get(nb.LAST_BAR) == first + 1,
        )
        tap("NO")
        until("cancel candidate discarded", lambda: get(nb.PHASE) == get(nb.OWN) == 0)
        tap("SONG")
        screen("04-long-capture-cancelled")
        check(
            "cancelling an active LEN 64 preserves current B frozen A and assignments",
            get(nb.STARTS) == 3
            and get(nb.STOPS) == get(nb.USES) == 2
            and get(nb.RESULT) == -2 & 0xFFFFFFFF
            and fw.u32(s.STATE + s.ACTION) == s.ARM_CANCELLED
            and snapshot() == committed
            and assignments() == assigned
            and fw.read(0x405B1368 + logical * 16, 16) == current_header
            and fw.read(0x405B1368 + frozen * 16, 16) == frozen_header
            and len(session.flex.pages) == pages_before
            and fw.u32(w.DEST) == 0,
        )
        report["cancelled_capture"] = dict(
            requested_steps=64, native_bars_before_cancel=1, publication=False
        )
    check(
        "native recorder and loader used throughout",
        not fw.sources
        and not fw.handles
        and not fw.direct
        and session.flex.resource_hle_calls == 0,
    )
    dump_pages(out / "pages-B.bin", session.flex.pages)
    (out / "wire.bin").write_bytes(peer.wire)
    write_json(out / "voice-trace.json", peer.trace)
    report.update(
        publications=peer.publications,
        live_blocks=actual.completed,
        live_voice_sha256=peer.pcm.hexdigest(),
        native_fext_count=actual.fext_count,
        assignments=assignments(),
        initial_assignments=initial_assignments,
        freeze_contexts=session.flex.freeze_contexts,
        native_trace=session.flex.next_bar_trace,
    )
    # The entire captured control stream ran through the native SPI/SEC path.
    # Freeze saved inputs before the independent, fresh-state stock-file oracle.
    screen("03-B-current-A-frozen")
    if device:
        device.check(fw)
        check("all device canaries and native code preserved", True)
        check("no old emulator arena access", not session.flex.legacy_accesses)
        report.update(
            device_code_and_guards_preserved=True,
            legacy_accesses=session.flex.legacy_accesses,
        )
    check("sources stable", sources == source_hashes())
    report.update(
        status="pass", final=state(), fault_pages=len(session.emu._faulted_pages)
    )
except SetupComplete:
    require(sources == source_hashes(), "Setup source drift")
    report.update(status="pass", setup_only=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if session:
        report["final"] = state()
    raise
finally:
    if session:
        session.close()
    write_json(out / "report.json", report)
print(
    "Coupled Sketch validation",
    report["status"],
    "blocks",
    report.get("live_blocks"),
    flush=True,
)
