#!/usr/bin/env python3
# ruff: noqa: E402
"""Native request echo through original SPI2 descriptors and CF receive driver.

LP0 publisher capture, DMA events, completion callback entry and block cadence
are modeled. No host receipt commit, allocator permission or memory reuse.
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
from lab.project import (
    ROOT,
    doctor,
    read_json,
    require,
    sha256,
    source_hashes,
    write_json,
)

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
a = p.parse_args()
provenance = doctor()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored runs")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

# lab.dsp installs the pinned dependency import paths before external imports.
# isort: off
from lab import recorder_ack as ack
from lab import recorder_retirement as obs
from lab.dsp import Dsp
from lab.flex_audio import baseline_pages
from lab.flex_lite import FlexDsp, RamFirmware
from lab.flex_session import stock_inputs

import sharc_trace as st
from emu.dspi2 import Dspi2Link
from unicorn import UC_HOOK_CODE
# isort: on

sources = source_hashes()
write_json(out / "sources.json", sources)
for name in sources:
    dest = out / "frozen-sources" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, dest)

k = ack.constants()
ok = obs.constants()
fixture = ROOT / "out/runs/recorder-freeze-queue-native-20261021-02"
expected = {
    "report.json": "5053a977dd664b473692ce3b9e9769b847d403c2440062b8af84bcdfc8a2f579",
    "pages-af.bin": "ef0b4314174803a6535feb326c3f29951c4b211d0f0ab6cbbe4615cac99eee29",
    "pages-b.bin": "e596b46a882600036d0c258eb2b66e06ccdd7e4ff52e2c85f82ac79d9218159e",
}
report = dict(
    status="running",
    provenance=provenance,
    checks={},
    native_reclamation=False,
    native_sec_dispatch=False,
    lp0_publisher_body_executed=False,
    cpu_driver_hle=False,
    host_receipt_commit=False,
)
fw = None


def read(core, address, size):
    return bytes(core.peek(address + i, 1) for i in range(size))


def put(core, address, value, width=4):
    require(
        core.poke(address, value.to_bytes(width, "little"), width) == 1,
        "Fixture write failed",
    )


def cpu_state():
    return list(struct.unpack(">12I", fw.read(k["CF_STATE"], 48)))


def pages(name):
    raw = (fixture / name).read_bytes()
    require(len(raw) % 4104 == 0, "Partial page capture")
    return [
        (
            struct.unpack_from(">I", raw, i)[0],
            raw[i + 8 : i + 4104],
            struct.unpack_from(">I", raw, i + 4)[0],
        )
        for i in range(0, len(raw), 4104)
    ]


class Engine(FlexDsp):
    def __init__(self, blob=None):
        Dsp.__init__(self, blob)
        self.core.set_option(self.native.OPT_PERIPHERAL_MODEL, 1)
        # Explicit reset fixture for the missing SEC bank in this prepared pack.
        # This is the model's absent-register zero default, not device evidence.
        for address in range(0x31089800, 0x3108A000, 4):
            put(self.core, address, 0)
        self.core.set_reg(st.UREG_CODES["R4"], st.Const(0xABC))
        self.call(0x1C7BD4, 1_000_000)
        self.spi_init_instructions = self.core.stats()["instructions"]

    def block_after_exchange(self):
        self.core.set_reg(
            st.UREG_CODES["R8"], st.Const(self.h.DMA_SHIFT_CALLBACK_COMPLETE_EVENT)
        )
        self.call(self.h.DMA_SHIFT_CALLBACK, 64)
        before = self.core.stats()["instructions"]
        self.call(self.profile.block_handler, 4_000_000)
        return self.core.stats()["instructions"] - before

    def voices(self):
        raw = []
        for lane in range(32):
            base = (
                ok["VOICE_BASE"] + lane * ok["VOICE_STRIDE"] + self.h.FIELD_WORK_BUFFER
            )
            raw.extend(self.core.peek(base + i * 4) for i in range(64))
        return struct.pack("<2048I", *raw)


class Peer:
    def __init__(self, actual, stock):
        self.actual, self.stock = actual, stock
        self.calls = 0
        self.mode = None
        self.age = 0
        self.history = []
        self.old = []
        self.delay = deque()
        self.held = None
        self.last = 0
        self.pcm = hashlib.sha256()
        self.reply = hashlib.sha256()
        self.trace = []
        self.counts = []
        self.tx = bytearray()
        self.native_replies = bytearray()
        self.delivered_replies = bytearray()

    def fault(self, mode=None, stale=None):
        self.mode = mode
        self.age = 0
        self.delay = deque([0] * 4)
        self.held = None
        self.last = 0
        self.old = list(stale or [])

    def exchange(self, tx):
        self.calls += 1
        self.age += 1
        self.tx.extend(tx)
        incoming = self.actual.core.spi2_exchange(tx)
        self.native_replies.extend(incoming)
        stock = self.stock.core.spi2_exchange(tx)
        require(len(incoming) == len(stock) == 0xABC, "SPI2 frame width changed")
        c = k["CF_REPLY_BYTE"]
        require(
            incoming[:c] + incoming[c + 1 :] == stock[:c] + stock[c + 1 :],
            "Native transmitter changed non-carrier reply bytes",
        )
        byte = incoming[c]
        self.history.append(byte)
        wire = bytearray(incoming)
        if self.mode == "delay":
            self.delay.append(byte)
            wire[c] = self.delay.popleft()
        elif self.mode == "drop" and self.age == 17:
            wire[c] = 0
        elif self.mode == "duplicate" and self.age == 17:
            wire[c] = self.last
        elif self.mode == "reorder":
            if self.age == 17:
                self.held = byte
                wire[c] = 0
            elif self.age == 19:
                wire[c] = self.held
        elif self.mode == "corrupt" and self.age == 17:
            wire[c] ^= 1
        elif self.mode == "stale":
            require(self.old, "Missing native stale capture")
            wire[c] = self.old[(self.age - 1) % len(self.old)]
        elif self.mode == "zero":
            wire[c] = 0
        self.last = byte
        # Actual native DMA selection/movement happens above. Interrupt callback
        # entry and audio scheduling remain explicit host peripheral fixtures.
        counts = [e.block_after_exchange() for e in (self.actual, self.stock)]
        pcm = self.actual.voices()
        require(pcm == self.stock.voices(), "Echo changed original voice PCM")
        self.pcm.update(pcm)
        for bank in (0x266220, 0x267220):
            x, y = (read(e.core, bank, 0xABC) for e in (self.actual, self.stock))
            j = k["DSP_REPLY_BYTE"]
            require(
                x[:j] + x[j + 1 :] == y[:j] + y[j + 1 :], "Echo changed reply payload"
            )
            self.reply.update(x[:j] + x[j + 1 :])
        for slot in (300, 304, 305, 312):
            require(
                self.actual.slot_record(slot) == self.stock.slot_record(slot),
                "Echo changed sample descriptors",
            )
        q = [self.actual.core.peek(ok["STATE"] + i * 4) for i in range(6)]
        e = [self.actual.core.peek(k["DSP_STATE"] + i * 4) for i in range(6)]
        if q[0]:
            i = (e[1] - 1) % k["FRAGMENTS"]
            require(
                e[3] in (0x266220, 0x267220, 0x28266220, 0x28267220), "Bad echo bank"
            )
            require(
                self.actual.core.peek(e[3] + k["DSP_REPLY_BYTE"], 1)
                == ack.fragments(*q[1:4])[i],
                "Native fragment differs from independent oracle",
            )
        self.trace.append(
            dict(frame=self.calls, raw=byte, delivered=wire[c], mode=self.mode)
        )
        self.counts.append(dict(patched=counts[0], stock=counts[1]))
        self.delivered_replies.extend(wire)
        return bytes(wire)


try:
    for name, digest in expected.items():
        require(
            sha256(fixture / name) == digest, "Unknown native worker fixture: " + name
        )
    proof = read_json(fixture / "report.json")
    require(proof["status"] == "passed", "Unproven native fixture")
    blob, meta = ack.build(out / "dsp")
    report["build"] = meta
    actual, stock = Engine(blob), Engine()
    report["checks"]["native-spi-init"] = {
        hex(base): [actual.core.peek(base + i * 4) for i in range(7)]
        for base in (0x2641B0, 0x2641CC, 0x2641E8, 0x264204)
    }
    pa, pb = pages("pages-af.bin"), pages("pages-b.bin")
    require(pb[: len(pa)] == pa, "Page history changed")
    for engine in (actual, stock):
        engine.publish(baseline_pages(stock_inputs()["lp0"]))
        engine.publish(pa)
        # Nonzero stock flag adjacent to the selected padding byte.
        put(engine.core, 0x2528E8, 0x7B, 1)
        for bank in (0x266220, 0x267220):
            put(engine.core, bank + 26, 0x8ABC, 2)  # independent CAPI-field sentinel
    frozen = actual.slot_record(312)
    inputs = stock_inputs()
    fw = RamFirmware(inputs["card"], inputs["snapshot"])
    for base, size in ((obs.CF_BASE, 8192), (k["CF_BASE"], 16384)):
        for offset in range(0, size, 4096):
            fw.m.ensure(base + offset)
        fw.write(base, bytes(size))
    fw.write(obs.CF_ENTRY, obs.sender())
    for address, code in ack.cpu().items():
        fw.write(address, code)
        (out / f"cf-{address:x}.bin").write_bytes(code)
    peer = Peer(actual, stock)
    link = Dspi2Link(fw.m, peer)
    fw.m.mmio[0xEC03802C] = fw.m.mmio.get(0xEC03802C, 0) | (1 << 28)
    fw.m.install_mmio()
    fw.call(0x400CD2B0, [0xABC])
    counters = {"driver": 0, "new_code": 0}

    def count_driver(*_):
        counters["driver"] += 1

    def count_code(*_):
        counters["new_code"] += 1

    fw.uc.hook_add(UC_HOOK_CODE, count_driver, begin=0x400CD2BC, end=0x400CD47E)
    fw.uc.hook_add(
        UC_HOOK_CODE, count_code, begin=k["CF_BASE"], end=k["CF_BASE"] + 0x1FFF
    )
    wire = bytearray.fromhex(proof["audio_inputs"]["wire"])
    for track, slot in ((0, 300), (4, 300), (5, 312)):
        struct.pack_into(">H", wire, 0xE0 + track * 0x60, slot)
    cpu_trace = []

    def pump(trigger=0):
        frame = bytearray(wire)
        for offset in (0x22, 0x24, 0x26, 0x28, 0x2A):
            struct.pack_into(
                ">H", frame, offset, trigger if offset in (0x22, 0x26) else 0
            )
        fw.write(0x80005348, frame[:0x802])
        value = fw.call(ack.CF_PUMP, [])
        cpu_trace.append(
            dict(
                frame=peer.calls,
                value=value,
                state=cpu_state(),
                received=fw.read(0x8000488C + 24, 1).hex(),
            )
        )
        return value

    pump(49)
    for _ in range(5):
        pump()
    require(cpu_state()[ack.PHASE // 4] == 0, "No request invented a receipt")
    require(not any(peer.history), "Stock-zero padding was not zero")
    report["checks"]["no-request"] = True
    report["checks"]["native-cf-driver"] = dict(
        exchanges=link.frames, previous_receive_copy=True
    )
    seq = 0
    requests = bytearray()

    def request(generation=1):
        global seq
        seq += 1
        entry = proof["checks"]["first" if generation == 1 else "second"]["allocation"]
        args = (1, ok["FIRST_ID"] + generation - 1, seq, entry["start"], entry["size"])
        fw.pages.clear()
        require(
            fw.call(ack.CF_REQUEST, list(args)) == 0 and len(fw.pages) == 1,
            "Native request failed",
        )
        require(
            fw.pages[0] == (ok["TAG"], obs.packet(*args), 1), "Native request encoding"
        )
        require(
            fw.read(ack.CF_EXPECTED, 48) == ack.fragments(*args[:3]),
            "Native expected fragment table differs",
        )
        tag, packet, order = fw.pages[0]
        requests.extend(struct.pack(">II", tag, order) + packet)
        for engine in (actual, stock):
            engine.publish(fw.pages)
        return args

    def confirm(name, mode=None, generation=1):
        peer.fault(mode)
        args = request(generation)
        start = peer.calls
        before = cpu_state()[ack.MATCHES // 4]
        for _ in range(k["TIMEOUT"]):
            result = pump()
            if result:
                break
        require(
            result == 1 and cpu_state()[ack.MATCHES // 4] == before + 1,
            "Missing native echo: " + name,
        )
        report["checks"][name] = dict(
            args=list(args), polls=peer.calls - start, state=cpu_state()
        )
        print("PASS", name, "polls", peer.calls - start, flush=True)

    confirm("echo-a")
    stale = list(peer.history[-48:])
    for page in pb[len(pa) :]:
        for engine in (actual, stock):
            engine.publish([page])
        pump()
    # New track triggers pick B while the immutable A snapshot remains valid.
    confirm("echo-b", generation=2)
    pump(49)
    pump()
    require(actual.slot_record(312) == frozen, "FREEZE alias changed")
    require(actual.reading(312), "Frozen A reader disappeared")
    report["checks"]["frozen-root"] = dict(slot=312, descriptor=frozen)
    for name, mode in (
        ("delayed", "delay"),
        ("dropped", "drop"),
        ("duplicate", "duplicate"),
        ("reordered", "reorder"),
        ("corrupt", "corrupt"),
    ):
        confirm(name, mode)
    peer.fault("stale", stale)
    request()
    before = cpu_state()[ack.MATCHES // 4]
    for _ in range(k["TIMEOUT"]):
        last = pump()
    require(
        last == 0xFFFFFFFF and cpu_state()[ack.MATCHES // 4] == before,
        "Stale native replies confirmed a newer request",
    )
    report["checks"]["stale"] = dict(state=cpu_state(), native_capture=stale)
    peer.fault()
    request()
    for _ in range(20):
        require(pump() == 0, "Partial echo confirmed")
    confirm("supersede")
    peer.fault("zero")
    request()
    before = cpu_state()[ack.MATCHES // 4]
    for _ in range(k["TIMEOUT"]):
        last = pump()
    require(
        last == 0xFFFFFFFF and cpu_state()[ack.MATCHES // 4] == before,
        "Zero replies did not time out",
    )
    report["checks"]["timeout"] = cpu_state()
    peer.fault()
    request()
    fw.m.mmio[0xEC03802C] &= ~(1 << 28)
    before = peer.calls
    for _ in range(k["TIMEOUT"]):
        last = pump()
    require(
        peer.calls == before and last == 0xFFFFFFFF,
        "Busy transport fabricated exchange",
    )
    report["checks"]["transport-busy"] = dict(exchanges=0, state=cpu_state())
    fw.m.mmio[0xEC03802C] |= 1 << 28
    # In-band field compatibility: stock flag and Capicola word stay untouched.
    flags = []
    for bank in (0x266220, 0x267220):
        require(actual.core.peek(bank + 26, 2) == 0x8ABC, "CAPI sentinel overwritten")
        flags.append(actual.core.peek(bank + 24, 1))
    require(any(flags), "Stock flag preservation control was vacuous")
    report["checks"]["byte-preservation"] = dict(
        stock_flags=flags, capicola_word=0x8ABC
    )
    report["checks"]["exact-pcm"] = dict(
        blocks=peer.calls,
        lanes=32,
        pcm_sha256=peer.pcm.hexdigest(),
        reply_sha256=peer.reply.hexdigest(),
    )
    require(actual.slot_record(312) == frozen, "Frozen root lost after fault tests")
    require(not fw.card.writes, "Echo wrote storage")
    report.update(
        cpu_instruction_observations=counters,
        counts=peer.counts,
        link_frames=link.frames,
        request_sequence=seq,
        final_cpu_state=cpu_state(),
        native_return_transport="descriptor DMA with modeled callback entry",
        captures_sha256={
            name: hashlib.sha256(data).hexdigest()
            for name, data in (
                ("tx.bin", peer.tx),
                ("native-replies.bin", peer.native_replies),
                ("delivered-replies.bin", peer.delivered_replies),
                ("native-requests.bin", requests),
            )
        },
    )
    write_json(out / "wire-trace.json", peer.trace)
    write_json(out / "cpu-trace.json", cpu_trace)
    require(
        set(report["checks"]) == set(ack.contract()["experiment"]["conditions"]),
        "Unexecuted echo contract condition",
    )
    require(source_hashes() == sources, "Source drift during echo probe")
    report["status"] = "passed"
    print("PASS", out / "report.json", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if fw:
        report["failure_cpu_state"] = cpu_state()
    if "actual" in globals():
        report["failure_echo_state"] = [
            actual.core.peek(k["DSP_STATE"] + i * 4) for i in range(6)
        ]
        report["failure_request_state"] = [
            actual.core.peek(ok["STATE"] + i * 4) for i in range(6)
        ]
    raise
finally:
    if fw:
        fw.close()
    if "peer" in globals():
        for name, data in (
            ("tx.bin", peer.tx),
            ("native-replies.bin", peer.native_replies),
            ("delivered-replies.bin", peer.delivered_replies),
        ):
            (out / name).write_bytes(data)
    if "requests" in globals():
        (out / "native-requests.bin").write_bytes(requests)
    write_json(out / "report.json", report)
