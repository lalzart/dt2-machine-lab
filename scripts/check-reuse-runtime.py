#!/usr/bin/env python3
"""Paired prepared-SHARC comparison of reference, cached and trace-off variants."""

# ruff: noqa: E402
import argparse
import hashlib
import json
import math
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, source_hashes, write_json

config = settings()
if Path(sys.executable).absolute() != config["python"].absolute():
    os.execv(
        str(config["python"]), [str(config["python"]), "-B", __file__, *sys.argv[1:]]
    )
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
args = parser.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a new out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance = doctor()
import sharcldr
from sharc_dac import read_master_mix_pcm, read_ring_a_pcm

from lab.capicola_layout import STATE_BASE, address
from lab.capicola_memory import RESERVED_BASE
from lab.dsp import Dsp
from lab.dsp_build import build_blob
from lab.formats import read_frames
from lab.replay_io import load_pcm
from lab.sharc_tools import header

POOL = 0x8422B9C8
HANDOFF, CACHE, LANES = [address(x) for x in (0x200E4000, 0x200E7000, 0x200E8000)]
variants = ("reference", "trace-off", "cached", "cached-trace-off")


class Engine(Dsp):
    def call(self, pc, limit):
        return super().call(
            pc, 8_000_000 if pc == self.profile.block_handler else limit
        )


def read(engine, start, size):
    return bytes(engine.core.peek(start + i, 1) for i in range(size))


def sample_slot(engine, slot, offset, data):
    engine.core.poke(POOL + offset, struct.pack(f"<{len(data)}h", *data), 1)
    engine.core.poke(
        0x257810 + slot * 20,
        struct.pack("<5I", offset, offset, len(data) * 2, 48000, 0),
        1,
    )


def patch_word(wire, offset, value):
    wire[offset : offset + 2] = value.to_bytes(2, "big")


def musical_state(engine):
    left, right = read_master_mix_pcm(engine.core.peek)
    require(
        all(math.isfinite(x) for x in left + right), "Nonfinite modeled master output"
    )
    ring = read_ring_a_pcm(engine.core.peek, engine.core.peek(0x25F780))
    return (
        read(engine, CACHE, 1436),
        read(engine, LANES, 32 * 276),
        read(engine, HANDOFF, 36),
        struct.pack(f"<{len(left + right)}f", *(left + right)),
        tuple(ring.interleaved_q31()),
    )


report = dict(
    status="running",
    hardware_timing=None,
    boundary="whole DSP block handler; callbacks excluded",
    variants={},
    cases={},
    inputs={},
    source_hashes=provenance["source_hashes"],
)
try:
    capture = ROOT / "out/runs/capicola-panel-08/capicola.dtfr"
    load = ROOT / "out/runs/capicola-panel-05/flexbus.raw"
    expected = {
        capture: "3e6a3f0f319ca2c27087a77fb09d73f0b88922c2eabec0bb42651de8a1596290",
        load: "85f122f352abf80e5ae7fd11e9d5f05e5cc8b3e0526cd694d4fe420b6707e844",
    }
    for path, digest in expected.items():
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == digest, "Fixture drift"
        )
        report["inputs"][path.name] = digest
    template = next(
        w
        for w in read_frames(capture)
        if int.from_bytes(w[0x94:0x96], "big") == 8
        and int.from_bytes(w[0x22:0x24], "big") & 1
    )
    wire = bytearray(template)
    samples = [
        [int(12000 * math.sin(i * (track + 1) * 0.08)) for i in range(512)]
        for track in range(16)
    ]
    for track in range(16):
        patch_word(wire, 0x94 + track * 2, 2)
        patch_word(wire, 2 + track * 2, 60 * 256)
        patch_word(wire, 0x34 + track * 2, 100 * 256)
        block = 0xDA + track * 0x60
        wire[block : block + 0x60] = template[0xDA:0x13A]
        for offset, value in (
            (0, 16384),
            (2, 256),
            (4, 0),
            (6, 1000 + track),
            (12, 0),
            (14, 30720),
            (16, 256),
            (18, 25600),
        ):
            patch_word(wire, block + offset, value)
    engines = {}
    for variant in variants:
        blob = build_blob(
            True,
            family="capicola-stretch-live",
            layout="reserved-state",
            runtime_variant=variant,
            output=out / variant,
        )
        split = sharcldr.parse_blocks(blob)[-1]["offset"]
        extra = header(POOL - 1024, 4 * 1024 * 1024) + bytes(4 * 1024 * 1024)
        extra += header(RESERVED_BASE, STATE_BASE - RESERVED_BASE) + bytes(
            STATE_BASE - RESERVED_BASE
        )
        engine = Engine(blob[:split] + extra + blob[split:])
        load_pcm(engine, load.read_bytes())
        engines[variant] = engine
        report["variants"][variant] = dict(blob_sha256=hashlib.sha256(blob).hexdigest())

    def frame(case, trigger=0):
        patch_word(wire, 0x22, trigger)
        expected_state = None
        counters = report["cases"].setdefault(case, {name: [] for name in variants})
        for name, engine in engines.items():
            engine.frame(bytes(wire))
            state = musical_state(engine)
            if expected_state is None:
                expected_state = state
            else:
                require(
                    state == expected_state,
                    f"Musical state/master/ring mismatch: {name}/{case}",
                )
            counters[name].append(engine.block_instructions[-1])

    frame("startup")
    for engine in engines.values():
        for track, data in enumerate(samples):
            sample_slot(engine, 1000 + track, 0x20000 + track * 2048, data)
    frame("unready", 65535)
    frame("unready")
    for _preparation_index in range(1500):
        frame("preparation")
        if engines["reference"].core.peek(HANDOFF + 8) == 16:
            break
    require(
        all(e.core.peek(HANDOFF + 8) == 16 for e in engines.values()),
        "Banks did not prepare",
    )
    print(
        "Paired bank preparation and unready fallback exact",
        _preparation_index + 1,
        flush=True,
    )
    frame("steady", 65535)
    for _ in range(24):
        frame("steady")
    require(
        all(e.core.peek(LANES + 264) == 1 for e in engines.values()),
        "Custom backend inactive",
    )
    for index in range(20):
        for track in range(16):
            block = 0xDA + track * 0x60
            patch_word(wire, block + 2, (0, 256, 512, 768)[(index + track) % 4])
            patch_word(wire, block + 12, (index % 3) * 1024)
            patch_word(wire, block + 14, 24576 + (index % 2) * 4096)
        frame("live-edits")
    for _ in range(6):
        frame("settled")
    for track in range(16):
        patch_word(wire, 0x94 + track * 2, 0)
    for _ in range(3):
        frame("switch-away")
    require(
        all(
            e.core.peek(LANES + i * 276 + 264) == 0
            for e in engines.values()
            for i in range(32)
        ),
        "Custom lane survived switch-away",
    )
    require(
        source_hashes() == provenance["source_hashes"], "Source drift during paired run"
    )
    for case, measurements in report["cases"].items():
        report["cases"][case] = {
            name: dict(
                blocks=len(values),
                total=sum(values),
                maximum=max(values),
                mean=sum(values) / len(values),
            )
            for name, values in measurements.items()
        }
    report.update(
        status="passed",
        state_and_master_ring_exact=True,
        fresh_16_banks=True,
        source_stable=True,
        variant_order=list(variants),
    )
    print(json.dumps(report["cases"], indent=2), flush=True)
except BaseException as error:
    report.update(status="failed", error=f"{type(error).__name__}: {error}")
    raise
finally:
    write_json(out / "runtime-comparison.json", report)
