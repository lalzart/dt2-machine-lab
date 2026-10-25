#!/usr/bin/env python3
"""Compare optional CAPI rendering against stock and preserved R3 native DSP."""

# ruff: noqa: E402, I001
import argparse
import hashlib
import math
import os
import struct
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--package", type=Path, required=True)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.capicola_layout import STATE_BASE, address
from lab.capicola_memory import RESERVED_BASE
from lab.dsp import Dsp, header
from lab.formats import read_frames
from lab.runtime import STOCK_BLOB
import sharcldr

POOL = 0x8422B9C8
STRIDE, BACKEND, LAST_DEST = 276, 264, 272
AUTO, HANDOFF, CACHE, LANES = [
    address(x) for x in (0x200E4500, 0x200E4000, 0x200E7000, 0x200E8000)
]


# Helpers copied unchanged from the preserved native R3 validator.
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
    if engine.core.peek(LANES + lane * STRIDE + BACKEND) == 1:
        require(
            engine.core.peek(LANES + lane * STRIDE + LAST_DEST) == pointer,
            "Renderer destination differs from native pointer table",
        )
        return floats(engine, address(0x200EB000) + lane * 128, 32)
    return floats(engine, pointer, 32)


def sample_slot(engine, slot, offset, data):
    engine.core.poke(POOL + offset, struct.pack("<" + str(len(data)) + "h", *data), 1)
    engine.core.poke(
        0x257810 + slot * 20,
        struct.pack("<5I", offset, offset, len(data) * 2, 48000, 0),
        1,
    )


def frame(engine, wire, trig=0):
    put(wire, 0x22, trig)
    engine.frame(
        bytes(wire),
        instruction_limit=64_000_000 if manifest.get("capicola_source") else 4_000_000,
    )


def downstream(engine):
    from sharc_dac import float_to_q31, read_master_mix_pcm, read_ring_a_pcm

    left, right = read_master_mix_pcm(engine.core.peek)
    ring = read_ring_a_pcm(engine.core.peek, engine.core.peek(0x25F780))
    # Pinned native execution negates BOTH channels after FUN_1c74a1.
    # Independent stock and pre-negation breakpoint audit retained under
    # capicola-output-audit-01; do not infer physical output polarity here.
    converted = [
        float_to_q31(v) for pair in zip(left, right, strict=True) for v in pair
    ]
    expected = [(-v + 2**31) % 2**32 - 2**31 for v in converted]
    errors = [abs(a - b) for a, b in zip(ring.interleaved_q31(), expected, strict=True)]
    if max(errors) > 1:
        write_json(
            out / "failed-downstream.json",
            dict(
                flag=engine.core.peek(0x25F780),
                master_left=left,
                master_right=right,
                actual=ring.interleaved_q31(),
                expected=expected,
                errors=errors,
                halves=[read(engine, 0x261CC8 + i * 256, 256).hex() for i in range(2)],
            ),
        )
    require(all(math.isfinite(v) for v in left + right), "Nonfinite master mix")
    require(max(errors) <= 1, "DAC-facing ring differs from native master conversion")
    return dict(
        master_left=left,
        master_right=right,
        ring_left=ring.left,
        ring_right=ring.right,
        half_written=ring.half_written,
        conversion_maximum_lsb=max(errors),
        unadjusted_maximum_lsb=max(
            abs(a - b) for a, b in zip(ring.interleaved_q31(), converted, strict=True)
        ),
    )


report = dict(status="running", hardware_verified=False, firmware="OS1.16")
sources = source_hashes()
replies = []
statuses = []


def reply(engine):
    base = 0x266220 + ((engine.core.peek(0x261CA4) & 1) << 12)
    raw = read(engine, base, 0xABC)
    result = bytearray(raw)
    result[::2], result[1::2] = raw[1::2], raw[::2]
    word = int.from_bytes(result[0x1A:0x1C], "big")
    require(word & 0xF000 == 0xD000 and word & 255 <= 6, "Native reply tag")
    replies.append(bytes(result))
    statuses.append(dict(track=(word >> 8) & 15, state=word & 255, word=word))
    return word


def backends(engine):
    return [engine.core.peek(LANES + i * STRIDE + BACKEND) for i in range(32)]


