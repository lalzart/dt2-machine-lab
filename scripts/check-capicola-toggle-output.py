#!/usr/bin/env python3
"""Check OS1.16 CAPI OFF/ON at the final mix and DAC-facing ring.

The causal negative control changes only prepared bank amplitudes in a separate
emulator instance. It leaves original PCM, bank timing and compiled code intact.
This establishes modeled routing and signal differences, not listening quality.
"""

# ruff: noqa: E402, I001
import argparse
import ctypes
import hashlib
import json
import math
import os
import random
import struct
import sys
import wave
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
p.add_argument(
    "--checkpoint",
    type=Path,
    help="Optional prepared state from this check or capi-listening-audit-02; source identity is checked",
)
p.add_argument("--blocks", type=int, default=1500)
p.add_argument(
    "--sample-frames",
    type=int,
    default=48000,
    help="Bounded mono routing fixture length; default preserves the one-second audit",
)
a = p.parse_args()
require(512 <= a.sample_frames <= 48000, "Use 512..48000 source frames")
require(2 <= a.blocks <= 6000, "Use 2..6000 blocks")
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
from sharc_transpile_run import OPT_EXPORT_RANGES
from sharc_dac import read_master_mix_pcm, read_ring_a_pcm

POOL = 0x8422B9C8
STRIDE, BACKEND, LAST_DEST = 276, 264, 272
AUTO, HANDOFF, CACHE, LANES = [
    address(x) for x in (0x200E4500, 0x200E4000, 0x200E7000, 0x200E8000)
]
# Reuse the validated fixture helpers without executing that script's suite.
helper_path = ROOT / "scripts/check-capicola-toggle-native.py"


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
    from sharc_dac import float_to_q31

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


def backends(engine):
    return [engine.core.peek(LANES + i * STRIDE + BACKEND) for i in range(32)]


package = a.package.resolve()
manifest = json.loads((package / "manifest.json").read_text())
blob_path = package / manifest["dsp"]["path"]
require(manifest.get("capi_toggle") is True, "Package lacks CAPI toggle")
require(sha256(blob_path) == manifest["dsp"]["sha256"], "DSP drift")
capture = ROOT / "out/runs/capicola-panel-08/capicola.dtfr"
load = ROOT / "out/runs/capicola-panel-05/flexbus.raw"
require(
    sha256(capture)
    == "3e6a3f0f319ca2c27087a77fb09d73f0b88922c2eabec0bb42651de8a1596290",
    "Capture drift",
)
require(
    sha256(load) == "85f122f352abf80e5ae7fd11e9d5f05e5cc8b3e0526cd694d4fe420b6707e844",
    "PCM fixture drift",
)
sources = source_hashes()
write_json(
    out / "inputs.json",
    dict(
        dsp_sha256=sha256(blob_path),
        capture_sha256=sha256(capture),
        load_sha256=sha256(load),
        helper_sha256=sha256(helper_path),
        sources=sources,
    ),
)
blob = blob_path.read_bytes()
# Exact stock decode of the hook and resume instructions.
from sharc_disasm import decode_confident_loaded

memory = sharcldr.LoadedMemory.from_stream(STOCK_BLOB.read_bytes())
pc = 0x1C6AEB
decoded = []
while pc < 0x1C6B20:
    ins = decode_confident_loaded(memory, pc)
    decoded.append(
        dict(pc=hex(pc), form=ins.type_name, fields=ins.fields, bytes=ins.length_bytes)
    )
    if not ins.length_bytes:
        break
    pc += ins.length_bytes // 2
