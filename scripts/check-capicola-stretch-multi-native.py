#!/usr/bin/env python3
"""Execute bounded multi-source Capicola playback through native STRETCH.

Uses captured LP0 PCM and explicitly adapted control wire. Output is the actual
STRETCH destination before the final mix, never the generic voice-buffer tap.
"""

# ruff: noqa: E402, I001
import argparse
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
args = parser.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
doctor()
from lab.capicola_layout import STATE_BASE, address
from lab.capicola_memory import RESERVED_BASE
from lab.capicola_memory import patch_cpu as reserve
from lab.dsp import Dsp, header
from lab.flex_native_build import patch_cpu as flex
from lab.formats import read_frames
from lab.plaits import build_blob, build_cpu
from lab.plaits_menu import patch_cpu as menu

import sharc_trace as st
import sharcldr
from capicola_stretch_reference import Reader
from sharc_transpile_run import OPT_STOP_PC

POOL = 0x8422B9C8
AUTO, HANDOFF, CACHE, LANES = [
    address(a) for a in (0x200E4500, 0x200E4000, 0x200E7000, 0x200E4800)
]
CAPTURE = ROOT / "out/runs/capicola-panel-08/capicola.dtfr"
LOAD = ROOT / "out/runs/capicola-panel-05/flexbus.raw"
EXPECTED_INPUTS = {
    CAPTURE: "3e6a3f0f319ca2c27087a77fb09d73f0b88922c2eabec0bb42651de8a1596290",
    LOAD: "85f122f352abf80e5ae7fd11e9d5f05e5cc8b3e0526cd694d4fe420b6707e844",
}
report = dict(status="running", firmware="Digitakt II OS1.16", hardware_verified=False)
wire_log = []


def read(engine, address, count):
    return bytes(engine.core.peek(address + i, 1) for i in range(count))


def floats(engine, address, count):
    return struct.unpack("<" + str(count) + "f", read(engine, address, count * 4))


def put(wire, offset, value):
    wire[offset : offset + 2] = value.to_bytes(2, "big")


from lab.replay_io import load_pcm


def arena(blob, extent, *, bank):
    split = sharcldr.parse_blocks(blob)[-1]["offset"]
    extra = header(POOL - 1024, extent) + bytes(extent)
    if bank:
        # Stop before constants/state: do not zero the linked working arena.
        extra += header(RESERVED_BASE, STATE_BASE - RESERVED_BASE) + bytes(
            STATE_BASE - RESERVED_BASE
        )
    return blob[:split] + extra + blob[split:]


def destination(engine, lane=0):
    pointer = engine.core.peek(0x24EF2C + lane * 4)
    require(
        0x80000000 <= pointer < 0xA0000000 and pointer % 4 == 0,
        "Native destination bounds",
    )
    if engine.core.peek(LANES + lane * 132 + 120) == 1:
        require(
            engine.core.peek(LANES + lane * 132 + 128) == pointer,
            "Renderer destination differs from native pointer table",
        )
        return floats(engine, address(0x200E6000) + lane * 128, 32)
    return floats(engine, pointer, 32)


def reference(engine, lane=0):
    core = engine.core
    bank = core.peek(LANES + lane * 132)
    count, frames = core.peek(bank + 16), core.peek(bank + 20)
    values = floats(engine, core.peek(bank), count)
    wholes = [core.peek(core.peek(bank + 4) + 4 * i) for i in range(count)]
    fractions = [core.peek(core.peek(bank + 8) + 4 * i) for i in range(count)]
    times = [w + f / 2**24 for w, f in zip(wholes, fractions, strict=True)]
    voice = 0x2412CC + lane * 0x1D8
    positions = [
        (core.peek(voice + offset + 4) << 1) | (core.peek(voice + offset) >> 31)
        for offset in (0x198, 0x1A0)
    ]
    return Reader(
        values,
        times,
        frames,
        *positions,
        core.peek(voice + 0x1BB, 1),
        core.peek(voice + 0x1BC, 1),
        floats(engine, voice + 0x1CC, 1)[0],
        floats(engine, voice + 0x1C8, 1)[0],
    )


