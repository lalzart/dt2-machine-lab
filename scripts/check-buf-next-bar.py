#!/usr/bin/env python3
# ruff: noqa: E402
"""Native next-bar BUF capture and publication with original queued loading.

Capture, LP0 callback entry, CPU/DSP cadence and SEC reset contents are modeled.
No host retirement call, pause certificate, diagnostic copy or completion write.
"""

import argparse
import array
import hashlib
import math
import os
import shutil
import struct
import sys
import wave
from collections import Counter, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, require, sha256, source_hashes, write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--cpu-only", action="store_true")
p.add_argument("--no-clock", action="store_true")
p.add_argument("--cancel-before-bar", action="store_true")
p.add_argument(
    "--continuous",
    action="store_true",
    help="one empty-BUF session, native cleanup, frozen A, at most 15 recordings",
)
p.add_argument(
    "--prior-attempts",
    type=int,
    default=0,
    help="recording attempts already consumed from the total cap of 15",
)
p.add_argument(
    "--continuous-recordings",
    type=int,
    help="remaining recordings in this session; total including prior attempts <=15",
)
p.add_argument(
    "--alignment",
    action="store_true",
    help="empty BUF, shared selector, performance edits and publication-only flow",
)
a = p.parse_args()
require(
    not a.continuous or not (a.cpu_only or a.no_clock or a.cancel_before_bar),
    "Continuous reuse needs the native DSP/clock; no control-only mode",
)
if a.continuous:
    a.alignment = True
require(0 <= a.prior_attempts < 15, "Prior attempts outside the 15-recording cap")
SESSION_RECORDINGS = (
    15 - a.prior_attempts
    if a.continuous_recordings is None
    else a.continuous_recordings
)
require(
    1 <= SESSION_RECORDINGS <= 15 - a.prior_attempts,
    "Requested recordings exceed the total cap of 15",
)
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored runs")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance = doctor()

import plusdrive_check as check
import tools.plusdrive as pd

from lab import buf_auto_retirement as auto
from lab import buf_next_bar as nb
from lab import buf_performance as perf
from lab import recorder_ack_loop as loop
from lab import recorder_freeze_code as generations
from lab import recorder_freeze_worker_code as q
from lab import recorder_native_retirement as t
from lab import recorder_worker_code as w
from lab.buf_next_bar_ui import NextBarUI
from lab.flex_audio import baseline_pages
from lab.flex_dsp_probe import control
from lab.flex_freeze_probe import dump_pages, payload
from lab.flex_heap import MALLOC_RETURN, inspect_heap
from lab.flex_lite import FlexDsp
from lab.flex_recorder import Take
from lab.flex_session import Session as OriginalSession
from lab.flex_session import stock_inputs
from lab.runtime import STOCK_MAIN
from lab.type7a_matrix import recording_session
from lab.voice_read import VoiceReader

events = []
Session = recording_session(OriginalSession, events)
sources = source_hashes()
write_json(out / "sources.json", sources)
for name in sources:
    target = out / "frozen-sources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
report = dict(
    status="running",
    provenance=provenance,
    scope=__doc__,
    checks={},
    cycles=[],
    retirements=[],
    audio={},
    native_return=True,
    host_retirement=False,
    host_certificate=False,
)
session = ref_fw = heap_profile = None
CAPTURE_LIMIT = 15


class Peer:
    def __init__(self, actual, stock):
        self.actual, self.stock = actual, stock
        self.calls = self.age = 0
        self.inner = None
        self.mode = self.next_mode = None
        self.history = []
        self.stale = []
        self.trace = []
        self.delay = deque()
        self.reordered = None
        self.last = 0
        self.dsp_state = t.contract()["constants"]["DSP_STATE"]
        self.pcm = hashlib.sha256()
        self.tx = bytearray()
        self.rx = bytearray()
        self.counts = []
        self.diagnostics = []
        self.track1 = []
        self.publications = []
        self.retained_readers = []

    def request(self):
        self.mode, self.age = self.next_mode, 0
        self.delay = deque([0] * (4 if self.mode == "delay" else 1))
        self.reordered = None

    def publish(self, pages):
        for page in pages:
            before = self.actual.slot_record(300)
            readers = [
                (
                    self.actual.core.peek(0x2412CC + i * 0x1D8),
                    self.actual.core.peek(0x2412CC + i * 0x1D8 + 0x1B8, 1),
                )
                for i in range(32)
            ]
            self.actual.publish([page])
            after = self.actual.slot_record(300)
            if before != after:
                unchanged = readers == [
                    (
                        self.actual.core.peek(0x2412CC + i * 0x1D8),
                        self.actual.core.peek(0x2412CC + i * 0x1D8 + 0x1B8, 1),
                    )
                    for i in range(32)
                ]
                require(unchanged, "LP0 publication redirected an existing voice")
                if after[2] and len(self.publications) == 1:
                    old = self.publications[0]["descriptor"]
                    addresses = {0x8422B9C8 + old[0], 0x8422B9C8 + old[1]}
                    self.retained_readers = [
                        i
                        for i, (pointer, active) in enumerate(readers)
                        if active and pointer in addresses
                    ]
                    require(
                        self.retained_readers, "No active old reader at replacement"
                    )
                    require(
                        after[:2] != old[:2],
                        "New allocation aliases the frozen old PCM",
                    )
                    # Do not clone a live SEC peripheral: native state import
                    # omits its internal state. Old-reader PCM has a separate
                    # captured-publication/stock-file oracle.
                if after[2]:
                    self.publications.append(
                        dict(
                            frame=self.calls,
                            descriptor=after,
                            readers_unchanged=unchanged,
                        )
                    )
            self.stock.publish([page])
            for slot in (300, 312):
                require(
                    self.actual.slot_record(slot) == self.stock.slot_record(slot),
                    "Public descriptor parity",
                )

    def exchange(self, tx):
        if self.inner:
            self.inner.exchange(tx)
        self.calls += 1
        self.age += 1
        self.tx.extend(tx)
        rx = self.actual.core.spi2_exchange(tx)
        stock_rx = self.stock.core.spi2_exchange(tx)
        require(
            rx[:24] + rx[25:] == stock_rx[:24] + stock_rx[25:],
            "Non-carrier reply changed",
        )
        b = rx[24]
        self.history.append(b)
        wire = bytearray(rx)
        if self.mode == "delay":
            self.delay.append(b)
            wire[24] = self.delay.popleft()
        elif self.mode == "drop" and self.age == 17:
            wire[24] = 0
        elif self.mode == "duplicate" and self.age == 17:
            wire[24] = self.last
        elif self.mode == "reorder":
            # One-byte latency supplies a genuine adjacent transposition,
            # without inventing a future native reply or dropping a fragment.
            self.delay.append(b)
            if self.age == 17:
                self.reordered = self.delay.popleft()
                wire[24] = self.delay.popleft()
            elif self.age == 18:
                wire[24] = self.reordered
            else:
                wire[24] = self.delay.popleft()
        elif self.mode == "corrupt":
            wire[24] = b ^ 1
        elif self.mode == "stale":
            wire[24] = self.stale[(self.age - 1) % len(self.stale)]
        elif self.mode == "zero":
            wire[24] = 0
        self.last = b
        self.counts.append(
            [e.block_after_exchange() for e in (self.actual, self.stock)]
        )
        voice = voice_reader.read(self.actual)
        stock_voice = voice_reader.read(self.stock)
        if self.calls < 8 or self.calls % 256 == 0:
            require(
                voice == self.actual.voices() and stock_voice == self.stock.voices(),
                "Batched/scalar voice read mismatch",
            )
        require(
            voice == stock_voice,
            "Voice PCM diverged from original stock execution",
        )
        self.pcm.update(voice)
        active = [
            bool(
                self.actual.core.peek(0x2412CC + lane * 0x1D8)
                and self.actual.core.peek(0x2412CC + lane * 0x1D8 + 0x1B8, 1)
            )
            for lane in (0, 1)
        ]
        samples = [
            value
            for lane in (0, 1)
            if active[lane]
            for value in struct.unpack_from("<64f", voice, lane * 256)
        ]
        require(all(map(math.isfinite, samples)), "Nonfinite active T1 voice PCM")
        self.track1.append(
            dict(
                frame=self.calls - 1,
                trigger=bool(int.from_bytes(tx[0x22:0x24], "big") & 1),
                trigger_mask=int.from_bytes(tx[0x22:0x24], "big"),
                slot=int.from_bytes(tx[0xE0:0xE2], "big"),
                slot5=int.from_bytes(tx[0xE0 + 4 * 0x60 : 0xE2 + 4 * 0x60], "big"),
                active=active,
                peak=max(map(abs, samples), default=0.0),
            )
        )
        self.trace.append([self.calls, self.mode, b, wire[24]])
        self.rx.extend(wire)
        base = self.dsp_state
        if self.age < 5 or self.age % 32 == 0:
            self.diagnostics.append(
                [self.calls] + [self.actual.core.peek(base + i * 4) for i in range(8)]
            )
        return bytes(wire)


