#!/usr/bin/env python3
# ruff: noqa: E402
"""Running native retirement: worker lease -> DSP descriptor seal -> ISR -> unload.

Capture, LP0 callback entry, CPU/DSP cadence and SEC reset contents are modeled.
No host retirement call, pause certificate, diagnostic copy or completion write.
"""

import argparse
import array
import hashlib
import os
import shutil
import struct
import sys
import wave
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, require, sha256, source_hashes, write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--cycles", type=int, default=100)
p.add_argument("--faults", action="store_true")
a = p.parse_args()
require(3 <= a.cycles <= 100, "Use 3..100 recordings")
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored runs")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance = doctor()

import plusdrive_check as check
import tools.plusdrive as pd

from lab import recorder_ack as ack
from lab import recorder_ack_loop as loop
from lab import recorder_freeze_worker_code as q
from lab import recorder_native_retirement as t
from lab import recorder_worker_code as w
from lab.flex_audio import baseline_pages
from lab.flex_dsp_probe import control
from lab.flex_freeze_probe import dump_pages, payload
from lab.flex_heap import inspect_heap
from lab.flex_lite import FlexDsp
from lab.flex_recorder import Take
from lab.flex_session import Session as OriginalSession
from lab.flex_session import stock_inputs
from lab.recorder_native_retirement_ui import NativeRetirementUI
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
session = ref_fw = None


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

    def request(self):
        self.mode, self.age = self.next_mode, 0
        self.delay = deque([0] * (4 if self.mode == "delay" else 1))
        self.reordered = None

    def publish(self, pages):
        for page in pages:
            self.actual.publish([page])
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
        self.trace.append([self.calls, self.mode, b, wire[24]])
        self.rx.extend(wire)
        base = self.dsp_state
        if self.age < 5 or self.age % 32 == 0:
            self.diagnostics.append(
                [self.calls] + [self.actual.core.peek(base + i * 4) for i in range(8)]
            )
        return bytes(wire)


def pcm(number):
    return Take(
        b"".join(
            struct.pack(
                ">hh",
                (i * (37 + number * 16)) % 20001 - 10000,
                (i * (67 + number * 22)) % 16001 - 8000,
            )
            for i in range(12000)
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
            token=row["id"],
            slot=row["slot"],
            private=row["private"],
            allocations=allocations(),
            nodes=nodes(),
            heap_free=inspect_heap(fw.read).free_bytes,
            allocation=row["allocation"],
            private_descriptors={
                str(i): peer.actual.slot_record(i) for i in range(304, 312)
            },
            frame=peer.calls,
        )
    )
    (out / f"candidate-{number}.pcm").write_bytes(row["pcm"])
    dump_pages(out / f"pages-{number}.bin", session.flex.pages)
    print("record", number, hex(row["id"]), "frame", peer.calls, flush=True)
    return row


def freeze():
    before = fw.u32(q.STATE + 32)
    fw.write(q.STATE, struct.pack(">I", fw.u32(q.STATE) + 1))
    session.turn("A", 0)
    for _ in range(20):
        if fw.u32(q.STATE + 32) > before:
            break
        session.advance()
    require(fw.u32(q.STATE + 32) == before + 1, "Queued FREEZE did not complete")
    slot = fw.u32(q.STATE + 12)
    require(0 < slot < 1024, "FREEZE refused")
    return slot


def retire(item, mode=None, *, drain=True, expected=0):
    before = allocations()
    count = fw.u32(t.STATE + t.SUCCESSES)
    peer.next_mode = mode
    fw.write(t.STATE + 16, struct.pack(">I", item["id"]))
    fw.write(t.STATE, struct.pack(">I", fw.u32(t.STATE) + 1))
    session.turn("A", 0)  # test command wake; no further host GUI polling.
    if drain and fw.u32(t.STATE + t.PHASE) == 2:
        for _ in range(3):
            session.tap("TRIG 1")
    for _ in range(30):
        if fw.u32(t.STATE + t.PHASE) in (4, 5):
            break
        session.advance()
    phase, result = fw.u32(t.STATE + t.PHASE), fw.u32(t.STATE + 12)
    require(
        phase in (4, 5),
        f"Transaction stuck {phase}, reply {fw.u32(ack.constants()['CF_STATE'] + ack.PHASE)}",
    )
    require(
        result == (expected & 0xFFFFFFFF),
        f"Retirement {mode} returned {result:#x}, expected {expected}; diagnostics {peer.diagnostics[-4:]}",
    )
    if expected == 0:
        require(
            phase == 4 and fw.u32(t.STATE + t.SUCCESSES) == count + 1,
            "No native release",
        )
        require(fw.slot(item["private"])["empty"], "Private stock owner retained")
        require(
            sum(x["size"] for x in before) - sum(x["size"] for x in allocations())
            == item["allocation"]["size"],
            "Wrong allocation released",
        )
    else:
        require(
            phase == 5
            and allocations() == before
            and fw.u32(t.STATE + t.SUCCESSES) == count,
            "Refusal mutated allocator",
        )
    require(fw.u32(w.STATE + 12) == 0, "Native lease not released")
    report["retirements"].append(
        dict(
            token=item["id"],
            mode=mode,
            result=result,
            phase=phase,
            sequence=fw.u32(t.STATE + t.SEQ),
            before=before,
            after=allocations(),
            frame=peer.calls,
        )
    )
    print("retire", hex(item["id"]), mode, hex(result), "frame", peer.calls, flush=True)
    if not peer.stale and expected == 0:
        peer.stale = list(peer.history[-64:])


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