def compare(actual, expected, label):
    import math

    errors = [abs(a - b) for a, b in zip(actual, expected, strict=True)]
    maximum, rms = max(errors), math.sqrt(sum(e * e for e in errors) / len(errors))
    if not (maximum <= 1e-4 and rms <= 1e-5):
        write_json(
            out / "failed-destination.json",
            dict(
                label=label,
                actual=actual,
                expected=expected,
                maximum_error=maximum,
                rms_error=rms,
            ),
        )
    require(all(math.isfinite(v) for v in actual), "Nonfinite destination: " + label)
    require(maximum <= 1e-4 and rms <= 1e-5, f"{label}: max={maximum}, rms={rms}")
    return maximum, rms


# Synthetic samples are explicit fixture inputs, not a new panel/sample capture.
ENTRY_BASE, ENTRY_STRIDE = CACHE + 28, 88


def entries(engine):
    return [
        dict(
            index=i,
            bank=ENTRY_BASE + i * ENTRY_STRIDE,
            source=engine.core.peek(ENTRY_BASE + i * ENTRY_STRIDE + 36),
            epoch=engine.core.peek(ENTRY_BASE + i * ENTRY_STRIDE + 40),
            ready=engine.core.peek(ENTRY_BASE + i * ENTRY_STRIDE + 48),
            bytes=engine.core.peek(ENTRY_BASE + i * ENTRY_STRIDE + 68),
            state=engine.core.peek(ENTRY_BASE + i * ENTRY_STRIDE + 80),
        )
        for i in range(16)
    ]


def sample_slot(engine, slot, offset, data):
    engine.core.poke(POOL + offset, struct.pack("<" + str(len(data)) + "h", *data), 1)
    engine.core.poke(
        0x257810 + slot * 20,
        struct.pack("<5I", offset, offset, len(data) * 2, 48000, 0),
        1,
    )


def frame(engine, wire, trig=0):
    put(wire, 0x22, trig)
    engine.frame(bytes(wire))


