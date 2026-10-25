#!/usr/bin/env python3
# ruff: noqa: E402
"""Coupled recorder/echo test: original CPU ISR and SHARC SEC completion path.

No host pump, receipt commit or direct BUF/FREEZE command. Capture, LP0 and
event cadence are modeled. This is an opt-in experiment, never a device build.
"""

import argparse
import hashlib
import os
import shutil
import struct
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, require, source_hashes, write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--smoke", action="store_true")
a = p.parse_args()
provenance = doctor()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored runs")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k

from lab import recorder_ack as ack
from lab import recorder_ack_loop as loop
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab.flex_audio import baseline_pages
from lab.flex_freeze_probe import payload
from lab.flex_recorder import Take
from lab.flex_session import Session, stock_inputs
from lab.recorder_freeze_worker_native import QueuedFreezeUI

sources = source_hashes()
write_json(out / "sources.json", sources)
for name in sources:
    dest = out / "frozen-sources" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, dest)
report = dict(
    status="running",
    provenance=provenance,
    checks={},
    native_reuse=False,
    host_receipt_commit=False,
    host_pump=False,
    capture_producer_native=False,
    lp0_callback_entry_modeled=True,
    full_dsp_rtos_startup=False,
)
session = None


class Peer:
    def __init__(self, actual, stock):
        self.actual, self.stock = actual, stock
        self.calls = self.age = 0
        self.mode = self.next_mode = None
        self.delay = deque()
        self.last = 0
        self.stale = []
        self.inner = None
        self.pcm, self.reply = hashlib.sha256(), hashlib.sha256()
        self.trace, self.history, self.publications = [], [], []
        self.voice_at_publication = []
        self.counts = []
        self.tx, self.rx = bytearray(), bytearray()
        self.triggers = []

    def request(self):
        self.mode, self.age = self.next_mode, 0
        self.delay = deque([0] * 4)

    def publish(self, pages):
        for tag, block, header in pages:
            self.publications.append([self.calls, tag, header])
            if tag == 0xFFFFFFFF:
                self.voice_at_publication.append(
                    dict(
                        frame=self.calls,
                        voice=self.actual.voice(),
                        logical=self.actual.slot_record(300),
                    )
                )
            for engine in (self.actual, self.stock):
                engine.publish([(tag, block, header)])
            for slot in (300, 304, 305, 312):
                require(
                    self.actual.slot_record(slot) == self.stock.slot_record(slot),
                    "Slot parity",
                )

    def exchange(self, tx):
        if self.inner:
            self.inner.exchange(tx)  # existing capture only; discard its zero reply
        self.calls += 1
        self.age += 1
        mask = int.from_bytes(tx[0x22:0x24], "big")
        if mask:
            self.triggers.append(
                dict(
                    frame=self.calls,
                    mask=mask,
                    slots=[
                        int.from_bytes(tx[0xE0 + t * 0x60 : 0xE2 + t * 0x60], "big")
                        for t in (0, 4, 5)
                    ],
                )
            )
        self.tx.extend(tx)
        rx = self.actual.core.spi2_exchange(tx)
        ref = self.stock.core.spi2_exchange(tx)
        require(rx[:24] + rx[25:] == ref[:24] + ref[25:], "Wire non-carrier parity")
        wire = bytearray(rx)
        byte = rx[24]
        self.history.append(byte)
        if self.mode == "delay":
            self.delay.append(byte)
            wire[24] = self.delay.popleft()
        elif self.mode == "drop" and self.age == 17:
            wire[24] = 0
        elif self.mode == "duplicate" and self.age == 17:
            wire[24] = self.last
        elif self.mode == "stale":
            require(self.stale, "Missing native stale bytes")
            wire[24] = self.stale[(self.age - 1) % len(self.stale)]
        elif self.mode == "zero":
            wire[24] = 0
        self.last = byte
        counts = [engine.block_after_exchange() for engine in (self.actual, self.stock)]
        # Stock control decoding can queue a trigger for the following block.
        # Observe that reader there, before a short voice can naturally end.
        if self.triggers and self.triggers[-1]["frame"] == self.calls - 1:
            self.triggers[-1]["next_readers"] = [
                dict(
                    pointer=self.actual.core.peek(0x2412CC + t * 2 * 0x1D8),
                    active=self.actual.core.peek(0x2412CC + t * 2 * 0x1D8 + 0x1B8, 1),
                )
                for t in (0, 4, 5)
            ]
        voice = self.actual.voices()
        require(voice == self.stock.voices(), "Original voice PCM changed")
        self.pcm.update(voice)
        self.reply.update(rx[:24] + rx[25:])
        self.counts.append(counts)
        self.trace.append([self.calls, self.mode, byte, wire[24]])
        self.rx.extend(wire)
        return bytes(wire)