class ContinuousPeer:
    """One live native DSP; independent file oracles run at bookends.

    This peer transports native replies unchanged. It never grants retirement.
    The large paired-DSP fault-injection comparator remains in Peer above.
    """

    def __init__(self, actual):
        self.actual, self.inner = actual, None
        self.calls = self.requests = 0
        self.pcm = hashlib.sha256()
        self.tx = bytearray()
        self.rx = bytearray()
        self.track1, self.trace, self.publications = [], [], []

    def request(self):
        self.requests += 1

    def publish(self, pages):
        for page in pages:
            before = self.actual.slot_record(300)
            readers = self.readers()
            self.actual.publish([page])
            require(readers == self.readers(), "LP0 changed an existing voice reader")
            after = self.actual.slot_record(300)
            if before != after and after[2]:
                self.publications.append(
                    dict(frame=self.calls, descriptor=after, readers_unchanged=True)
                )

    def readers(self):
        return [
            (
                self.actual.core.peek(0x2412CC + i * 0x1D8),
                self.actual.core.peek(0x2412CC + i * 0x1D8 + 0x1B8, 1),
            )
            for i in range(32)
        ]

    def exchange(self, tx):
        if self.inner:
            self.inner.exchange(tx)
        self.calls += 1
        self.tx[:] = tx  # Last complete wire frame is enough for file oracles.
        rx = self.actual.core.spi2_exchange(tx)
        self.actual.block_after_exchange()
        voice = voice_reader.read(self.actual)
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
            require(all(map(math.isfinite, samples)), "Nonfinite active BUF voice")
            peaks.append(max(map(abs, samples), default=0.0))
        self.track1.append(
            dict(
                frame=self.calls - 1,
                trigger=bool(int.from_bytes(tx[0x22:0x24], "big") & 1),
                trigger_mask=int.from_bytes(tx[0x22:0x24], "big"),
                slot=int.from_bytes(tx[0xE0:0xE2], "big"),
                slot5=int.from_bytes(tx[0x260:0x262], "big"),
                slot6=int.from_bytes(tx[0x2C0:0x2C2], "big"),
                peaks=peaks,
            )
        )
        self.rx[:] = rx
        return rx


def pcm(number):
    return Take(
        b"".join(
            struct.pack(
                ">hh",
                (i * (37 + number * 16)) % 20001 - 10000,
                (i * (67 + number * 22)) % 16001 - 8000,
            )
            for i in range(12000 if number == 1 else 240000)
        ),
        True,
    )


def allocations():
    begin, end = fw.u32(0x405A0F64), fw.u32(0x405A0F68)
    return [
        dict(start=fw.u32(x + 16), size=fw.u32(x + 20), aliases=fw.u32(x + 48))
        for x in range(begin, end, 52)
    ]


def nodes():
    result = []
    at = fw.u32(w.STATE)
    while at:
        require(at not in result and len(result) < 9, "Metadata unbounded")
        result.append(at)
        require(fw.u32(at + 20) == 0, "Retained CPU source PCM")
        at = fw.u32(at)
    return result