write_json(out / "stock-resume-decode.json", decoded)
engines = {
    name: Dsp(arena(blob, 4 * 1024 * 1024, bank=True))
    for name in ("off", "on", "muted")
}
template = next(
    w
    for w in read_frames(capture)
    if int.from_bytes(w[0x94:0x96], "big") == 8
    and int.from_bytes(w[0x22:0x24], "big") & 1
)
wires = {name: bytearray(template) for name in engines}
rng = random.Random(19)
pcm = []
for i in range(a.sample_frames):
    p = i % 12000
    kick = (
        0.43
        * math.exp(-p / 1300)
        * math.sin(
            2 * math.pi * (47 * p / 48000 + 0.008 * 1100 * (1 - math.exp(-p / 1100)))
        )
    )
    snare = 0.2 * math.exp(-p / 1100) * rng.uniform(-1, 1) if (i // 12000) % 2 else 0
    hat = 0.16 * math.exp(-(i % 3000) / 180) * rng.uniform(-1, 1)
    tone = (
        0.1
        * math.sin(2 * math.pi * 220 * i / 48000)
        * (0.5 + 0.5 * math.sin(2 * math.pi * i / 48000))
    )
    pcm.append(round(30000 * (kick + snare + hat + tone)))
expected_pcm = struct.pack("<" + str(len(pcm)) + "h", *pcm)


def export_checkpoint(e):
    e.core.set_option(OPT_EXPORT_RANGES, 1)
    capacity = 1 << 20
    while True:
        buffer = ctypes.create_string_buffer(capacity)
        length = e.core._lib.sharc_native_export_state(e.core._handle, buffer, capacity)
        if length >= 0:
            break
        capacity = -length
    e.core.set_option(OPT_EXPORT_RANGES, 0)
    return buffer.raw[:length]


if a.checkpoint:
    checkpoint_path = a.checkpoint.resolve()
    origin = json.loads((checkpoint_path.parent / "inputs.json").read_text())
    for key, path in (
        ("dsp_sha256", blob_path),
        ("capture_sha256", capture),
        ("load_sha256", load),
        ("helper_sha256", helper_path),
    ):
        require(origin[key] == sha256(path), "Checkpoint input drift: " + key)
    checkpoint = checkpoint_path.read_bytes()
    prepared_blocks = None
else:
    e = engines["on"]
    w = bytearray(template)
    load_pcm(e, load.read_bytes())
    for t in range(16):
        put(w, 0x94 + t * 2, 0)
    put(w, 0x94, 2)
    put(w, 2, 60 * 256)
    for off, val in (
        (0, 16384),
        (2, 256),
        (4, 256),
        (6, 1000),
        (12, 0),
        (14, 30720),
        (16, 0),
        (18, 25600),
    ):
        put(w, 0xDA + off, val)
    frame(e, w)
    sample_slot(e, 1000, 0x20000, pcm)
    for b in range(4000):
        frame(e, w)
        if b % 1000 == 0:
            print("Preparing", b, flush=True)
        if e.core.peek(HANDOFF + 8) == 1:
            break
    else:
        raise RuntimeError("Bank not ready")
    prepared_blocks = b + 1
    checkpoint = export_checkpoint(e)
    checkpoint_path = out / "prepared-checkpoint.pack"
    checkpoint_path.write_bytes(checkpoint)
write_json(
    out / "checkpoint-input.json",
    dict(
        path=str(checkpoint_path),
        sha256=hashlib.sha256(checkpoint).hexdigest(),
        prepared_blocks=prepared_blocks,
        pcm_sha256=hashlib.sha256(expected_pcm).hexdigest(),
    ),
)


def reset_prepared(e):
    require(
        e.core._lib.sharc_native_import_state(
            e.core._handle, checkpoint, len(checkpoint)
        )
        == 0,
        "Checkpoint import",
    )
    require(e.core.peek(HANDOFF + 8) == 1, "Checkpoint bank missing")
    require(
        read(e, POOL + 0x20000, len(expected_pcm)) == expected_pcm,
        "Checkpoint PCM changed",
    )


for name, w in wires.items():
    for t in range(16):
        put(w, 0x94 + t * 2, 0)
    put(w, 0x94, 2)
    put(w, 2, 60 * 256)
    put(w, 0x34, 100 * 256)
    for off, val in (
        (0, 16384),
        (2, 256),
        (4, 0 if name == "off" else 256),
        (6, 1000),
        (12, 0),
        (14, 30720),
        (16, 0),
        (18, 25600),
    ):
        put(w, 0xDA + off, val)


def mute_bank(e):
    entries = CACHE + 28
    found = []
    for i in range(16):
        bank = entries + i * 88
        if e.core.peek(bank + 36) == POOL + 0x20000 and e.core.peek(bank + 20) == len(
            pcm
        ):
            pointer = e.core.peek(bank)
            count = e.core.peek(bank + 16)
            require(
                2 <= count <= len(pcm) + 4 and RESERVED_BASE <= pointer < STATE_BASE,
                "Bank bounds",
            )
            e.core.poke(pointer, bytes(count * 4), 1)
            found.append(dict(entry=i, pointer=hex(pointer), count=count))
    require(len(found) == 1, "No unique ready bank")
    return found[0]


def metrics(a, b):
    ra = math.sqrt(sum(x * x for x in a) / len(a))
    rb = math.sqrt(sum(x * x for x in b) / len(b))
    delta = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)) / len(a))
    return dict(
        rms_a=ra,
        rms_b=rb,
        difference_rms=delta,
        difference_db_relative_to_a=20 * math.log10(delta / ra)
        if ra and delta
        else None,
        maximum_difference=max(abs(x - y) for x, y in zip(a, b, strict=True)),
        equal_samples=sum(x == y for x, y in zip(a, b, strict=True)),
        samples=len(a),
    )