class ControlUI(QueuedFreezeUI):
    def __init__(self, *args, peer, **kwargs):
        self.peer = peer
        self.requests, self.receipts = [], []
        super().__init__(*args, **kwargs)

    def install(self, main):
        super().install(main)
        loop.install_cpu(self.fw)
        link = self.clock_state["events"]["dspi2"]
        self.peer.inner, link.peer = link.peer, self.peer
        for pc in (ack.CF_REQUEST, ack.CF_CONSUME, ack.CF_PUMP, 0x4002DD88):
            self.hooks.append(
                self.fw.uc.hook_add(UC_HOOK_CODE, self.observe_ack, begin=pc, end=pc)
            )

    def observe_ack(self, uc, pc, *_):
        fw = self.fw
        require(not fw.direct, "Host diagnostic entered running echo path")
        require(pc != ack.CF_PUMP, "Diagnostic pump was executed")
        if pc == ack.CF_CONSUME:
            ret = fw.u32(uc.reg_read(k.UC_M68K_REG_A7))
            require(loop.RECEIVE <= ret < loop.SUBMIT, "Matcher bypassed the ISR")
            return
        if pc == ack.CF_REQUEST:
            sp = uc.reg_read(k.UC_M68K_REG_A7)
            require(
                loop.SUBMIT <= fw.u32(sp) < loop.FLUSH_COPY,
                "Request bypassed completion",
            )
            args = list(struct.unpack(">5I", fw.read(sp + 4, 20)))
            self.requests.append(
                dict(frame=self.peer.calls, args=args, sr=uc.reg_read(k.UC_M68K_REG_SR))
            )
            self.peer.request()
        else:
            state = list(
                struct.unpack(">12I", fw.read(ack.constants()["CF_STATE"], 48))
            )
            key = state[1:4] + state[6:9]
            if not self.receipts or key != self.receipts[-1]["key"]:
                self.receipts.append(
                    dict(
                        frame=self.peer.calls,
                        key=key,
                        state=state,
                        sr=uc.reg_read(k.UC_M68K_REG_SR),
                    )
                )

    def published_page(self, *args):
        before = len(self.pages)
        super().published_page(*args)
        self.peer.publish(self.pages[before:])


def pcm(number, frames=12000):
    return Take(
        b"".join(
            struct.pack(
                ">hh",
                (i * (37 + number * 16)) % 20001 - 10000,
                (i * (67 + number * 22)) % 16001 - 8000,
            )
            for i in range(frames)
        ),
        True,
    )


def state():
    return list(struct.unpack(">12I", fw.read(ack.constants()["CF_STATE"], 48)))