def record(number):
    seq_before = len(session.flex.sequence_trace)
    start_frame = peer.calls
    if number > 1:
        require(playing(), "Pattern stopped before recording")
    session.flex.input.source = pcm(number)
    before = fw.u32(w.STATE + 80)
    session.record()
    session.tap("YES")
    for _ in range(20):
        if fw.u32(w.STATE + 80) == before + 1:
            break
        session.advance()
    require(fw.u32(w.STATE + 80) == before + 1, "Native USE did not complete")
    session.flex.sync_observation()
    row = dict(session.flex.current)
    row["id"] = fw.u32(0x405B1368 + row["slot"] * 16)
    row["private"] = fw.u32(w.STATE + 72)
    row["pcm"] = payload(session.flex.pages, row["slot"])
    expected = session.flex.input.candidate(
        fw.u32(w.STATE + 24), fw.u32(w.STATE + 24) + row["frames"]
    ).pcm
    require(row["pcm"] == expected, "Native recorder/page PCM mismatch")
    require(
        not fw.sources
        and not fw.handles
        and not fw.direct
        and session.flex.resource_hle_calls == 0,
        "Host transaction used",
    )
    report["cycles"].append(
        dict(
            number=number,
            start_frame=start_frame,
            token=row["id"],
            slot=row["slot"],
            private=row["private"],
            allocations=allocations(),
            nodes=nodes(),
            heap_free=inspect_heap(fw.read).free_bytes,
            allocation=row["allocation"],
            private_descriptors={
                str(i): peer.actual.slot_record(i)
                for i in range(304, 312)
                if not a.cpu_only
            },
            frame=peer.calls,
        )
    )
    (out / f"candidate-{number}.pcm").write_bytes(row["pcm"])
    dump_pages(out / f"pages-{number}.bin", session.flex.pages)
    print("record", number, hex(row["id"]), "frame", peer.calls, flush=True)
    if number > 1:
        require(playing(), "Pattern stopped during record/trim/USE")
        require(
            len(session.flex.sequence_trace) > seq_before,
            "No native sequence during recording",
        )
        require(
            any(x["trigger"] for x in peer.track1[start_frame:]),
            "No native T1 notes during record/trim/USE",
        )
    return row


def playing():
    return (fw.u32(0x43164F94) | fw.u32(0x43165010)) == 1


def wait_for(label, predicate, steps=80):
    for _ in range(steps):
        if predicate():
            print(label, "frame", peer.calls, flush=True)
            return
        session.advance()
    raise RuntimeError(f"{label}: bounded wait expired; policy={policy_state()}")


def policy_state():
    return [fw.u32(auto.STATE + i * 4) for i in range(10)]


def freeze():
    before = fw.u32(q.STATE + 32)
    kit = fw.u32(0x80004704)
    assignments = [fw.read(kit + i * 0x450 + 0x80, 2) for i in range(16)]
    c_name = session.emu.button_names[43]
    report["freeze_key"] = c_name
    session.chord("SAMPLING", c_name)
    wait_for("native FREEZE chord", lambda: fw.u32(q.STATE + 32) == before + 1, 24)
    require(
        len(session.flex.native_freeze_requests) == 1, "No single native FREEZE request"
    )
    require(fw.u32(perf.STATE + perf.REQUESTS) == 1, "Gesture did not request FREEZE")
    require(
        assignments == [fw.read(kit + i * 0x450 + 0x80, 2) for i in range(16)],
        "FREEZE changed track assignments",
    )
    slot = fw.u32(q.STATE + 12)
    require(0 < slot < 1024 and playing(), "FREEZE failed/stopped playback")
    session.screenshot("01-native-freeze-playing")
    return slot


def pattern():
    # All notes/transport are edited through original panel events.
    wait_for(
        "original USE UI completed",
        lambda: fw.u32(w.STATE + 8) == fw.u32(w.STATE + 12) == 0,
        20,
    )
    session.tap("SRC")
    session.chord("TRK", "TRIG 1")
    session.tap("RECORD")
    session.chord("FUNC", "PLAY")
    session.chord("FUNC", "PAGE")
    session.tap("PAGE")
    session.tap("NO")
    for step in (1, 5, 9, 13):
        session.tap(f"TRIG {step}")
    session.tap("SRC")
    session.tap("RECORD")
    session.chord("TRK", "TRIG 1")
    before = len(session.flex.sequence_trace)
    start_frame = peer.calls
    session.tap("PLAY")
    wait_for(
        "native pattern advances",
        lambda: playing() and len(session.flex.sequence_trace) > before + 12,
        24,
    )
    ptr = fw.u32(0x4316501C)
    report["pattern"] = dict(
        pointer=ptr, master=fw.read(ptr + 0x1DB74, 12).hex(), start_frame=start_frame
    )


def exact_audio(item, history, label=None):
    """Independent original CPU disk load -> stock ONESHOT oracle."""
    global ref_fw
    label = str(item["generation"]) if label is None else label
    play_slot = item["slot"]
    folder = out / f"reference-{label}"
    folder.mkdir()
    with wave.open(str(folder / "sample.wav"), "wb") as f:
        f.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        pcm_le = b"".join(
            item["pcm"][i : i + 2][::-1] for i in range(0, len(item["pcm"]), 2)
        )
        f.writeframes(pcm_le)
    card = out / f"reference-{label}.img"
    entries = pd.build(str(folder), str(card), main_os=STOCK_MAIN.read_bytes())
    snap = (
        ROOT.parent
        / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap"
    )
    require(
        sha256(snap)
        == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
        "Oracle snapshot drift",
    )
    ref_fw = check.Firmware(card, snap, STOCK_MAIN)
    try:
        ref_fw.call(0x40154358, [])
        check.check_mount(ref_fw, entries[0]["ref"])
        loaded = check.check_load(ref_fw, entries[0]["ref"], play_slot)
        require(
            loaded["load_d0"] == 0
            and all(
                check.sent_pcm_matches(
                    loaded, pd.build_native_sample(item["pcm"], True)
                )
            ),
            "Stock file oracle failed",
        )
        ref_pages = list(ref_fw.pages)
    finally:
        ref_fw.close()
        ref_fw = None
    take, reference = FlexDsp(), FlexDsp()
    if a.continuous:
        # Reuse the existing guarded register-FEXT adapter at direct oracle
        # entry points too. No live SEC state is exported or cloned.
        from types import MethodType

        from lab.pattern_dsp import PatternDsp

        for engine in (take, reference):
            engine.fallbacks = Counter()
            engine.call = MethodType(PatternDsp.call, engine)
    for engine in (take, reference):
        engine.publish(baseline)
    take.publish(history)
    reference.publish(ref_pages)
    chunks = []
    for i in range(48):
        frame = control(wire, play_slot, trigger=i == 0)
        x = array.array("f", take.frame(frame)).tobytes()
        y = array.array("f", reference.frame(frame)).tobytes()
        require(x == y, "Reused ONESHOT differs from stock-file PCM")
        chunks.append(x)
    data = b"".join(chunks)
    require(any(struct.unpack(f"<{len(data) // 4}f", data)), "Silent oracle")
    (out / f"audio-{label}.f32").write_bytes(data)
    return dict(exact=True, blocks=48, sha256=hashlib.sha256(data).hexdigest())


