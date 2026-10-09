#!/usr/bin/env python3
"""Bounded native OS1.16 STRETCH control/renderer audit, without DSP patches.

Reuses captured sample transfers. Control cases are explicit modified wire
fixtures, not a claim of new panel gestures or Capicola playback.
"""

# ruff: noqa: E402, I001
import argparse
import itertools
import json
import math
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
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--capture", required=True, type=Path)
p.add_argument("--sample-load", required=True, type=Path)
args = p.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
doctor()
from lab.dsp import Dsp, header
from lab.formats import read_frames
from lab.runtime import STOCK_BLOB
import sharcldr
import sharc_trace as st
from sharc_transpile_run import OPT_STOP_PC

report = dict(status="running", firmware="Digitakt II OS1.16")
try:
    sources = source_hashes()
    capture = args.capture.resolve()
    boot = args.sample_load.resolve()
    require(
        json.loads((capture / "capture.json").read_text())["status"] == "passed",
        "Capture failed",
    )
    wire_path, samples_path = capture / "capicola.dtfr", boot / "flexbus.raw"
    report["inputs"] = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in (wire_path, samples_path, STOCK_BLOB)
    }
    raw = samples_path.read_bytes()
    require(len(raw) % 4100 == 0, "Incomplete sample transfer")
    pages = [struct.unpack_from("<I", raw, pos)[0] for pos in range(0, len(raw), 4100)]
    pages = [tag for tag in pages if tag < 0x19200]
    require(pages and max(pages) < 0x1000, "Bound sample RAM to 16MiB")
    pool = 0x8422B9C8
    extent = (max(pages) + 2) * 4096 + 1024
    blob = STOCK_BLOB.read_bytes()
    split = sharcldr.parse_blocks(blob)[-1]["offset"]
    engine = Dsp(
        blob[:split] + header(pool - 1024, extent) + bytes(extent) + blob[split:]
    )
    core = engine.core
    registers = [f"{prefix}{i}" for prefix in ("R", "I", "M", "L") for i in range(16)]
    saved = {r: core.get_reg(st.UREG_CODES[r]) for r in registers}
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

    wires = read_frames(wire_path)
    wire = bytearray(
        next(
            w
            for w in wires
            if int.from_bytes(w[0x94:0x96], "big") == 8
            and int.from_bytes(w[0x22:0x24], "big") & 1
        )
    )

    def put(offset, value):
        wire[offset : offset + 2] = value.to_bytes(2, "big")

    put(0x94, 2)
    put(2, 60 * 256)  # Explicit C5 note, independent of prior prototype capture.
    put(0x22, 0)
    put(0xDE, 0)  # Stock STRETCH's unexposed slot; no RATE overlay.
    put(0xEC, 25600)
    for _ in range(3):
        engine.frame(bytes(wire))

    def float_at(address):
        return struct.unpack("<f", struct.pack("<I", core.peek(address)))[0]

    def position_at(address):
        low, high = core.peek(address), core.peek(address + 4)
        require(high < 0x80000000, "Negative position")
        return (high << 1) | (low >> 31)

    cases = []
    for play, bars, tune, region in itertools.product(
        (0, 256, 512, 768),
        (0, 256, 512, 768),
        (1024, 13312, 16384, 19456, 31744),
        ((0, 30720), (7680, 15360), (15360, 30720)),
    ):
        start, length = region
        for offset, value in (
            (0xDA, tune),
            (0xDC, play),
            (0xE6, start),
            (0xE8, length),
            (0xEA, bars),
        ):
            put(offset, value)
        put(0x22, 1)
        engine.frame(bytes(wire))
        put(0x22, 0)
        engine.frame(bytes(wire))
        engine.frame(bytes(wire))
        voice = 0x2412CC
        pitch, advance = float_at(voice + 0x1CC), float_at(voice + 0x1C8)
        require(
            math.isfinite(pitch)
            and pitch > 0
            and math.isfinite(advance)
            and advance > 0,
            "Invalid native controls",
        )
        expected_pitch = 2 ** ((tune / 256 - 64) / 12)
        require(abs(pitch - expected_pitch) < 2e-5, "Native pitch mapping differs")
        flags = [core.peek(voice + offset, 1) for offset in (0x1BB, 0x1BC)]
        require(
            flags == [(play >> 8) < 2, (play >> 8) in (1, 2)],
            "Native PLAY mapping differs",
        )
        cases.append(
            dict(
                play_raw=play,
                bars_raw=bars,
                bars=1 << (bars >> 8),
                tune_raw=tune,
                start_raw=start,
                length_raw=length,
                pitch=pitch,
                advance=advance,
                reverse=flags[0],
                loop=flags[1],
                frames=core.peek(voice + 0x188),
                native_start=position_at(voice + 0x198),
                native_end=position_at(voice + 0x1A0),
            )
        )
    require(len(cases) == 240, "Matrix incomplete")
    for row in cases:
        baseline = next(
            other
            for other in cases
            if other["play_raw"] == row["play_raw"]
            and other["tune_raw"] == row["tune_raw"]
            and other["start_raw"] == row["start_raw"]
            and other["length_raw"] == row["length_raw"]
            and other["bars_raw"] == 0
        )
        require(
            abs(row["advance"] * row["bars"] - baseline["advance"]) < 1e-7,
            "Native BARS timing differs",
        )
    write_json(out / "native-control-cases.json", cases)
    write_json(
        out / "adapted-wire.json",
        dict(
            source="Captured prototype wire with explicit stock STRETCH control replacements",
            patches=dict(type=2, note=60 * 256, unused_slot=0, level=25600),
            controls="PLAY x BARS x TUNE x STRT/LEN; native firmware computes all output fields",
        ),
    )
    require(source_hashes() == sources, "Source drift")
    report.update(
        status="passed",
        native_cases=len(cases),
        lp0_transfers=len(raw) // 4100,
        pitch_range=[min(c["pitch"] for c in cases), max(c["pitch"] for c in cases)],
        advance_range=[
            min(c["advance"] for c in cases),
            max(c["advance"] for c in cases),
        ],
        native_pitch_offset="voice+0x1cc",
        native_advance_offset="voice+0x1c8",
        sources=sources,
        scope="Native stock control computation on modified wire fixtures. No Capicola DSP patch, new panel capture, output audio, listening or physical timing proof.",
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "sources"}, indent=2
        )
    )