def record(number, mode=None, long=False):
    peer.next_mode = mode
    session.flex.input.source = pcm(number, 96000 if long else 12000)
    before = len(session.flex.requests)
    session.tap("SAMPLING")
    session.tap("YES")
    require(session.flex.phase == "recording", "Recorder did not start")
    session.advance(32_000_000 if long else 8_000_000)
    session.tap("YES")
    require(session.flex.phase == "trim", "Recorder did not stop")
    session.tap("YES")
    for _ in range(20):
        if session.flex.phase == "assigned" and state()[6] in (2, 3):
            break
        session.advance()
    require(session.flex.phase == "assigned", "Native USE failed")
    require(
        len(session.flex.requests) == before + 1,
        "Native completion did not submit once",
    )
    expected = 3 if mode in ("stale", "zero") else 2
    require(state()[6] == expected, f"Receipt result {mode}: {state()}")
    require(fw.u32(loop.STATE + 8) == 0, "Native submission refused")
    require(not fw.sources and not fw.handles and not fw.direct, "Host source used")
    require(session.flex.resource_hle_calls == 0, "Resource HLE used")
    row = dict(session.flex.current)
    candidate = session.flex.input.candidate(
        fw.u32(w.STATE + 24), fw.u32(w.STATE + 24) + row["frames"]
    )
    require(
        payload(session.flex.pages, row["slot"]) == candidate.pcm,
        "Native PCM copy differs",
    )
    row.update(receipt=state(), request=session.flex.requests[-1])
    report["checks"][f"record-{number}"] = row
    print("PASS recording", number, "mode", mode, "age", state()[8], flush=True)
    return row