class CpuPeer:
    """Control-only native probe; no SHARC playback evidence."""

    def __init__(self):
        self.calls = 0
        self.inner = None
        self.tx = bytearray()
        self.track1 = []

    def exchange(self, tx):
        self.inner.exchange(tx)
        self.tx.extend(tx)
        self.calls += 1
        self.track1.append(
            dict(
                trigger=bool(int.from_bytes(tx[0x22:0x24], "big") & 1),
                trigger_mask=int.from_bytes(tx[0x22:0x24], "big"),
                slot=int.from_bytes(tx[0xE0:0xE2], "big"),
                slot5=int.from_bytes(tx[0xE0 + 4 * 0x60 : 0xE2 + 4 * 0x60], "big"),
            )
        )
        return bytes(len(tx))

    def publish(self, pages):
        pass

    def request(self):
        raise AssertionError("No obsolete unpinned generation in this two-take probe")


def state():
    return {
        name: fw.u32(nb.STATE + getattr(nb, name))
        for name in (
            "PHASE",
            "RESULT",
            "ARMS",
            "STARTS",
            "STOPS",
            "USES",
            "CANCELS",
            "DEST",
            "TRACK",
            "KIT",
            "EPOCH",
            "CTRL",
            "POOL",
            "CLOCK_EPOCH",
            "AFTER",
            "START_BAR",
            "START_EDGE",
            "START_TICK",
            "STOP_EDGE",
            "STOP_TICK",
            "JOB_RESULT",
            "CANCEL",
            "OWN",
            "SERIAL",
            "CEPOCH",
            "LAST_STEP",
            "VALID",
            "PUBLISH_TICK",
            "QUEUE_TICK",
        )
    }


def track_slot(track):
    return int.from_bytes(fw.read(fw.u32(0x80004704) + track * 0x450 + 0x80, 2), "big")


def native_edit(track, page, delta=16):
    session.chord("TRK", f"TRIG {track + 1}")
    session.tap(page)
    base = fw.u32(0x80004704) + track * 0x450
    before = fw.read(base, 0x450)
    changed = []
    # A fixed direction can become a clamped no-op. Try the reverse direction
    # before counting an actual edit; a harmless UI no-op must not abort capture.
    directions = (delta, -delta) if a.continuous else (delta,)
    for direction in directions:
        for _ in range(4):
            session.turn("A", direction)
            session.advance()
            after = fw.read(base, 0x450)
            changed = [
                i
                for i in range(0x450)
                if i not in (0x80, 0x81) and before[i] != after[i]
            ]
            if changed:
                break
        if changed:
            break
    phase = fw.u32(nb.STATE + nb.PHASE)
    require(phase in (1, 2), f"Capture left armed/recording phase during {page}")
    require(changed or a.continuous, f"No native {page} edit during capture")
    report.setdefault("parameter_edits", []).append(
        dict(
            track=track + 1,
            page=page,
            changed=changed,
            phase=phase,
            requested_delta=delta,
            applied_delta=direction,
            no_op=not bool(changed),
        )
    )