try:
    import math
    import hashlib

    sources = source_hashes()
    for path, expected in EXPECTED_INPUTS.items():
        require(sha256(path) == expected, "Fixture drift")
    raw = LOAD.read_bytes()
    candidate = build_blob(
        True,
        family="capicola-stretch-multi",
        layout="reserved-state",
        output=out / "candidate",
    )
    repeat = build_blob(
        True,
        family="capicola-stretch-multi",
        layout="reserved-state",
        output=out / "repeat",
    )
    require(candidate == repeat, "Nondeterministic multi-source build")
    r1 = build_blob(
        True, family="capicola-stretch", layout="reserved-state", output=out / "r1"
    )
    require(
        hashlib.sha256(r1).hexdigest()
        == "2e40f16aca0243cf44732703be0e18817669ddb2ae5653c945de352ca4b3334a",
        "Preserved R1 drift",
    )
    build_cpu(family="integration")
    image = reserve(menu(flex((out / "PLAITS_MAIN_OS.bin").read_bytes())[0])[0])[0]
    (out / "STRETCH_MAIN_OS.bin").write_bytes(image)
    require(
        sha256(out / "STRETCH_MAIN_OS.bin")
        == "7f19553cc4bbdf170378ba67c85bedcf4a57a1d10a4a9751080e249547bd8ff3",
        "Native CPU interface drift",
    )
    engine = Dsp(arena(candidate, 4 * 1024 * 1024, bank=True))
    load_pcm(engine, raw)
    template = next(
        w
        for w in read_frames(CAPTURE)
        if int.from_bytes(w[0x94:0x96], "big") == 8
        and int.from_bytes(w[0x22:0x24], "big") & 1
    )
    wire = bytearray(template)
    pcm = []
    for track in range(16):
        data = [int(12000 * math.sin(i * (track + 1) * 0.08)) for i in range(512)]
        pcm.append(data)
        sample_slot(engine, 1000 + track, 0x20000 + track * 2048, data)
        put(wire, 0x94 + track * 2, 2)
        put(wire, 2 + track * 2, 60 * 256)
        put(wire, 0x34 + track * 2, 100 * 256)
        block = 0xDA + track * 0x60
        wire[block : block + 0x60] = template[0xDA:0x13A]
        for offset, value in (
            (0, 16384 + ((track % 3) - 1) * 3072),
            (2, (0, 256, 512, 768)[track % 4]),
            (4, 0),
            (6, 1000 + track),
            (12, 0),
            (14, 30720),
            (16, (track % 4) * 256),
            (18, 25600),
        ):
            put(wire, block + offset, value)
    frame(engine, wire)
    # Startup can overwrite slot metadata; reapply synthetic slots after block.
    for track, data in enumerate(pcm):
        sample_slot(engine, 1000 + track, 0x20000 + track * 2048, data)
    frame(engine, wire, 65535)
    frame(engine, wire)
    require(
        all(engine.core.peek(LANES + i * 132 + 120) == 0 for i in range(32)),
        "Unready source selected custom",
    )
    prepared = 0
    while engine.core.peek(HANDOFF + 8) != 16 and prepared < 1500:
        frame(engine, wire)
        prepared += 1
    require(
        engine.core.peek(HANDOFF + 8) == 16, "Sixteen distinct banks did not prepare"
    )
    require(
        all(engine.core.peek(LANES + i * 132 + 120) == 0 for i in range(32)),
        "Preparation took over stock note",
    )
    bank_entries = entries(engine)
    require(len({e["source"] for e in bank_entries}) == 16, "Sources not distinct")
    used = engine.core.peek(HANDOFF + 12)
    require(0 < used <= 0x6FFF00, "Arena overflow")
    import ctypes as ct
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "host_prep", ROOT / "scripts/check-capicola-prep.py"
    )
    host_prep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host_prep)
    host_dir = out / "host-keys"
    host_dir.mkdir()
    lib, capacity = host_prep.build(host_dir)
    key_max = 0.0
    key_time_max = 0.0
    for track, data in enumerate(pcm):
        bank = capacity.Bank()
        worker = host_prep.Prep()
        input_data = (ct.c_short * len(data))(*data)
        lib.cap_bank_init(ct.byref(bank))
        lib.cap_prepare_init(ct.byref(worker), ct.byref(bank))
        lib.cap_prepare_begin(ct.byref(worker), input_data, len(data), 1, track + 1)
        while worker.phase == 1:
            lib.cap_prepare_step(ct.byref(worker), track + 1, 256)
        n = worker.needed
        values = (ct.c_float * n)()
        wholes = (ct.c_int * n)()
        fractions = (ct.c_uint * n)()
        lib.cap_prepare_storage(ct.byref(worker), values, wholes, fractions, n)
        while worker.phase == 3:
            lib.cap_prepare_step(ct.byref(worker), track + 1, 256)
        target = next(
            e["bank"]
            for e in bank_entries
            if e["source"] == POOL + 0x20000 + track * 2048
        )
        require(
            engine.core.peek(target + 16) == n,
            "Native key count differs from independent preparation",
        )
        for i, value in enumerate(floats(engine, engine.core.peek(target), n)):
            key_max = max(key_max, abs(value - values[i]))
            whole = engine.core.peek(engine.core.peek(target + 4) + i * 4)
            fraction = engine.core.peek(engine.core.peek(target + 8) + i * 4)
            key_time_max = max(
                key_time_max,
                abs((whole - wholes[i]) + (fraction - fractions[i]) / 2**24),
            )
    require(
        key_max <= 1e-6 and key_time_max <= 2**-24,
        "Native bank differs from independent preparation",
    )
    print(
        f"Sixteen distinct banks ready: {used} bytes after {prepared} blocks",
        flush=True,
    )
    frame(engine, wire, 65535)
    frame(engine, wire)
    require(
        all(engine.core.peek(LANES + i * 132 + 120) == 1 for i in range(32)),
        "Sixteen-source custom playback failed",
    )
    require(
        len({engine.core.peek(LANES + i * 264) for i in range(16)}) == 16,
        "Tracks share a descriptor despite different source",
    )
    refs = [reference(engine, i) for i in range(32)]
    maximum = rms = 0.0
    counts = []
    audio = [[] for _ in range(32)]
    for block in range(16):
        if block:
            frame(engine, wire)
        counts.append(engine.block_instructions[-1])
        for lane in range(32):
            actual = destination(engine, lane)
            m, r = compare(
                actual, refs[lane].process(32), f"distinct lane {lane} block {block}"
            )
            maximum = max(maximum, m)
            rms = max(rms, r)
            audio[lane].extend(actual)
    require(
        len({tuple(audio[i]) for i in range(0, 32, 2)}) == 16,
        "Distinct samples yielded identical PCM",
    )
    # Same controls, length and readers: compare shared versus distinct-source
    # work in this candidate. This is an emulator instruction comparison only.
    for track in range(16):
        put(wire, 0xE0 + track * 0x60, 1000)
    frame(engine, wire, 65535)
    frame(engine, wire)
    shared_refs = [reference(engine, i) for i in range(32)]
    shared_counts = []
    for block in range(8):
        if block:
            frame(engine, wire)
        shared_counts.append(engine.block_instructions[-1])
        for lane in range(32):
            compare(
                destination(engine, lane),
                shared_refs[lane].process(32),
                f"all shared {lane}/{block}",
            )
    require(
        len({engine.core.peek(LANES + i * 264) for i in range(16)}) == 1,
        "All shared fixture created duplicate banks",
    )
    for track in range(16):
        put(wire, 0xE0 + track * 0x60, 1000 + track)
    frame(engine, wire, 65535)
    frame(engine, wire)
    refs = [reference(engine, i) for i in range(32)]
    for lane in range(32):
        compare(
            destination(engine, lane),
            refs[lane].process(32),
            f"restored distinct {lane}",
        )
    # Pitch/BARS remain continuous with each reader using its own bank.
    for track in range(16):
        put(wire, 0xDA + track * 0x60, 16384)
        put(wire, 0xEA + track * 0x60, 512)
    for block in range(8):
        frame(engine, wire)
        for lane in range(32):
            refs[lane].update(
                floats(engine, LANES + lane * 132 + 40, 1)[0],
                floats(engine, LANES + lane * 132 + 44, 1)[0],
            )
            compare(
                destination(engine, lane),
                refs[lane].process(32),
                f"continuous lane {lane} block {block}",
            )
    # Sharing the first source on track 16 preserves all remaining selected banks.
    put(wire, 0xE0 + 15 * 0x60, 1000)
    frame(engine, wire, 1 << 15)
    frame(engine, wire)
    require(
        engine.core.peek(LANES + 30 * 132) == engine.core.peek(LANES),
        "Identical source was not shared",
    )
    # Exercise the installed LP0 page/header hooks through original native
    # transfer routines. Preserve the page PCM in this reload fixture.
    bank0 = engine.core.peek(LANES)
    epoch0 = engine.core.peek(bank0 + 40)
    preserved = [
        (
            engine.core.peek(LANES + i * 264),
            engine.core.peek(engine.core.peek(LANES + i * 264) + 28),
        )
        for i in range(1, 15)
    ]
    core = engine.core
    core.poke(POOL + 0x30000, read(engine, POOL + 0x20000, 4096), 1)

    def transfer(pc, values, stack=None):
        regs = [f"{k}{i}" for k in ("R", "I", "M", "L") for i in range(16)]
        saved = {r: core.get_reg(st.UREG_CODES[r]) for r in regs}
        defaults = dict(M5=0, M6=1, M7=-1, M14=1, I6=0x200D7F00, I7=0x200D7EF8)
        defaults.update({f"L{i}": 0 for i in range(16)})
        defaults.update(values)
        for reg, value in defaults.items():
            core.set_reg(st.UREG_CODES[reg], st.Const(value))
        core.poke(0x200D7EFC, bytes(32), 1)
        if stack:
            core.poke(0x200D7F04, struct.pack("<3I", *stack), 1)
        engine.call(pc, 2000000)
        for reg, value in saved.items():
            core.set_reg(st.UREG_CODES[reg], value)

    transfer(0x1C403C, dict(R4=0x20000 >> 12, R8=POOL + 0x30000))
    require(engine.core.peek(bank0 + 48) == 0, "Mutation retained publication")
    frame(engine, wire)
    require(destination(engine, 0) == (0.0,) * 32, "Invalidated note read old bank")
    # A page covers two synthetic sources: both invalidate; all other sources survive.
    require(
        all(engine.core.peek(b + 28) == g for b, g in preserved[1:]),
        "Unrelated bank generation changed",
    )
    for track in (0, 1):
        offset = 0x20000 + track * 2048
        transfer(
            0x1C3FE5, dict(R4=1000 + track, R8=offset, R12=offset), [1024, 48000, 0]
        )
    for _ in range(100):
        frame(engine, wire)
    require(
        engine.core.peek(bank0 + 48) == engine.core.peek(bank0 + 40)
        and engine.core.peek(bank0 + 40) != epoch0,
        "Reload did not republish epoch",
    )
    require(destination(engine, 0) == (0.0,) * 32, "Reload took over invalidated note")
    frame(engine, wire, 65535)
    frame(engine, wire)
    require(
        all(engine.core.peek(LANES + i * 132 + 120) == 1 for i in range(32)),
        "Reload trigger did not restart custom",
    )
    # Unsupported stereo metadata must not reuse a ready mono bank.
    engine.core.poke(0x257810 + 1000 * 20 + 16, struct.pack("<I", 1), 1)
    frame(engine, wire, 1)
    frame(engine, wire)
    require(engine.core.peek(LANES + 120) == 0, "Stereo incorrectly reused mono bank")
    # Fresh stock/Plaits parity, and isolated capacity-pressure fallback.
    baseline = build_blob(True, family="integration", output=out / "integration")
    comparator = Dsp(arena(baseline, 4 * 1024 * 1024, bank=False))
    isolated = Dsp(arena(candidate, 4 * 1024 * 1024, bank=True))
    load_pcm(comparator, raw)
    load_pcm(isolated, raw)
    test = bytearray(template)
    for track in range(16):
        put(test, 0x94 + track * 2, 0)
    for offset, value in (
        (2, 60 * 256),
        (0xDA, 16384),
        (0xDC, 768),
        (0xDE, 0),
        (0xE0, 7),
        (0xE6, 0),
        (0xE8, 30720),
        (0xEA, 512),
        (0xEC, 25600),
    ):
        put(test, offset, value)
    parity = 0
    for typ in (0, 1, 3, 4, 6, 7):
        put(test, 0x94, typ)
        for trig in (0, 0, 0, 1, 0, 0, 0, 0):
            frame(comparator, test, trig)
            frame(isolated, test, trig)
            require(isolated.source == comparator.source, "Stock/Plaits PCM drift")
            parity += 1
    put(test, 0x94, 2)
    frame(isolated, test)
    frame(comparator, test)
    isolated.core.poke(CACHE + 4, struct.pack("<I", 96), 1)
    for _ in range(170):
        frame(isolated, test)
        frame(comparator, test)
    require(
        engine.core.peek(HANDOFF + 12) <= 0x6FFF00, "Large cache exceeded reservation"
    )
    require(
        any(e["state"] == 7 for e in entries(isolated)),
        "Reduced-budget fixture did not exercise pressure",
    )
    for trig in (1, 0, 0, 0):
        frame(isolated, test, trig)
        frame(comparator, test, trig)
        require(
            isolated.core.peek(LANES + 120) == 0, "Pressure trigger selected custom"
        )
        require(
            destination(isolated) == destination(comparator),
            "Pressure fallback PCM drift",
        )
    for track in range(16):
        put(wire, 0x94 + track * 2, 0)
    for _ in range(3):
        frame(engine, wire)
    require(
        all(engine.core.peek(LANES + i * 132 + 120) == 0 for i in range(32)),
        "Switch-away retained custom lane",
    )
    write_json(out / "banks.json", bank_entries)
    (out / "distinct-renderers.f32").write_bytes(
        struct.pack(
            "<" + str(sum(map(len, audio))) + "f", *(v for a in audio for v in a)
        )
    )
    (out / "synthetic-pcm.s16").write_bytes(
        struct.pack("<8192h", *(v for a in pcm for v in a))
    )
    report.update(
        status="passed",
        distinct_sources=16,
        readers=32,
        prepared_blocks=prepared,
        prepared_bytes=used,
        key_maximum_error=key_max,
        key_time_maximum_error=key_time_max,
        shared_instructions_per_block=dict(
            minimum=min(shared_counts), maximum=max(shared_counts)
        ),
        maximum_error=maximum,
        rms_error=rms,
        continuous_blocks=8,
        sharing=True,
        selective_reload=True,
        pressure_fallback_blocks=4,
        stock_plaits_parity_blocks=parity,
        r1_blob_sha256=hashlib.sha256(r1).hexdigest(),
        blob_sha256=sha256(out / "candidate/PLAITS_BLOB.bin"),
        main_sha256=sha256(out / "STRETCH_MAIN_OS.bin"),
        instructions_per_block=dict(minimum=min(counts), maximum=max(counts)),
        source_hashes=sources,
        source_fresh=source_hashes() == sources,
        output_boundary="Native STRETCH renderer before effects/final mix; not hardware timing",
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