def check_pcm(actual, expected, label, exact=False):
    require(all(math.isfinite(v) for v in actual), "Nonfinite " + label)
    errors = [abs(x - y) for x, y in zip(actual, expected, strict=True)]
    maximum = max(errors)
    rms = math.sqrt(sum(x * x for x in errors) / len(errors))
    require(
        (actual == expected) if exact else maximum <= 1e-4 and rms <= 1e-5,
        f"{label} max={maximum} rms={rms}",
    )
    return maximum


try:
    package = a.package.resolve()
    manifest = json.loads((package / "manifest.json").read_text())
    blob = (package / manifest["dsp"]["path"]).read_bytes()
    require(
        hashlib.sha256(blob).hexdigest() == manifest["dsp"]["sha256"],
        "Package DSP changed",
    )
    r3path = ROOT / "out/runs/combined-package-03/firmware/PLAITS_BLOB.bin"
    require(
        sha256(r3path)
        == "0cfb6c8315bd2db0e7346527c2834907fa7d131b0b55faf04f047d2ebb801faf",
        "Preserved R3 drift",
    )
    if manifest.get("capicola_source"):
        from lab.dsp_build import build_blob

        source_base = out / "source-base"
        build_blob(
            True,
            family="capicola-stretch-live",
            layout="reserved-state",
            runtime_variant="source",
            output=source_base,
        )
        r3path = source_base / "PLAITS_BLOB.bin"
        report["comparator"] = (
            "Source playback core without toggle; full original-source PCM checked separately"
        )
    elif manifest.get("capicola_quality"):
        from lab.dsp_build import build_blob

        # Routing/latching comparator uses the same quality core without the
        # toggle wrapper. Independent source/target fidelity is checked by the
        # dedicated quality checker, never inferred from this comparator.
        quality_base = out / "quality-base"
        build_blob(
            True,
            family="capicola-stretch-live",
            layout="reserved-state",
            runtime_variant="quality",
            output=quality_base,
        )
        r3path = quality_base / "PLAITS_BLOB.bin"
        report["comparator"] = (
            "Quality core without toggle wrapper; independent Granule check is separate"
        )
    capture = ROOT / "out/runs/capicola-panel-08/capicola.dtfr"
    load = ROOT / "out/runs/capicola-panel-05/flexbus.raw"
    require(
        sha256(capture)
        == "3e6a3f0f319ca2c27087a77fb09d73f0b88922c2eabec0bb42651de8a1596290",
        "Control fixture drift",
    )
    require(
        sha256(load)
        == "85f122f352abf80e5ae7fd11e9d5f05e5cc8b3e0526cd694d4fe420b6707e844",
        "LP0 fixture drift",
    )
    toggle = Dsp(arena(blob, 4 * 1024 * 1024, bank=True))
    custom = Dsp(arena(r3path.read_bytes(), 4 * 1024 * 1024, bank=True))
    stock = Dsp(arena(STOCK_BLOB.read_bytes(), 4 * 1024 * 1024, bank=False))
    engines = (toggle, custom, stock)
    for e in engines:
        load_pcm(e, load.read_bytes())
    template = next(
        w
        for w in read_frames(capture)
        if int.from_bytes(w[0x94:0x96], "big") == 8
        and int.from_bytes(w[0x22:0x24], "big") & 1
    )
    wire = bytearray(template)
    pcm = [
        [int(12000 * math.sin(i * (t + 1) * 0.08)) for i in range(512)]
        for t in range(16)
    ]
    for t in range(16):
        put(wire, 0x94 + t * 2, 2)
        put(wire, 2 + t * 2, 60 * 256)
        put(wire, 0x34 + t * 2, 100 * 256)
        b = 0xDA + t * 0x60
        wire[b : b + 0x60] = template[0xDA:0x13A]
        for off, value in (
            (0, 16384 + ((t % 3) - 1) * 3072),
            (2, (0, 256, 512, 768)[t % 4]),
            (4, 256),
            (6, 1000 + t),
            (12, 0),
            (14, 30720),
            (16, (t % 4) * 256),
            (18, 25600),
        ):
            put(wire, b + off, value)

    def step(trigger=0):
        if manifest.get("capicola_source") and trigger:
            # An always-ON comparator has prior grains that an OFF->ON track
            # does not. Match that INITIAL HISTORY before executing the same
            # real trigger, retaining exact PCM tolerances and production code.
            prior = backends(toggle)
            for track in range(16):
                raw = int.from_bytes(
                    wire[0xDE + track * 0x60 : 0xE0 + track * 0x60], "big"
                )
                if trigger & (1 << track) and 128 <= raw <= 256:
                    for lane in (track * 2, track * 2 + 1):
                        if not prior[lane]:
                            custom.core.poke(LANES + lane * STRIDE, bytes(256), 1)
        for e in engines:
            frame(e, wire, trigger)
        reply(toggle)

    step()
    for e in engines:
        for t, data in enumerate(pcm):
            sample_slot(e, 1000 + t, 0x20000 + t * 2048, data)
    step(65535)
    step()
    require(not any(backends(toggle)), "Unready ON selected custom")
    blocks = 0
    while toggle.core.peek(HANDOFF + 8) != 16 and blocks < 1500:
        step()
        blocks += 1
    require(
        toggle.core.peek(HANDOFF + 8) == 16 and custom.core.peek(HANDOFF + 8) == 16,
        "Distinct banks not ready",
    )
    require(not any(backends(toggle)), "Preparation changed active engine")
    print("Sixteen distinct banks ready", blocks, flush=True)
    # Force only the documented control inputs; original frame handler performs
    # trigger allocation, playback and all downstream processing.
    for t in range(16):
        put(wire, 0xDE + t * 0x60, 0)
    step(65535)
    step()
    require(not any(backends(toggle)), "OFF did not select stock")
    off_peak = 0
    on_max = 0
    ignored_off_difference = False
    for b in range(24):
        if b == 4:
            for t in range(16):
                put(wire, 0xDE + t * 0x60, 256)
        if b == 12:
            for t in range(16):
                put(wire, 0xDE + t * 0x60, 0)
        step(65535 if b in (8, 16) else 0)
        if b in (8, 16):
            # Native trigger transport schedules the two lanes across blocks,
            # matching the preserved R3 validator's trigger/settle sequence.
            step()
        want = 1 if 8 <= b < 16 else 0
        require(backends(toggle) == [want] * 32, f"Trigger latching block {b}")
        for lane in range(32):
            actual = destination(toggle, lane)
            expected = destination(custom if want else stock, lane)
            on_max = max(
                on_max,
                check_pcm(actual, expected, f"lane{lane}/block{b}", exact=not want),
            )
            if not want:
                off_peak = max(off_peak, max(map(abs, actual)))
                ignored_off_difference |= actual != destination(custom, lane)
        if b < 8:
            require(
                downstream(toggle) == downstream(stock),
                "OFF final output differs from stock",
            )
    require(off_peak > 1e-5 and ignored_off_difference, "Silent/vacuous stock oracle")
    # Sixteen mixed modes and malformed raw values; per-track guard must remain
    # independent while source cache stays shared.
    modes = [0, 127, 128, 256, 257, 65535] * 3
    for t in range(16):
        put(wire, 0xDE + t * 0x60, modes[t])
    step(65535)
    step()
    expected = [int(128 <= modes[i // 2] <= 256) for i in range(32)]
    require(backends(toggle) == expected, "Sixteen-track mixed routing")
    mixed_words = []
    for _ in range(16):
        active_before = [
            toggle.core.peek(0x2412CC + lane * 0x1D8 + 0x1B8, 1) for lane in range(32)
        ]
        step()
        row = dict(statuses[-1])
        track = row["track"]
        row["expected"] = (
            (3 if expected[track * 2] else 4)
            if any(active_before[track * 2 : track * 2 + 2])
            else 2
        )
        mixed_words.append(row)
        for lane, want in enumerate(expected):
            check_pcm(
                destination(toggle, lane),
                destination(custom if want else stock, lane),
                f"mixed lane{lane}",
                exact=not want,
            )
    require(
        {x["track"] for x in mixed_words} == set(range(16)),
        "Status did not visit all tracks",
    )
    for x in mixed_words:
        require(
            x["state"] == x["expected"],
            "Status not actual backend",
        )
    # Both voices active but different latched engines is an informational MIX.
    toggle.core.poke(LANES + BACKEND, struct.pack("<I", 1), 1)
    toggle.core.poke(LANES + STRIDE + BACKEND, struct.pack("<I", 0), 1)
    toggle.core.poke(0x2412CC + 0x1B8, b"\1", 1)
    toggle.core.poke(0x2414A4 + 0x1B8, b"\1", 1)
    # Ordinary frame execution can retire forced state; call only compiled
    # maintenance here, using the same native-call ABI as the existing harness.
    listing = (package / "firmware/listing.txt").read_text()
    import re

    maintenance = int(
        re.search(r"(?m)^cap_maintenance\.:\n\s+([0-9a-f]+)", listing)[1], 16
    )
    # Set only fixture scheduler index to the round that broadcasts track 0.
    toggle.core.poke(AUTO + 28, struct.pack("<I", 15), 1)
    toggle.call(maintenance, 4_000_000)
    require(reply(toggle) & 255 == 5, "Mixed native lane status")

    # Explicit idle fixture proves WAIT/READY/UNSUP, independently of requested
    # state. Native maintenance still resolves metadata and publication.
    def idle():
        for lane in range(32):
            toggle.core.poke(0x2412CC + lane * 0x1D8 + 0x1B8, bytes(1), 1)

    idle()
    sample_slot(toggle, 1000, 0x30000, pcm[0])
    toggle.core.poke(AUTO + 28, struct.pack("<I", 15), 1)
    frame(toggle, wire)
    require(reply(toggle) & 255 == 1, "Idle eligible source not WAIT")
    for _ in range(80):
        frame(toggle, wire)
        reply(toggle)
    toggle.core.poke(AUTO + 28, struct.pack("<I", 15), 1)
    frame(toggle, wire)
    require(reply(toggle) & 255 == 2, "Idle published source not READY")
    toggle.core.poke(0x257810 + 1000 * 20 + 16, struct.pack("<I", 1), 1)
    toggle.core.poke(AUTO + 28, struct.pack("<I", 15), 1)
    frame(toggle, wire)
    require(reply(toggle) & 255 == 6, "Unsupported idle source not UNSUP")
    put(wire, 0xDE, 256)
    frame(toggle, wire, 1)
    frame(toggle, wire)
    require(backends(toggle)[:2] == [0, 0], "Stereo reused ready mono bank")
    # Different machines pass the same original interface to the unchanged R3
    # renderer. Fresh instances avoid inherited filters/effect-tail history.
    isolated = Dsp(arena(blob, 4 * 1024 * 1024, bank=True))
    comparator = Dsp(arena(r3path.read_bytes(), 4 * 1024 * 1024, bank=True))
    for e in (isolated, comparator):
        load_pcm(e, load.read_bytes())
    test = bytearray(template)
    for t in range(16):
        put(test, 0x94 + t * 2, 0)
    parity = 0
    for typ in (0, 1, 3, 4, 5, 6, 7):
        put(test, 0x94, typ)
        for trig in (0, 0, 0, 1, 0, 0, 0, 0):
            frame(isolated, test, trig)
            frame(comparator, test, trig)
            require(isolated.source == comparator.source, "Other-machine PCM drift")
            parity += 1
    report.update(
        status="passed",
        sources=sources,
        prepared_blocks=blocks,
        bank_bytes=toggle.core.peek(HANDOFF + 12),
        stock_exact=True,
        capicola_maximum_error=on_max,
        negative_ignored_off_detected=True,
        mixed_tracks=16,
        trigger_latched=True,
        unsupported_fallback=True,
        idle_states=True,
        other_machine_parity_blocks=parity,
        stock_final_mix_exact_before_engine_change=True,
        reply_snapshots=len(replies),
        instruction_limit_per_block=64_000_000
        if manifest.get("capicola_source")
        else 4_000_000,
        maximum_native_block_instructions=max(toggle.block_instructions),
        source_comparator_history_matched=bool(manifest.get("capicola_source")),
        scope="Native frame handler and final mix; synthetic mono fixtures plus captured LP0; MIX status includes explicit lane-state fixture",
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    (out / "native-replies.bin").write_bytes(b"".join(replies))
    write_json(out / "native-statuses.json", statuses)
    write_json(out / "report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))
