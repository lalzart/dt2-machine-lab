#!/usr/bin/env python3
"""Build and execute the original OS1.16 STRETCH path with Capicola.

Uses captured LP0 PCM and explicitly adapted control wire. Output is the actual
STRETCH destination before the final mix, never the generic voice-buffer tap.
"""

# ruff: noqa: E402, I001
import argparse
import array
import itertools
import json
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
from lab.capicola_memory import BANK_BASE, RESERVED_BASE
from lab.capicola_memory import patch_cpu as reserve
from lab.dsp import Dsp, header
from lab.flex_native_build import patch_cpu as flex
from lab.formats import read_frames
from lab.plaits import build_blob, build_cpu
from lab.plaits_menu import patch_cpu as menu
from lab.runtime import STOCK_BLOB

import sharc_trace as st
import sharcldr
from capicola_stretch_reference import Reader
from sharc_transpile_run import OPT_STOP_PC

POOL = 0x8422B9C8
AUTO, HANDOFF, BANK, LANES = [
    address(a) for a in (0x200E4500, 0x200E4000, 0x200E4100, 0x200E4800)
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


def load_pcm(engine, raw):
    core = engine.core
    regs = [f"{k}{i}" for k in ("R", "I", "M", "L") for i in range(16)]
    saved = {r: core.get_reg(st.UREG_CODES[r]) for r in regs}
    core.set_option(OPT_STOP_PC, 0x1C834A)
    for pos in range(0, len(raw), 4100):
        core.poke(0x268240, raw[pos : pos + 4100], 1)
        values = dict(
            M5=0,
            M6=1,
            M7=-1,
            M14=1,
            I6=0x200D7F00,
            I7=0x200D7EF8,
            R4=0,
            R8=4,
            R12=0x268220,
        )
        values.update({f"L{i}": 0 for i in range(16)})
        for reg, value in values.items():
            core.set_reg(st.UREG_CODES[reg], st.Const(value))
        core.poke(0x200D7EFC, bytes(32), 1)
        core.fresh_call(0x1C7E1F)
        core.run(50000)
        require(core.pc() == 0x1C834A, "LP0 callback did not resubmit")
    core.set_option(OPT_STOP_PC, 0)
    for reg, value in saved.items():
        core.set_reg(st.UREG_CODES[reg], value)


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
    count, frames = core.peek(BANK + 16), core.peek(BANK + 20)
    values = floats(engine, core.peek(BANK), count)
    wholes = [core.peek(core.peek(BANK + 4) + 4 * i) for i in range(count)]
    fractions = [core.peek(core.peek(BANK + 8) + 4 * i) for i in range(count)]
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


try:
    sources = source_hashes()
    for path, expected in EXPECTED_INPUTS.items():
        require(sha256(path) == expected, "Fixture drift: " + str(path))
    raw = LOAD.read_bytes()
    pages = [struct.unpack_from("<I", raw, p)[0] for p in range(0, len(raw), 4100)]
    extent = (max(p for p in pages if p < 0x19200) + 2) * 4096 + 1024
    require(extent <= 16 * 1024 * 1024, "PCM allocation bound")
    candidate = build_blob(
        True,
        family="capicola-stretch",
        layout="reserved-state",
        output=out / "candidate",
    )
    repeated = build_blob(
        True, family="capicola-stretch", layout="reserved-state", output=out / "repeat"
    )
    require(candidate == repeated, "Nondeterministic native build")
    build_cpu(family="integration")
    image = reserve(menu(flex((out / "PLAITS_MAIN_OS.bin").read_bytes())[0])[0])[0]
    (out / "STRETCH_MAIN_OS.bin").write_bytes(image)
    require(
        sha256(out / "STRETCH_MAIN_OS.bin")
        == "7f19553cc4bbdf170378ba67c85bedcf4a57a1d10a4a9751080e249547bd8ff3",
        "Original STRETCH CPU interface drift",
    )
    engine = Dsp(arena(candidate, extent, bank=True))
    original_frame = engine.frame

    def recorded_frame(wire):
        wire_log.append(bytes(wire))
        return original_frame(wire)

    engine.frame = recorded_frame
    stock = Dsp(arena(STOCK_BLOB.read_bytes(), extent, bank=False))
    load_pcm(engine, raw)
    load_pcm(stock, raw)
    template = next(
        w
        for w in read_frames(CAPTURE)
        if int.from_bytes(w[0x94:0x96], "big") == 8
        and int.from_bytes(w[0x22:0x24], "big") & 1
    )
    wire = bytearray(template)
    for offset, value in (
        (0x94, 2),
        (2, 60 * 256),
        (0x22, 0),
        (0x24, 0),
        (0xDE, 0),
        (0xDA, 16384),
        (0xDC, 768),
        (0xE6, 0),
        (0xE8, 30720),
        (0xEA, 512),
        (0xEC, 25600),
    ):
        put(wire, offset, value)
    for _ in range(3):
        engine.frame(bytes(wire))
        stock.frame(bytes(wire))
    # Trigger while preparation is pending; compare actual stock destinations.
    fallback_blocks = 0
    for event in (1, 0, 0, 0):
        put(wire, 0x22, event)
        engine.frame(bytes(wire))
        stock.frame(bytes(wire))
        require(destination(engine) == destination(stock), "Stock fallback PCM drift")
        require(engine.core.peek(LANES + 120) == 0, "Unready trigger selected custom")
        fallback_blocks += 1
    prep_blocks = 0
    while engine.core.peek(HANDOFF + 8) != 1 and prep_blocks < 500:
        engine.frame(bytes(wire))
        prep_blocks += 1
    require(engine.core.peek(HANDOFF + 8) == 1, "Preparation did not publish")
    require(
        engine.core.peek(LANES + 120) == 0 and engine.core.peek(LANES + 124) == 0,
        "Mid-note takeover",
    )
    require(engine.core.peek(BANK) == BANK_BASE, "Unowned bank storage")
    print(
        f"Native preparation ready after {prep_blocks} additional blocks; stock fallback and no takeover passed",
        flush=True,
    )
    # Native firmware computes controls and both lanes' trigger state.
    cases, rendered, worst_max, worst_rms = [], array.array("f"), 0, 0
    for play, bars, tune, region in itertools.product(
        (0, 256, 512, 768),
        (0, 256, 512, 768),
        (1024, 13312, 16384, 19456, 31744),
        ((0, 30720), (7680, 15360), (15360, 30720)),
    ):
        for offset, value in (
            (0xDC, play),
            (0xEA, bars),
            (0xDA, tune),
            (0xE6, region[0]),
            (0xE8, region[1]),
            (0x22, 1),
        ):
            put(wire, offset, value)
        engine.frame(bytes(wire))
        put(wire, 0x22, 0)
        engine.frame(bytes(wire))
        require(
            engine.core.peek(LANES + 120) == 1,
            f"Ready trigger failed to select Capicola: {(play, bars, tune, region)}",
        )
        require(
            engine.core.peek(LANES + 64) == 32,
            "Native transport did not start at actual trigger",
        )
        ref = reference(engine)
        write_json(
            out / "last-reader.json",
            dict(
                voice=[engine.core.peek(0x2412CC + i * 4) for i in range(118)],
                reader=[engine.core.peek(LANES + i * 4) for i in range(33)],
                destination=engine.core.peek(0x24EF2C),
                pitch=ref.pitch,
                advance=ref.rate,
                start=ref.start,
                end=ref.end,
                reverse=ref.reverse,
                loop=ref.loop,
            ),
        )
        actual, expected = [], []
        for block in range(4):
            if block:
                engine.frame(bytes(wire))
            actual.extend(destination(engine))
            expected.extend(ref.process(32))
        maximum, rms = compare(actual, expected, str((play, bars, tune, region)))
        worst_max, worst_rms = max(worst_max, maximum), max(worst_rms, rms)
        rendered.extend(actual)
        cases.append(
            dict(
                play=play,
                bars=bars,
                tune=tune,
                region=region,
                maximum_error=maximum,
                rms_error=rms,
                destination=engine.core.peek(LANES + 128),
            )
        )
    write_json(out / "native-cases.json", cases)
    (out / "native-stretch-destinations.f32").write_bytes(rendered.tobytes())
    print(f"{len(cases)} native STRETCH destination cases passed", flush=True)
    deep_cases = []
    for play in (0, 256, 512, 768):
        for offset, value in (
            (0xDC, play),
            (0xDA, 31744),
            (0xEA, 768),
            (0xE6, 7680),
            (0xE8, 15360),
            (0x22, 1),
        ):
            put(wire, offset, value)
        engine.frame(bytes(wire))
        put(wire, 0x22, 0)
        engine.frame(bytes(wire))
        ref = reference(engine)
        actual, expected = [], []
        for block in range(64):
            if block:
                engine.frame(bytes(wire))
            actual.extend(destination(engine))
            expected.extend(ref.process(32))
        maximum, rms = compare(actual, expected, f"2048-frame PLAY {play}")
        deep_cases.append(
            dict(play=play, frames=2048, maximum_error=maximum, rms_error=rms)
        )
    write_json(out / "deep-cases.json", deep_cases)
    # Continuous TUNE/BARS changes consume the values actually used at each
    # render boundary; the native control update has a one-block pipeline.
    for offset, value in (
        (0xDC, 512),
        (0xDA, 16384),
        (0xEA, 512),
        (0xE6, 0),
        (0xE8, 30720),
        (0x22, 1),
    ):
        put(wire, offset, value)
    engine.frame(bytes(wire))
    put(wire, 0x22, 0)
    engine.frame(bytes(wire))
    live_ref = reference(engine)
    compare(destination(engine), live_ref.process(32), "live update initial block")
    live_blocks = 0
    for tune, bars in ((19456, 0), (13312, 768), (31744, 256), (1024, 512)):
        put(wire, 0xDA, tune)
        put(wire, 0xEA, bars)
        for _ in range(8):
            engine.frame(bytes(wire))
            live_ref.update(
                floats(engine, LANES + 40, 1)[0], floats(engine, LANES + 44, 1)[0]
            )
            compare(
                destination(engine),
                live_ref.process(32),
                f"live controls {tune}/{bars}",
            )
            require(
                engine.core.peek(LANES + 8) == int(live_ref.ideal)
                and engine.core.peek(LANES + 20)
                == int((live_ref.ideal - int(live_ref.ideal)) * 2**24),
                "Live controls reset timing cursor",
            )
            live_blocks += 1
    # LP0 rewrites invalidate publication before any subsequent render.
    old_generation = engine.core.peek(BANK + 28)
    load_pcm(engine, raw)
    require(engine.core.peek(HANDOFF + 8) == 0, "LP0 rewrite retained publication")
    engine.frame(bytes(wire))
    require(
        destination(engine) == (0.0,) * 32, "Invalidated custom note read retired bank"
    )
    reloaded = 0
    while engine.core.peek(HANDOFF + 8) != 1 and reloaded < 500:
        engine.frame(bytes(wire))
        reloaded += 1
    require(
        engine.core.peek(HANDOFF + 8) == 1
        and engine.core.peek(BANK + 28) != old_generation,
        "Reload did not prepare new generation",
    )
    require(destination(engine) == (0.0,) * 32, "Reload took over invalidated note")
    # Independent PLAY/tune/bar settings, all sixteen tracks sharing one sample.
    shared = bytearray(wire)
    for track in range(16):
        put(shared, 0x94 + track * 2, 2)
        put(shared, 2 + track * 2, 60 * 256)
        put(shared, 0x34 + track * 2, 100 * 256)
        block = 0xDA + track * 0x60
        shared[block : block + 0x60] = wire[0xDA:0x13A]
        for offset, value in (
            (0, 16384 + ((track % 3) - 1) * 3072),
            (2, (256, 512)[track % 2]),
            (6, 7),
            (12, 0),
            (14, 30720),
            (16, (track % 4) * 256),
        ):
            put(shared, block + offset, value)
    put(shared, 0x22, 0)
    for _ in range(3):
        engine.frame(bytes(shared))
    put(shared, 0x22, 65535)
    engine.frame(bytes(shared))
    put(shared, 0x22, 0)
    engine.frame(bytes(shared))
    references = [reference(engine, lane) for lane in range(32)]
    require(
        all(engine.core.peek(LANES + lane * 132 + 120) == 1 for lane in range(32)),
        "All-track bank sharing failed",
    )
    shared_pcm = [[] for _ in range(32)]
    shared_instruction_counts = [engine.block_instructions[-1]]
    for block in range(8):
        if block:
            engine.frame(bytes(shared))
            shared_instruction_counts.append(engine.block_instructions[-1])
        for lane in range(32):
            output = destination(engine, lane)
            compare(
                output,
                references[lane].process(32),
                f"shared lane {lane} block {block}",
            )
            shared_pcm[lane].extend(output)
    # BARS changes the ideal cursor immediately; its audible splice correction
    # starts only after the leash is exceeded. At this short 256-frame boundary
    # six pitch/direction combinations, and twelve timing/pitch states, differ.
    distinct_pcm = len({tuple(samples) for samples in shared_pcm})
    distinct_transport = len(
        {
            (
                engine.core.peek(LANES + lane * 132 + 8),
                engine.core.peek(LANES + lane * 132 + 20),
                engine.core.peek(LANES + lane * 132 + 32),
            )
            for lane in range(32)
        }
    )
    write_json(
        out / "shared-readers.json",
        dict(
            distinct_pcm=distinct_pcm,
            distinct_transport=distinct_transport,
            readers=[
                dict(
                    lane=lane,
                    position=engine.core.peek(LANES + lane * 132 + 64),
                    ideal_whole=engine.core.peek(LANES + lane * 132 + 8),
                    ideal_fraction=engine.core.peek(LANES + lane * 132 + 20),
                    destination=engine.core.peek(LANES + lane * 132 + 128),
                )
                for lane in range(32)
            ],
        ),
    )
    require(
        distinct_pcm >= 6 and distinct_transport >= 12,
        "Shared controls did not yield independent playback/state",
    )
    # A different eligible source falls back instead of evicting the bank still
    # referenced by the other fifteen tracks. Synthetic slot metadata is an
    # explicit admission negative, not a captured sample upload.
    offset = extent - 8192
    engine.core.poke(
        0x257810 + 1023 * 20, struct.pack("<5I", offset, offset, 4800, 48000, 0), 1
    )
    put(shared, 0xE0 + 0x60, 1023)
    put(shared, 0x22, 2)
    engine.frame(bytes(shared))
    put(shared, 0x22, 0)
    engine.frame(bytes(shared))
    require(
        engine.core.peek(LANES + 2 * 132 + 120) == 0
        and engine.core.peek(LANES + 3 * 132 + 120) == 0,
        "Uncached distinct sample did not fall back",
    )
    require(
        engine.core.peek(HANDOFF + 8) == 1
        and engine.core.peek(AUTO + 4) == POOL + 0x40,
        "Distinct sample evicted a referenced shared bank",
    )
    # Stereo sources use stock, even if the same PCM address has a ready mono
    # bank. Check the two lanes of the sole remaining type-2 track.
    engine.core.poke(0x257810 + 7 * 20 + 16, struct.pack("<I", 1), 1)
    for track in range(1, 16):
        put(shared, 0x94 + track * 2, 0)
    put(shared, 0x22, 1)
    engine.frame(bytes(shared))
    put(shared, 0x22, 0)
    engine.frame(bytes(shared))
    require(
        engine.core.peek(LANES + 120) == 0 and engine.core.peek(LANES + 132 + 120) == 0,
        "Unsupported stereo trigger did not fall back",
    )
    require(
        all(engine.core.peek(LANES + lane * 132 + 120) == 0 for lane in range(2, 32)),
        "Switch-away retained Capicola backend state",
    )
    # Fresh native stock/Plaits comparators run through the full enclosing block.
    baseline = build_blob(
        True, family="integration", output=out / "integration-baseline"
    )
    comparator = Dsp(arena(baseline, extent, bank=False))
    isolated = Dsp(arena(candidate, extent, bank=True))
    load_pcm(comparator, raw)
    load_pcm(isolated, raw)
    parity_blocks = 0
    for typ in (0, 1, 3, 4, 6, 7):
        test = bytearray(wire)
        put(test, 0x94, typ)
        put(test, 0x22, 0)
        for event in (0, 0, 0, 1, 0, 0, 0, 0, 0, 0):
            put(test, 0x22, event)
            isolated.frame(bytes(test))
            comparator.frame(bytes(test))
            require(
                isolated.source == comparator.source,
                f"Stock/Plaits output changed for type {typ}",
            )
            parity_blocks += 1
    # Recorded image hashes are preserved; new optional family cannot alter old ones.
    old_images = {}
    for family, expected in {
        "capicola-selection": "9fd52edc63ccd428e076653311f796b0ea7e67758d28288b44351af76f6cf879",
        "capicola-controls": "ce51ec4ced24b1617ae35337c4bf7cdddf22a2d288f320d74fc3d636206f2c5f",
        "capicola-feedback": "459c667dee6850dc59f0582d20289ca1539cac2e6cd303032ca0003b091fc88e",
        "capicola-live-feedback": "8173d84db87e4d685047b6461d07cb30d6f87db592b420506d87c12664a6713b",
    }.items():
        # The recorded controls hash is its preserved LEGACY layout. Selection
        # and feedback hashes are the later reserved-state builds. Do not compare
        # two different placements or regenerate the expected hash on failure.
        layout = "legacy" if family == "capicola-controls" else "reserved-state"
        build_blob(True, family=family, layout=layout, output=out / family)
        digest = sha256(out / family / "PLAITS_BLOB.bin")
        require(digest == expected, "Prior image changed: " + family)
        old_images[family] = digest
    require(source_hashes() == sources, "Source drift during native execution")
    report.update(
        status="passed",
        native_cases=len(cases),
        deep_native_cases=deep_cases,
        continuous_control_blocks=live_blocks,
        stock_plaits_parity_blocks=parity_blocks,
        maximum_error=worst_max,
        rms_error=worst_rms,
        stock_fallback_blocks=fallback_blocks,
        preparation_blocks=prep_blocks,
        reload_blocks=reloaded,
        shared_readers=32,
        shared_tracks=16,
        shared_instructions_per_block=dict(
            minimum=min(shared_instruction_counts),
            maximum=max(shared_instruction_counts),
        ),
        old_images=old_images,
        source_hashes=sources,
        main_sha256=sha256(out / "STRETCH_MAIN_OS.bin"),
        blob_sha256=sha256(out / "candidate/PLAITS_BLOB.bin"),
        instructions_per_block=dict(
            minimum=min(engine.block_instructions),
            maximum=max(engine.block_instructions),
        ),
        inputs={str(p.relative_to(ROOT)): h for p, h in EXPECTED_INPUTS.items()},
        output_boundary="Actual native STRETCH destination; pre-final-mix; not physical timing or listening proof",
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    if wire_log:
        (out / "adapted-stretch.dtfr").write_bytes(
            b"DTFR\x01\0\0\0"
            + struct.pack("<I", len(wire_log))
            + b"".join(struct.pack("<I", len(wire)) + wire for wire in wire_log)
        )
    write_json(out / "report.json", report)
    print(
        json.dumps({k: v for k, v in report.items() if k != "source_hashes"}, indent=2)
    )
