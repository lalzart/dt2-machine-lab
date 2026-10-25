#!/usr/bin/env python3
"""Native LP0 stereo loading,32-bank admission and actual channel voice PCM."""

# ruff: noqa: E402,I001
import argparse
import ctypes as ct
import importlib.util
import json
import math
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from lab.project import require, settings, source_hashes, sha256, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--package", type=Path, required=True)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab import runtime  # noqa: F401 - initialize pinned imports
import plusdrive as pd
import sharc_lp0 as lp0
import sharcldr
from lab.dsp import Dsp, header
from lab.capicola_layout import address, STATE_BASE
from lab.capicola_memory import RESERVED_BASE
from lab.replay_io import load_pcm
from lab.formats import read_frames

spec = importlib.util.spec_from_file_location(
    "source_host", ROOT / "scripts/check-capicola-source.py"
)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
manifest = json.loads((a.package / "manifest.json").read_text())
require(manifest.get("capicola_source"), "Source package required")
blob = (a.package / manifest["dsp"]["path"]).read_bytes()
require(
    sha256(a.package / manifest["dsp"]["path"]) == manifest["dsp"]["sha256"],
    "DSP drift",
)
frozen = source_hashes()
q, h, lib, old, ref = host.build(out)
POOL = 0x8422B9C8
LANES = address(0x200E8000)
HANDOFF = address(0x200E4000)
STRIDE = 276
split = sharcldr.parse_blocks(blob)[-1]["offset"]
extra = (
    header(POOL - 1024, 4 * 1024 * 1024)
    + bytes(4 * 1024 * 1024)
    + header(RESERVED_BASE, STATE_BASE - RESERVED_BASE)
    + bytes(STATE_BASE - RESERVED_BASE)
)
e = Dsp(blob[:split] + extra + blob[split:])


def put(w, off, v):
    w[off : off + 2] = v.to_bytes(2, "big")


def read(at, n):
    return bytes(e.core.peek(at + i, 1) for i in range(n))


def frame(trigger=0):
    put(wire, 0x22, trigger)
    e.frame(bytes(wire), instruction_limit=64_000_000)


def transfer_raw(transfers):
    data = bytearray()
    for tag, block, swap in transfers:
        data.extend(struct.pack("<I", tag))
        width = 2 if swap else 4
        data.extend(
            b"".join(block[i : i + width][::-1] for i in range(0, len(block), width))
        )
    return bytes(data)


def integer(voice, offset):
    q31 = e.core.peek(voice + offset) | (e.core.peek(voice + offset + 4) << 32)
    require(q31 % (1 << 31) == 0, "Fractional native bound")
    return q31 >> 31


load_pcm(e, (ROOT / "out/runs/capicola-panel-05/flexbus.raw").read_bytes())
template = next(
    w
    for w in read_frames(ROOT / "out/runs/capicola-panel-08/capicola.dtfr")
    if int.from_bytes(w[0x94:0x96], "big") == 8
    and int.from_bytes(w[0x22:0x24], "big") & 1
)
wire = bytearray(template)
for track in range(16):
    put(wire, 0x94 + track * 2, 2)
    put(wire, 2 + track * 2, 60 * 256)
    put(wire, 0x34 + track * 2, 100 * 256)
    base = 0xDA + track * 0x60
    wire[base : base + 0x60] = template[0xDA:0x13A]
    for off, v in [
        (0, 16384),
        (2, 256),
        (4, 256),
        (6, 1000 + track),
        (12, 0),
        (14, 30720),
        (16, 0),
        (18, 25600),
    ]:
        put(wire, base + off, v)
frame()
sources = []
transfers = []
for track in range(16):
    left = [int(11000 * math.sin(i * (track + 1) * 0.043)) for i in range(512)]
    right = [
        int(9000 * math.sin(i * (track + 2) * 0.071) + 1500 * math.cos(i * 0.17))
        for i in range(512)
    ]
    pcm = struct.pack(
        ">" + "h" * 1024, *[v for pair in zip(left, right, strict=True) for v in pair]
    )
    native = pd.build_native_sample(pcm, True)
    parts = lp0.native_sample_transfers(
        native, 1000 + track, lp0.COLDFIRE_BLOCK_BASE + 0x20000 + track * 0x4000
    )
    raw = transfer_raw(parts)
    load_pcm(e, raw)
    transfers.extend(parts)
    meta = struct.unpack("<5I", read(0x257810 + (1000 + track) * 20, 20))
    require(meta[2:] == (1024, 48000, 1), "Native per-channel stereo header")
    for offset, channel in zip(meta[:2], [left, right], strict=True):
        require(
            read(POOL + offset, 1024) == struct.pack("<512h", *channel),
            "Native planar channel bytes",
        )
    sources.append(dict(left=left, right=right, metadata=meta))