try:
    t.contract()
    blob, metadata = t.build(out / "dsp")
    report["build"] = metadata
    voice_reader = VoiceReader(out / "voice-reader")
    Engine = loop.engine_class()
    actual, stock = Engine(blob), Engine()
    baseline = baseline_pages(stock_inputs()["lp0"])
    for engine in (actual, stock):
        engine.publish(baseline)
    peer = Peer(actual, stock)
    session = Session(
        pcm(1),
        out,
        adapter_factory=lambda *args, **kw: NativeRetirementUI(*args, peer=peer, **kw),
    )
    fw = session.flex.fw
    # The authenticated stock fixture starts T3 on STRETCH. Establish the
    # declared all-ONESHOT context through original panel events before BUF IDs exist.
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
    session.chord("TRK", "TRIG 1")
    report["checks"]["native-oneshot-context"] = machine_changes
    session.tap("STOP")
    session.tap("STOP")
    session.tap("SAMPLING")
    for _ in range(14):
        if session.flex.destination == 1:
            break
        session.turn("C", 5)
    session.tap("SRC")
    first = record(1)
    stable = first["slot"]
    retire(first, drain=False, expected=-5)
    report["checks"]["current-root"] = True
    session.tap("TRIG 1")
    # The peer records the actual original control frames; use its last public T1 frame.
    wire = bytes(peer.tx[-0xABC:])
    second = record(2)
    retire(first)
    third = record(3)
    frozen_slot = freeze()
    retire(second)
    previous = third
    for number in range(4, a.cycles + 1):
        current = record(number)
        if previous["id"] == third["id"]:
            retire(previous, drain=False, expected=-3)
            report["checks"]["frozen-root"] = True
            retire(first, drain=False, expected=-2)
            report["checks"]["stale-token-after-reuse"] = True
        else:
            mode = (
                {
                    5: "delay",
                    6: "drop",
                    7: "duplicate",
                    8: "reorder",
                    9: "corrupt",
                    10: "stale",
                    11: "zero",
                }.get(number)
                if a.faults
                else None
            )
            if mode in ("corrupt", "stale", "zero"):
                retire(previous, mode, expected=-6)
                report["checks"][mode + "-retains"] = True
                retire(previous)
            else:
                retire(previous, mode)
        if number in (5, 8, 9, 16, 32, 64, 100):
            report["audio"][str(number)] = exact_audio(
                current, list(session.flex.pages)
            )
        previous = current
        require(len(nodes()) == 2, "Dead source metadata grew")
    report["audio"]["late-frozen"] = exact_audio(
        dict(third, slot=frozen_slot), list(session.flex.pages), "late-frozen"
    )
    require(len({x["token"] for x in report["cycles"]}) == a.cycles, "Token repeated")
    require(
        len({sha256(out / f"candidate-{i}.pcm") for i in range(1, a.cycles + 1)})
        == a.cycles,
        "Captured PCM repeated",
    )
    require(
        {x["slot"] for x in report["cycles"]} == {stable}, "Public slot changed"
    )
    require(
        max(len(x["nodes"]) for x in report["cycles"]) <= 3,
        "Source metadata grew",
    )
    require(source_hashes() == sources, "Sources drifted")
    report["checks"]["native-isr-to-worker"] = True
    report["checks"]["exact-all-32-voice-buffers"] = dict(
        blocks=peer.calls, sha256=peer.pcm.hexdigest()
    )
    report["final_allocations"] = allocations()
    report["final_nodes"] = nodes()
    report["final_heap_free"] = inspect_heap(fw.read).free_bytes
    report["native_source_frees"] = session.flex.retirements
    report["status"] = "passed-restricted-native-transaction"
    print("PASS", out / "report.json", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    if session:
        report["native_trace"] = session.flex.transaction_trace
        report["phase"] = fw.u32(t.STATE + t.PHASE)
        report["tx_state"] = [fw.u32(t.STATE + i * 4) for i in range(29)]
        report["ack_state"] = [
            fw.u32(ack.constants()["CF_STATE"] + i * 4) for i in range(15)
        ]
        report["events"] = events
        session.close()
    if ref_fw:
        ref_fw.close()
    if "peer" in globals():
        (out / "tx.bin").write_bytes(peer.tx)
        (out / "rx.bin").write_bytes(peer.rx)
        write_json(out / "wire-trace.json", peer.trace)
        write_json(out / "diagnostics.json", peer.diagnostics)
        write_json(out / "instructions.json", peer.counts)
    write_json(out / "report.json", report)