def select_slot(track, target):
    """Original sample selector, including selection of an empty logical BUF."""
    session.chord("TRK", f"TRIG {track + 1}")
    session.tap("SRC")
    session.tap("ENCODER D")
    current = track_slot(track)
    for _ in range((target // 128 - current // 128) % 8):
        session.tap("RIGHT")
    key = "DOWN" if target % 128 > current % 128 else "UP"
    count = abs(target % 128 - current % 128)
    code = next(
        k for k, name in session.emu.button_names.items() if name.upper() == key
    )
    # Queue ordinary panel presses; DigiKit retains its normal dwell pacing.
    # This avoids a whole 4M-instruction pause after every browser arrow.
    for _ in range(count):
        session.emu.inbox.extend((("press", code, None), ("release", code, None)))
    while session.emu.inbox:
        session.advance()
    session.advance()
    session.screenshot(f"selector-t{track + 1}-{target}")
    session.tap("YES")
    require(track_slot(track) == target, "Stock selector did not retain logical BUF")


def aligned_capture(number):
    require(number <= CAPTURE_LIMIT, "Recording cap exceeded")
    session.flex.input.source = pcm(number + 1)
    before = fw.u32(w.STATE + 80)
    assignments = [track_slot(i) for i in range(16)]
    wait_for(
        "arm away from boundary",
        lambda: 3 <= int.from_bytes(fw.read(0x43164F98, 2), "big") <= 5,
    )
    session.chord("SAMPLING", "YES")
    require(fw.u32(nb.STATE + nb.PHASE) == 1, "Global empty/current BUF did not arm")
    # Actual stock encoder edits and selected-track changes, not host kit writes.
    delta = -16 if a.continuous and number % 2 == 0 else 16
    native_edit(5, "FLTR", delta)
    wait_for("native capture start", lambda: fw.u32(nb.STATE + nb.PHASE) == 2)
    native_edit(5, "SRC", delta)
    native_edit(1, "AMP", delta)
    wait_for(
        "automatic PCM publication",
        lambda: fw.u32(w.STATE + 80) == before + 1 and fw.u32(nb.STATE + nb.PHASE) == 0,
        180,
    )
    require(
        assignments == [track_slot(i) for i in range(16)],
        "Recording changed a track assignment",
    )
    require(playing(), "Performance edits/capture stopped pattern")
    session.flex.sync_observation()
    row = dict(session.flex.current)
    row.update(id=fw.u32(0x405B1368 + row["slot"] * 16), private=fw.u32(w.STATE + 72))
    row["pcm"] = payload(session.flex.pages, row["slot"])
    require(
        row["pcm"] == session.flex.input.candidate(0, row["frames"]).pcm,
        "Published PCM differs from captured source",
    )
    require(
        not fw.sources
        and not fw.handles
        and not fw.direct
        and session.flex.resource_hle_calls == 0,
        "Host commit/loader used",
    )
    s = state()
    edge = next(
        x
        for x in reversed(session.flex.next_bar_trace)
        if x.get("event") == "bar" and x["tick"] == s["STOP_EDGE"]
    )
    publication = next(
        x for x in reversed(session.flex.next_bar_trace) if x.get("event") == "publish"
    )
    capture_done = next(
        x for x in reversed(session.flex.next_bar_trace) if x.get("pc") == 0x400161FE
    )
    first_trigger = next(
        (
            i
            for i in range(edge["frame"], len(peer.track1))
            if peer.track1[i]["trigger"]
        ),
        None,
    )
    report["cycles"].append(
        dict(
            number=number,
            token=row["id"],
            slot=row["slot"],
            private=row["private"],
            frames=row["frames"],
            state=s,
            stop_to_publish_ticks=(s["PUBLISH_TICK"] - s["STOP_TICK"]) & 0xFFFFFFFF,
            capture_complete_tick=capture_done["tick"],
            capture_to_publish_ticks=(s["PUBLISH_TICK"] - capture_done["tick"])
            & 0xFFFFFFFF,
            modeled_capture_to_publish_ms=(
                (s["PUBLISH_TICK"] - capture_done["tick"]) & 0xFFFFFFFF
            )
            / 48,
            sample_tick_hz=48000,
            input_ticks_per_frame=session.flex.input.ticks_per_frame,
            assignments=assignments,
            frame=peer.calls,
            stop_edge_frame=edge["frame"],
            publish_frame=publication["frame"],
            first_following_bar_trigger_frame=first_trigger,
            first_following_bar_trigger_after_publication=first_trigger is not None
            and first_trigger > publication["frame"],
        )
    )
    (out / f"candidate-{number}.pcm").write_bytes(row["pcm"])
    dump_pages(out / f"pages-{number}.bin", session.flex.pages)
    print("published", number, hex(row["id"]), "frame", peer.calls, flush=True)
    return row


def continuous_workflow(first, frozen_slot, logical):
    """Complete the same native musical session; never request host retirement."""
    report["recording_cap"] = CAPTURE_LIMIT
    report["prior_attempts"] = a.prior_attempts
    report["session_recordings"] = SESSION_RECORDINGS
    report["scope"] += " Single live DSP; independent stock-file bookend oracles."
    releases = []
    report["native_releases"] = releases

    def observe_unload(uc, _pc, *_):
        if fw.u32(t.STATE + t.ACTIVE_UNLOAD) != 1:
            return
        slot = fw.u32(uc.reg_read(k.UC_M68K_REG_A7) + 4)
        start, size = fw.u32(t.STATE + t.START), fw.u32(t.STATE + t.SIZE)
        lo = 0x8422B9C8 + start - t.observer.constants()["POOL_START"]
        hi = lo + size
        require(
            not any(active and lo <= ptr < hi for ptr, active in peer.readers()),
            "Native unload has an active reader",
        )
        releases.append(
            dict(
                token=fw.u32(t.STATE + t.TOKEN),
                slot=slot,
                start=start,
                size=size,
                frame=peer.calls,
            )
        )

    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as k

    session.flex.hooks.append(
        fw.uc.hook_add(
            UC_HOOK_CODE,
            observe_unload,
            begin=generations.UNLOAD,
            end=generations.UNLOAD,
        )
    )

    def snapshot(number):
        live = allocations()
        registry = [
            [fw.u32(generations.GEN + i * 64 + j * 4) for j in range(16)]
            for i in range(8)
        ]
        state_ = dict(
            number=number,
            frame=peer.calls,
            allocations=live,
            dsp_pcm_bytes=sum(x["size"] for x in live),
            heap_free=inspect_heap(fw.read).free_bytes,
            nodes=nodes(),
            registry=registry,
            policy=policy_state(),
            native_releases=list(releases),
            frozen_descriptor=peer.actual.slot_record(frozen_slot),
        )
        require(
            len(live) <= len(report["initial_allocations"]) + 2,
            "Settled DSP allocation count grew beyond frozen/current roots",
        )
        report.setdefault("memory", []).append(state_)
        write_json(
            out / "progress.json",
            dict(
                recordings=len(report["cycles"]),
                cap=CAPTURE_LIMIT,
                memory=report["memory"],
                releases=releases,
                publication_ticks=[
                    x["capture_to_publish_ticks"] for x in report["cycles"]
                ],
            ),
        )
        write_json(out / f"sequence-{number}.json", session.flex.sequence_trace)
        session.flex.sequence_trace.clear()  # Bound only host evidence storage.
        print(
            "memory",
            number,
            state_["dsp_pcm_bytes"],
            "bytes",
            len(live),
            "allocations",
            len(releases),
            "releases",
            flush=True,
        )

    # FREEZE was made from A. Select it independently and give it native notes.
    select_slot(5, frozen_slot)
    session.tap("RECORD")
    for step in (1, 9):
        session.tap(f"TRIG {step}")
    session.tap("RECORD")
    frozen_descriptor = peer.actual.slot_record(frozen_slot)
    require(frozen_descriptor[2] > 0, "Empty frozen descriptor")
    assignments = [track_slot(i) for i in range(16)]
    snapshot(1)
    global wire
    wire = bytes(peer.tx)
    report["audio"]["initial-A"] = exact_audio(
        first, list(session.flex.pages), "initial-A"
    )
    last = first
    for number in range(2, SESSION_RECORDINGS + 1):
        wait_for(
            "native recorder/cleanup idle",
            lambda: fw.u32(w.STATE + 12) == 0 and fw.u32(auto.STATE + auto.ACTIVE) == 0,
        )
        last = aligned_capture(number)
        require(
            assignments == [track_slot(i) for i in range(16)],
            "Recording reassigned a live/frozen track",
        )
        if number >= 3:
            wait_for(
                "native obsolete allocation reclaimed",
                lambda: (
                    sum(bool(fw.u32(generations.GEN + i * 64)) for i in range(8)) == 2
                    and fw.u32(w.STATE + 12) == 0
                    and fw.u32(auto.STATE + auto.ACTIVE) == 0
                ),
                200,
            )
        require(
            peer.actual.slot_record(frozen_slot) == frozen_descriptor,
            "Frozen PCM descriptor changed",
        )
        require(not fw.slot(first["private"])["empty"], "Frozen A allocation released")
        snapshot(number)
    wire = bytes(peer.tx)
    report["audio"]["last-live"] = exact_audio(
        last, list(session.flex.pages), "last-live"
    )
    report["audio"]["late-frozen-A"] = exact_audio(
        dict(first, slot=frozen_slot), list(session.flex.pages), "late-frozen-A"
    )
    require(
        len({x["token"] for x in report["cycles"]}) == SESSION_RECORDINGS,
        "Generation identity repeated",
    )
    require(
        all(
            any(x["page"] == page and x["changed"] for x in report["parameter_edits"])
            for page in ("FLTR", "SRC", "AMP")
        ),
        "No actual parameter edit evidence for a performance page",
    )
    for track, mask, field in ((1, 1, "slot"), (5, 16, "slot5"), (6, 32, "slot6")):
        rows = [
            x
            for x in peer.track1[report["cycles"][1]["publish_frame"] :]
            if x["trigger_mask"] & mask
        ]
        target = frozen_slot if track == 6 else logical
        require(
            rows and all(x[field] == target for x in rows),
            "Native BUF trigger slot changed",
        )
        lane = {1: 0, 5: 1, 6: 2}[track]
        # A note's first control frame can be silent during its envelope attack.
        # Check the rendered interval, not just frames carrying a trigger bit.
        require(
            any(
                x["peaks"][lane] > 0
                for x in peer.track1[report["cycles"][1]["publish_frame"] :]
            ),
            "Silent shared/frozen pattern track",
        )
    report["native_releases"] = releases
    report["dsp_publications"] = peer.publications
    report["live_voice_pcm_sha256"] = peer.pcm.hexdigest()
    report["live_dsp_blocks"] = peer.calls
    report["status"] = "passed-continuous-native-buf"


def aligned_workflow():
    require(
        not a.no_clock and not a.cancel_before_bar, "Use focused controls separately"
    )
    session.tap("STOP")
    session.tap("STOP")
    if a.continuous:
        # A fixture restriction of the existing retirement mechanism, not a
        # new recorder admission requirement.
        machine_changes = []
        for track in range(16):
            kit = fw.u32(0x80004704)
            if fw.read(kit + track * 0x450 + 0xD6, 1) == b"\0":
                continue
            session.chord("TRK", f"TRIG {track + 1}")
            session.tap("SRC")
            session.chord("FUNC", "SRC")
            for _ in range(8):
                session.tap("UP")
            session.tap("YES")
            session.tap("YES")
            require(
                fw.read(kit + track * 0x450 + 0xD6, 1) == b"\0",
                "Native ONESHOT setup failed",
            )
            machine_changes.append(track + 1)
        report["oneshot_fixture_changes"] = machine_changes
        session.chord("TRK", "TRIG 1")
    session.tap("SAMPLING")
    for _ in range(14):
        if session.flex.destination == 1:
            break
        session.turn("C", 5)
    wait_for("native empty-buffer reservation", lambda: fw.u32(w.STATE + 64) == 1)
    logical = fw.u32(w.STATE + 96)
    require(
        fw.u32(w.STATE + 80) == 0 and fw.slot(logical)["empty"],
        "BUF was manually primed",
    )
    report["empty_buf"] = dict(
        slot=logical, accepted=0, key=fw.read(0x405B1368 + logical * 16, 16).hex()
    )
    require(
        session.flex.recorder_settings is not None,
        "Native recorder settings were not observed",
    )
    settings = session.flex.recorder_settings + 0x1AE
    report["pool_settings_pointer"] = fw.u32(w.STATE + 68) - 36
    report["rlen_settings_pointer"] = settings
    report["rlen_values"] = []
    session.screenshot("rlen-before")
    for _ in range(24):
        value = fw.u32(settings + 12)
        report["rlen_values"].append(value)
        if value == nb.RLEN:
            break
        session.turn("F", 16 if value < nb.RLEN else -16)
    session.screenshot("rlen-after")
    require(fw.u32(settings + 12) == nb.RLEN, "Native R.LEN did not reach 16 steps")
    report["capture_settings"] = fw.read(settings, 36).hex()
    session.advance()
    session.advance()
    session.screenshot("rlen-16-empty-buf")
    session.tap("SRC")
    for track in (0, 4):
        session.chord("TRK", f"TRIG {track + 1}")
        live = fw.u32(0x80004704) + track * 0x450
        if fw.read(live + 0xD6, 1) != b"\0":
            session.chord("FUNC", "SRC")
            for _ in range(8):
                session.tap("UP")
            session.tap("YES")
            session.tap("YES")
        require(fw.read(live + 0xD6, 1) == b"\0", "Test reader is not ONESHOT")
        select_slot(track, logical)
    report["checks"]["empty-selector-t1-t5"] = True
    pattern()
    session.chord("TRK", "TRIG 5")
    session.tap("RECORD")
    for step in (1, 9):
        session.tap(f"TRIG {step}")
    session.tap("RECORD")
    session.chord("TRK", "TRIG 6")
    first = aligned_capture(1)
    session.chord("TRK", "TRIG 1")
    frozen_slot = freeze()
    if a.continuous:
        continuous_workflow(first, frozen_slot, logical)
        return
    session.chord("TRK", "TRIG 6")
    second = aligned_capture(2)
    require(
        first["slot"] == second["slot"] == logical and first["id"] != second["id"],
        "Logical identity/generation conflated",
    )
    require(track_slot(0) == track_slot(4) == logical, "Shared BUF assignments changed")
    require(not fw.slot(first["private"])["empty"], "Frozen allocation was released")
    session.chord("TRK", "TRIG 6")
    select_slot(5, frozen_slot)
    report["checks"]["frozen-selector"] = True
    if not a.cpu_only:
        report["audio"]["current-B"] = exact_audio(
            second, list(session.flex.pages), "current-B"
        )
        report["audio"]["frozen-A"] = exact_audio(
            dict(first, slot=frozen_slot), list(session.flex.pages), "frozen-A"
        )
        report["checks"]["exact-all-32-voice-buffers"] = dict(
            blocks=peer.calls, sha256=peer.pcm.hexdigest()
        )
        require(peer.retained_readers, "No old readers during replacement")
        report["checks"]["old-reader-pointers-preserved"] = dict(
            readers=peer.retained_readers,
            pcm_scope="Separate captured-publication replay; no live SEC clone",
        )
        report["dsp_publications"] = peer.publications
    for track, mask, field in ((1, 1, "slot"), (5, 16, "slot5")):
        require(
            any(
                x["trigger_mask"] & mask and x[field] == logical
                for x in peer.track1[report["cycles"][1]["publish_frame"] :]
            ),
            f"No new-generation T{track} trigger",
        )
    report["checks"]["ordinary-edits-and-selection-preserved"] = True
    report["checks"]["publication-without-track-assignment"] = True
    report["status"] = (
        "passed-native-buf-alignment-cpu"
        if a.cpu_only
        else "passed-coupled-native-buf-alignment"
    )


try:
    nb.contract()
    perf.contract()
    auto.contract()
    t.contract()
    if a.cpu_only:
        peer = CpuPeer()
    else:
        blob, metadata = t.build(out / "dsp")
        report["build"] = metadata
        voice_reader = VoiceReader(out / "voice-reader")
        Engine = loop.engine_class()
        actual = Engine(blob)
        stock = None if a.continuous else Engine()
        baseline = baseline_pages(stock_inputs()["lp0"])
        for engine in (actual,) if stock is None else (actual, stock):
            engine.publish(baseline)
        peer = ContinuousPeer(actual) if a.continuous else Peer(actual, stock)
    session = Session(
        pcm(1),
        out,
        adapter_factory=lambda *args, **kw: NextBarUI(
            *args, peer=peer, clock_enabled=not a.no_clock, **kw
        ),
    )
    fw = session.flex.fw
    if a.continuous:
        # Observe the native heap at completed malloc boundaries. The broader
        # HeapTrace pointer-size ledger does not cover GUI realloc paths and
        # must not abort a musical session on inferred free-size accounting.
        from unicorn import UC_HOOK_CODE
        from unicorn import m68k_const as k

        initial_free = inspect_heap(fw.read).free_bytes
        heap_profile = dict(
            initial_free=initial_free,
            minimum_free=initial_free,
            malloc_samples=0,
            largest_capture_request=0,
        )

        def observe_malloc(uc, _pc, *_):
            free = inspect_heap(fw.read).free_bytes
            heap_profile["minimum_free"] = min(heap_profile["minimum_free"], free)
            heap_profile["malloc_samples"] += 1
            if fw.u32(nb.STATE + nb.OWN):
                request = fw.u32(uc.reg_read(k.UC_M68K_REG_A7) + 4)
                heap_profile["largest_capture_request"] = max(
                    heap_profile["largest_capture_request"], request
                )

        session.flex.hooks.append(
            fw.uc.hook_add(
                UC_HOOK_CODE, observe_malloc, begin=MALLOC_RETURN, end=MALLOC_RETURN
            )
        )
        report["initial_allocations"] = allocations()
    if a.alignment:
        aligned_workflow()
    else:
        machine_changes = []
        for track in range(16):
            kit = fw.u32(0x80004704)
            if fw.read(kit + track * 0x450 + 0xD6, 1) != b"\0":
                session.chord("TRK", f"TRIG {track + 1}")
                session.tap("SRC")
                session.chord("FUNC", "SRC")
                for _ in range(8):
                    session.tap("UP")
                session.tap("YES")
                session.tap("YES")
                require(
                    fw.read(kit + track * 0x450 + 0xD6, 1) == b"\0",
                    "Native ONESHOT setup failed",
                )
                machine_changes.append(track + 1)
        report["checks"]["native-oneshot-context"] = machine_changes
        session.chord("TRK", "TRIG 1")
        session.tap("STOP")
        session.tap("STOP")
        session.tap("SAMPLING")
        for _ in range(14):
            if session.flex.destination == 1:
                break
            session.turn("C", 5)
        session.tap("SRC")
        first = record(1)
        pattern()
        frozen_slot = freeze()
        wait_for(
            "arm away from boundary",
            lambda: 3 <= int.from_bytes(fw.read(0x43164F98, 2), "big") <= 5,
            80,
        )
        session.flex.input.source = pcm(2)
        before = fw.u32(w.STATE + 80)
        report["before_arm"] = dict(
            frame=peer.calls, tick=session.flex.tick(), state=state()
        )
        session.chord("SAMPLING", "YES")
        report["after_arm"] = dict(
            frame=peer.calls, tick=session.flex.tick(), state=state()
        )
        if a.no_clock:
            require(
                fw.u32(nb.STATE + nb.ARMS) == 0
                and fw.u32(nb.STATE + nb.RESULT) == 0xFFFFFFFF,
                "Missing-clock request did not refuse",
            )
            for _ in range(80):
                session.advance()
            require(
                fw.u32(nb.STATE + nb.STARTS) == fw.u32(nb.STATE + nb.USES) == 0,
                "Clockless capture/publication",
            )
            require(
                fw.u32(w.STATE + 80) == before and not session.flex.input.active,
                "Clockless record mutated BUF",
            )
            report["status"] = "passed-native-no-clock-control"
        else:
            require(
                fw.u32(nb.STATE + nb.ARMS) == 1 and fw.u32(nb.STATE + nb.PHASE) == 1,
                "Native chord did not arm",
            )
            if a.cancel_before_bar:
                session.tap("STOP")
                session.tap("STOP")
                wait_for(
                    "pending arm canceled", lambda: fw.u32(nb.STATE + nb.PHASE) == 0
                )
                session.tap("PLAY")
                for _ in range(80):
                    session.advance()
                require(
                    fw.u32(nb.STATE + nb.STARTS) == fw.u32(nb.STATE + nb.USES) == 0,
                    "Canceled arm restarted capture",
                )
                require(
                    fw.u32(w.STATE + 80) == before, "Canceled arm changed current take"
                )
                report["status"] = "passed-native-stop-cancel-control"
            else:
                wait_for(
                    "one-bar capture and automatic USE",
                    lambda: (
                        fw.u32(nb.STATE + nb.USES) == 1
                        and fw.u32(nb.STATE + nb.PHASE) == 0
                    ),
                    180,
                )
                require(
                    fw.u32(w.STATE + 80) == before + 1, "Automatic assignment count"
                )
                require(playing(), "Automatic capture stopped native pattern")
                s = state()
                bar_receipts = [
                    x for x in session.flex.next_bar_trace if x.get("event") == "bar"
                ]
                require(
                    len(bar_receipts) >= 2
                    and all(x["step"] == 1 and x["pulse"] == 0 for x in bar_receipts),
                    "Bar receipt is not the native first-step edge",
                )
                require(
                    s["ARMS"] == s["STARTS"] == s["STOPS"] == s["USES"] == 1,
                    "Automatic stages repeated",
                )
                require(
                    s["START_BAR"] == report["after_arm"]["state"]["AFTER"] + 1,
                    "Wrong start boundary",
                )
                require(
                    s["START_TICK"] - s["START_EDGE"] <= nb.LATENCY
                    and s["STOP_TICK"] - s["STOP_EDGE"] <= nb.LATENCY,
                    "Late bar service",
                )
                session.flex.sync_observation()
                second = dict(session.flex.current)
                second["pcm"] = payload(session.flex.pages, second["slot"])
                second["id"] = fw.u32(0x405B1368 + second["slot"] * 16)
                second["private"] = fw.u32(w.STATE + 72)
                require(
                    second["slot"] == first["slot"] and second["id"] != first["id"],
                    "BUF identity did not advance",
                )
                require(
                    fw.u32(w.STATE + 24) == 0
                    and second["pcm"]
                    == session.flex.input.candidate(0, second["frames"]).pcm,
                    "Automatic recorder/page PCM mismatch",
                )
                require(
                    not fw.sources
                    and not fw.handles
                    and not fw.direct
                    and session.flex.resource_hle_calls == 0,
                    "Host BUF orchestration",
                )
                starts = [x for x in session.flex.next_bar_trace if x["pc"] == nb.START]
                stops = [x for x in session.flex.next_bar_trace if x["pc"] == nb.STOP]
                require(
                    len(starts) == len(stops) == 1,
                    "Not one native controller start/stop",
                )
                require(
                    starts[0]["sr"] & 0x700 != 0x700
                    and stops[0]["sr"] & 0x700 != 0x700,
                    "Capture ran under masked ISR context",
                )
                report["automatic_capture"] = dict(
                    frames=second["frames"],
                    slot=second["slot"],
                    token=second["id"],
                    private=second["private"],
                    start=starts[0],
                    stop=stops[0],
                    start_delay=s["START_TICK"] - s["START_EDGE"],
                    stop_delay=s["STOP_TICK"] - s["STOP_EDGE"],
                    pcm_sha256=hashlib.sha256(second["pcm"]).hexdigest(),
                )
                (out / "candidate-2.pcm").write_bytes(second["pcm"])
                dump_pages(out / "pages-2.bin", session.flex.pages)
                completed = peer.calls
                wait_for(
                    "native note after automatic USE",
                    lambda: any(x["trigger"] for x in peer.track1[completed:]),
                    80,
                )
                for receipt in bar_receipts[:2]:
                    following_step = min(
                        x["frame"]
                        for x in session.flex.sequence_trace
                        if x["frame"] > receipt["frame"]
                        and x["active"] == 1
                        and x["step"] == 2
                    )
                    require(
                        any(
                            x["trigger"]
                            for x in peer.track1[receipt["frame"] : following_step]
                        ),
                        "Native first-step note does not align with bar receipt",
                    )
                require(
                    not fw.slot(first["private"])["empty"]
                    and not fw.slot(second["private"])["empty"],
                    "Current/frozen generation released",
                )
                if not a.cpu_only:
                    require(
                        max(x["peak"] for x in peer.track1[completed:]) > 0,
                        "Silent automatic take",
                    )
                    wire = bytes(peer.tx[-0xABC:])
                    report["audio"]["current-B"] = exact_audio(
                        second, list(session.flex.pages), "current-B"
                    )
                    report["audio"]["frozen-A"] = exact_audio(
                        dict(first, slot=frozen_slot),
                        list(session.flex.pages),
                        "frozen-A",
                    )
                    report["checks"]["exact-all-32-voice-buffers"] = dict(
                        blocks=peer.calls, sha256=peer.pcm.hexdigest()
                    )
                    report["status"] = "passed-coupled-native-next-bar-auto-use"
                else:
                    report["status"] = "passed-native-next-bar-auto-use-cpu"
                report["checks"]["no-post-arm-panel-confirmation"] = True
                report["checks"]["playing-native-notes"] = True
    session.tap("STOP")
    session.tap("STOP")
    require(source_hashes() == sources, "Sources drifted")
    print("PASS", out / "report.json", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    if session:
        report["next_bar_state"] = state()
        report["next_bar_trace"] = session.flex.next_bar_trace
        report["sequence_trace"] = session.flex.sequence_trace
        report["native_freeze_requests"] = session.flex.native_freeze_requests
        report["events"] = session.flex.events
        report["automatic_submissions"] = session.flex.automatic_submissions
        report["native_trace"] = session.flex.transaction_trace
        report["state_stable"] = source_hashes() == sources
        if heap_profile is not None:
            heap_profile["final_free"] = inspect_heap(fw.read).free_bytes
            report["cpu_heap"] = heap_profile
        session.close()
    if ref_fw:
        ref_fw.close()
    if "peer" in globals():
        (out / "tx.bin").write_bytes(peer.tx)
        write_json(out / "track1.json", peer.track1)
        if not a.cpu_only:
            (out / "rx.bin").write_bytes(peer.rx)
            write_json(out / "wire-trace.json", peer.trace)
    write_json(out / "report.json", report)