(out / "stereo-native-transfers.raw").write_bytes(transfer_raw(transfers))
report = dict(
    status="running",
    scope=__doc__,
    source_hashes=frozen,
    dsp_sha256=manifest["dsp"]["sha256"],
    channels=[],
)
try:
    blocks = 0
    while e.core.peek(HANDOFF + 8) < 1 and blocks < 100:
        frame()
        blocks += 1
    require(e.core.peek(HANDOFF + 8) == 1, "First channel preparation observation")
    frame(1)
    frame()
    require(
        [e.core.peek(LANES + lane * STRIDE + 264) for lane in [0, 1]] == [0, 0],
        "Partial stereo admission selected CAPI",
    )
    report["partial_stereo_uses_stock"] = True
    while e.core.peek(HANDOFF + 8) < 32 and blocks < 3000:
        frame()
        blocks += 1
    require(e.core.peek(HANDOFF + 8) == 32, "Thirty-two native channel banks not ready")
    report["prepared_blocks"] = blocks
    seen = set()
    for step in range(3):
        frame(65535 if step == 0 else 0)
        for lane in range(32):
            at = LANES + lane * STRIDE
            renders = e.core.peek(at + 268)
            if lane in seen or renders != 1:
                continue
            require(e.core.peek(at + 264) == 1, "Stereo lane fallback")
            track = lane // 2
            channel = lane & 1
            voice = 0x2412CC + lane * 0x1D8
            meta = sources[track]["metadata"]
            require(
                e.core.peek(voice) == POOL + meta[channel], "Native L/R voice mapping"
            )
            data = (ct.c_float * 512)(
                *[v / 32768 for v in sources[track]["right" if channel else "left"]]
            )
            bank, arrays = q.sample(h, lib, data)
            state = h.Live()
            pitch = struct.unpack("<f", read(voice + 0x1CC, 4))[0]
            advance = struct.unpack("<f", read(voice + 0x1C8, 4))[0]
            start, end = integer(voice, 0x198), integer(voice, 0x1A0)
            reverse = e.core.peek(voice + 0x1BB, 1)
            loop = e.core.peek(voice + 0x1BC, 1)
            require(
                lib.cap_live_start(
                    ct.byref(state),
                    ct.byref(bank),
                    start,
                    end,
                    reverse,
                    loop,
                    pitch,
                    advance,
                    128,
                )
                == 0,
                "Host native-controls start",
            )
            expected = (ct.c_float * 32)()
            lib.cap_live_process(ct.byref(state), expected, 32)
            actual = struct.unpack("<32f", read(address(0x200EB000) + lane * 128, 128))
            maximum, rms = q.error(expected, actual)
            require(
                maximum <= 1e-4 and rms <= 1e-5,
                f"Stereo host mismatch:{lane, maximum, rms}",
            )
            report["channels"].append(
                dict(
                    lane=lane,
                    track=track,
                    channel=channel,
                    pitch=pitch,
                    advance=advance,
                    start=start,
                    end=end,
                    maximum_error=maximum,
                    rms_error=rms,
                )
            )
            seen.add(lane)
    require(len(seen) == 32, "Did not observe first render on every stereo lane")
    # Real LP0 reset invalidates this native stereo slot; no mid-note stock takeover.
    first = sources[0]
    pcm = struct.pack(
        ">" + "h" * 1024,
        *[v for pair in zip(first["left"], first["right"], strict=True) for v in pair],
    )
    native = pd.build_native_sample(pcm, True)
    reset = lp0.native_sample_transfers(
        native, 1000, lp0.COLDFIRE_BLOCK_BASE + 0x20000
    )[:1]
    load_pcm(e, transfer_raw(reset))
    frame()
    require(
        not any(struct.unpack("<64f", read(address(0x200EB000), 256))),
        "Invalidated stereo source still renders",
    )
    require(
        [e.core.peek(LANES + lane * STRIDE + 264) for lane in [0, 1]] == [1, 1],
        "Mid-note stock takeover after stereo invalidation",
    )
    report["stereo_invalidation_silences_both"] = True
    report["maximum_native_block_instructions"] = max(e.block_instructions)
    require(frozen == source_hashes(), "Source drift")
    report["status"] = "passed"
    print(
        "PASS32 native stereo channels, partial-ready fallback and invalidation",
        flush=True,
    )
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}:{exc}")
    raise
finally:
    write_json(out / "report.json", report)