def wav(path, values):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(48000)
        f.writeframes(
            struct.pack(
                "<" + str(len(values)) + "h",
                *[max(-32768, min(32767, round(x * 32768))) for x in values],
            )
        )


report = dict(
    status="running",
    hardware_verified=False,
    scope=f"Native final mix and DAC-facing ring; synthetic {len(pcm)}-frame mono source, captured control/LP0 fixtures, identical prepared checkpoint. Causal intervention zeroes custom-bank values only; original PCM and algorithm code remain intact.",
    dsp_sha256=sha256(blob_path),
    prepared_blocks=prepared_blocks,
    source_frames=len(pcm),
    cases=[],
)
try:
    for semitone, bars in ((0, 0), (12, 0), (-12, 0), (12, 768)):
        name = f"tune{semitone}_bars{bars}"
        for e in engines.values():
            reset_prepared(e)
        muted_bank = mute_bank(engines["muted"])
        print("Rendering", name, flush=True)
        recordings = {k: [] for k in engines}
        rings = {k: [] for k in engines}
        conversion_max = 0
        for w in wires.values():
            put(w, 0xDA, 16384 + semitone * 256)
            put(w, 0xEA, bars)
        for block in range(a.blocks):
            for key, e in engines.items():
                frame(e, wires[key], 1 if block == 0 else 0)
                tap = downstream(e)
                recordings[key].extend(
                    x
                    for pair in zip(
                        tap["master_left"], tap["master_right"], strict=True
                    )
                    for x in pair
                )
                rings[key].extend(
                    x
                    for pair in zip(tap["ring_left"], tap["ring_right"], strict=True)
                    for x in pair
                )
                conversion_max = max(conversion_max, tap["conversion_maximum_lsb"])
            if block == 1:
                flags = {k: backends(e)[:2] for k, e in engines.items()}
                require(
                    flags["off"] == [0, 0] and flags["on"] == flags["muted"] == [1, 1],
                    "Backend flags " + str(flags),
                )
                controls = {
                    k: dict(
                        pitch=floats(e, 0x2412CC + 0x1CC, 1)[0],
                        advance=floats(e, 0x2412CC + 0x1C8, 1)[0],
                    )
                    for k, e in engines.items()
                }
            if block in (250, 500, 1000):
                print(name, block, flush=True)
        # Listening exports use the modeled DAC-facing ring, with native gain.
        for key, values in rings.items():
            wav(out / (name + "-" + key + ".wav"), values)
        row = dict(
            case=name,
            controls=controls,
            backends=flags,
            master_off_vs_on=metrics(recordings["off"], recordings["on"]),
            master_on_vs_muted=metrics(recordings["on"], recordings["muted"]),
            ring_off_vs_on=metrics(rings["off"], rings["on"]),
            ring_on_vs_muted=metrics(rings["on"], rings["muted"]),
            conversion_maximum_lsb=conversion_max,
            blocks=a.blocks,
            muted_bank=muted_bank,
        )
        require(row["ring_off_vs_on"]["rms_b"] > 1e-5, "Silent ON oracle")
        require(row["ring_off_vs_on"]["difference_rms"] > 1e-8, "No OFF/ON difference")
        require(
            row["ring_on_vs_muted"]["rms_b"] == 0,
            "Custom-bank mute did not silence output",
        )
        require(
            controls["off"] == controls["on"] == controls["muted"],
            "Native rates differ",
        )
        report["cases"].append(row)
        write_json(out / "report.json", report)
        print(json.dumps(row), flush=True)
    require(sources == source_hashes(), "Source drift during audit")
    report["status"] = "passed"
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