def select(track, target):
    session.chord("TRK", f"TRIG {track + 1}")
    live = fw.u32(0x80004704) + track * 0x450
    if fw.read(live + 0xD6, 1) != b"\0":
        session.chord("FUNC", "SRC")
        for _ in range(8):
            session.tap("UP")
        session.tap("YES")
        session.tap("YES")
    session.tap("SRC")
    session.tap("ENCODER D")
    current = int.from_bytes(fw.read(live + 0x80, 2), "big")
    for _ in range((target // 128 - current // 128) % 8):
        session.tap("RIGHT")
    for _ in range(abs(target % 128 - current % 128)):
        session.tap("DOWN" if target % 128 > current % 128 else "UP")
    session.tap("YES")
    require(int.from_bytes(fw.read(live + 0x80, 2), "big") == target, "Selector failed")


def enable_loop():
    # SRC remembers its two pages. Try their original PLAY encoder, going
    # down from stock FWD; positive rotation can be clamped at that endpoint.
    for page in range(2):
        for turn in range(24):
            session.turn("B", -5)
            session.tap("TRIG 1")
            if actual.voice()["loop"]:
                report["checks"]["stock-loop-control"] = dict(
                    page_attempt=page, turns=turn + 1, voice=actual.voice()
                )
                return
        session.tap("SRC")
    raise AssertionError("Original PLAY control did not enable a loop")


try:
    blob, meta = ack.build(out / "dsp")
    report["build"] = meta
    Engine = loop.engine_class()
    actual, stock = Engine(blob), Engine()
    for engine in (actual, stock):
        engine.publish(baseline_pages(stock_inputs()["lp0"]))
    peer = Peer(actual, stock)
    session = Session(
        pcm(1),
        out,
        adapter_factory=lambda *args, **kw: ControlUI(*args, peer=peer, **kw),
    )
    fw = session.flex.fw
    require(state()[6] == 0 and not session.flex.requests, "NORMAL invented receipt")
    report["checks"]["normal"] = dict(frames=peer.calls, no_request=True)
    session.tap("SAMPLING")
    for _ in range(14):
        if session.flex.destination == 1:
            break
        session.turn("C", 5)
    require(session.flex.destination == 1, "C destination failed")
    session.tap("SRC")
    first = record(1, long=True)
    peer.stale = list(peer.history[-48:])
    frozen = None
    if not a.smoke:
        select(4, first["slot"])
        session.chord("TRK", "TRIG 1")
        fw.write(q.STATE, struct.pack(">I", fw.u32(q.STATE) + 1))  # test command input
        session.turn("A", 0)
        for _ in range(20):
            if fw.u32(q.STATE + 32):
                break
            session.advance()
        frozen = fw.u32(q.STATE + 12)
        require(0 < frozen < 1024, "Queued native FREEZE failed")
        frozen_desc = actual.slot_record(frozen)
        frozen_allocation = first["allocation"]
        # CPU pool offsets include its 0x400 origin; DSP sample offsets omit it.
        frozen_offset = frozen_allocation["start"] - 0x400
        require(frozen_desc[0] == frozen_offset + 32, "DSP/allocator origin differs")
        frozen_pcm = hashlib.sha256(
            actual.sample_bytes(frozen_offset, frozen_allocation["size"])
        ).hexdigest()
        select(5, frozen)
        session.chord("TRK", "TRIG 1")
        enable_loop()
        session.tap("TRIG 5")
        session.tap("RECORD")
        session.chord("FUNC", "PLAY")
        session.chord("FUNC", "PAGE")
        session.tap("PAGE")
        session.tap("NO")
        for step in (1, 5, 9, 13):
            session.tap(f"TRIG {step}")
        session.tap("SRC")
        session.tap("RECORD")
        session.tap("PLAY")
        publication_start = len(peer.voice_at_publication)
        second = record(2, "delay")
        require(first["slot"] == second["slot"] == 300, "Logical buffer changed")
        require(
            actual.slot_record(frozen) == frozen_desc, "Frozen A descriptor changed"
        )
        old_pointer = 0x8422B9C8 + frozen_desc[0]
        active_old = [
            x
            for x in peer.voice_at_publication[publication_start:]
            if x["voice"]["active"] and x["voice"]["pointer"] == old_pointer
        ]
        require(active_old, "Old A active-reader replacement control was vacuous")
        report["checks"]["active-old-reader"] = active_old
        session.tap("TRIG 1")
        session.tap("TRIG 5")
        session.tap("TRIG 6")
        current_desc = actual.slot_record(300)
        readers = [actual.core.peek(0x2412CC + t * 2 * 0x1D8) for t in (0, 4, 5)]
        require(
            readers
            == [0x8422B9C8 + current_desc[0]] * 2 + [0x8422B9C8 + frozen_desc[0]],
            "Subsequent shared/frozen triggers resolved the wrong backing",
        )
        report["checks"]["shared-readers"] = readers
        for number, mode in (
            (3, "drop"),
            (4, "duplicate"),
            (5, "stale"),
            (6, "zero"),
            (7, None),
        ):
            record(number, mode)
        require(
            actual.slot_record(frozen) == frozen_desc, "Fault sequence changed frozen A"
        )
        require(
            hashlib.sha256(
                actual.sample_bytes(frozen_offset, frozen_allocation["size"])
            ).hexdigest()
            == frozen_pcm,
            "Frozen PCM allocation was overwritten",
        )
        session.tap("TRIG 6")
        report["checks"]["shared-freeze"] = dict(
            slot=frozen,
            descriptor=frozen_desc,
            generation_count=fw.u32(w.STATE + 4),
            snapshots=fw.u32(n.STATE + 4),
            pcm_allocation_sha256=frozen_pcm,
        )
        slots = [
            int.from_bytes(fw.read(fw.u32(0x80004704) + t * 0x450 + 0x80, 2), "big")
            for t in (0, 4, 5)
        ]
        require(slots == [300, 300, frozen], "Shared logical references changed")
        late_frozen = next(x for x in reversed(peer.triggers) if x["mask"] & 32)
        reader = late_frozen["next_readers"][2]
        require(
            reader["active"] and reader["pointer"] == old_pointer,
            "Late frozen A trigger was vacuous",
        )
        report["checks"]["shared-freeze"]["late_reader"] = late_frozen
        report["checks"]["shared-freeze"]["track_slots"] = slots
        # Re-enter the original NORMAL recorder and cancel its filename dialog.
        # This is not SAVE/readback of a DSP-only buffer.
        session.tap("STOP")
        session.tap("STOP")
        session.tap("SAMPLING")
        for _ in range(14):
            if session.flex.destination == 0:
                break
            session.turn("C", -5)
        require(session.flex.destination == 0, "Return to NORMAL failed")
        requests_before = len(session.flex.requests)
        session.tap("YES")
        session.advance(8_000_000)
        session.tap("YES")
        require(session.flex.phase == "trim", "NORMAL recording failed")
        require(fw.read(0x402296FB, 7) == b"Y:SAVE\0", "NORMAL lost SAVE convention")
        session.tap("YES")
        session.screenshot("normal-name-dialog")
        session.tap("NO")
        session.chord("FUNC", "NO")
        require(
            len(session.flex.requests) == requests_before,
            "NORMAL submitted buffer request",
        )
        require(fw.u32(w.STATE + 80) == 7, "NORMAL entered BUF completion")
        require(actual.slot_record(frozen) == frozen_desc, "NORMAL changed frozen A")
        report["checks"]["normal-after-buffers"] = True
    report["checks"]["native-path"] = dict(
        exchanges=peer.calls,
        dsp_completed=actual.completed,
        cpu_polls=fw.u32(loop.STATE + 12),
        submits=fw.u32(loop.STATE + 4),
        startup_sec_status=actual.startup_status,
        final_sec_status=actual.core.peek(0x31089404),
        requests=session.flex.requests,
        completions=session.flex.worker_contexts,
        freeze_contexts=session.flex.freeze_contexts,
    )
    require(all(not x["direct"] for x in session.flex.worker_contexts), "Direct worker")
    require(all(not x["direct"] for x in session.flex.freeze_contexts), "Direct FREEZE")
    nodes = []
    node = fw.u32(w.STATE)
    while node:
        nodes.append(dict(node=node, source=fw.u32(node + 20)))
        node = fw.u32(node)
    require(all(x["source"] == 0 for x in nodes), "CPU PCM retained")
    report["source_nodes"] = nodes
    report["source_retirements"] = session.flex.retirements
    report["triggers"] = peer.triggers
    report["checks"]["exact-pcm"] = dict(
        blocks=peer.calls,
        lanes=32,
        pcm_sha256=peer.pcm.hexdigest(),
        reply_sha256=peer.reply.hexdigest(),
    )
    # Independent failed-control fixture: pending DMA without SECI enable must
    # not toggle the stock command ring. Never use it as a fallback path.
    negative = Engine()
    import sharc_trace as st

    negative.core.set_reg(st.UREG_CODES["IMASK"], st.Const(0))
    shift = negative.core.peek(negative.profile.command_word_shift_src)
    negative.core.spi2_exchange(bytes(0xABC))
    negative.run_segment(loop.TASK_CALL, loop.TASK_RETURN)
    require(
        negative.core.peek(negative.profile.command_word_shift_src) == shift,
        "Disabled SEC toggled",
    )
    require(negative.core.peek(0x31089A2C) != 0, "Disabled SEC drained completion")
    report["checks"]["disabled-sec"] = True
    if not a.smoke:
        coverage = dict.fromkeys(loop.contract()["experiment"]["conditions"], True)
        require(
            fw.u32(loop.STATE + 4) == len(session.flex.requests) == 7,
            "Submission count",
        )
        require(
            fw.u32(loop.STATE + 12) == actual.completed == peer.calls,
            "Poll/block count",
        )
        require(len(session.flex.retirements) == 7, "Source-retirement count")
        report["conditions"] = coverage
    require(source_hashes() == sources, "Source drift during run")
    report["status"] = "passed"
    print("PASS", out / "report.json", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    if session:
        session.close()
        report["requests"] = session.flex.requests
        write_json(out / "receipts.json", session.flex.receipts)
        write_json(out / "publications.json", peer.publications)
        write_json(out / "publication-readers.json", peer.voice_at_publication)
        (out / "tx.bin").write_bytes(peer.tx)
        (out / "rx.bin").write_bytes(peer.rx)
        write_json(out / "wire-trace.json", peer.trace)
        write_json(out / "instruction-counts.json", peer.counts)
    write_json(out / "report.json", report)
