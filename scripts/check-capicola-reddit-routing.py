#!/usr/bin/env python3
"""Full native frame routing, stock/Plaits parity, stereo LP0, final-ring causal mute."""

# ruff: noqa: E402, I001
import argparse
import hashlib
import json
import math
import os
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
p.add_argument("--package", type=Path)
p.add_argument("--probe", type=Path)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab import runtime
import plusdrive as pd
import sharc_lp0 as lp0
import sharcldr
from sharc_dac import float_to_q31, read_master_mix_pcm, read_ring_a_pcm

from lab.capicola_reddit import VOICE_BASE
from lab.dsp import Dsp, header
from lab.formats import read_frames
from lab.replay_io import load_pcm
from lab.sharc_tools import assemble

frozen = source_hashes()
if a.package:
    manifest = json.loads((a.package / "manifest.json").read_text())
    require(
        manifest.get("capicola_reddit") and manifest["source_hashes"] == frozen,
        "Wrong/stale package",
    )
    firmware = a.package / "firmware"
else:
    require(a.probe, "Package/probe required")
    firmware = a.probe
blob = (firmware / "PLAITS_BLOB.bin").read_bytes()
meta = json.loads((firmware / "build.json").read_text())
POOL = 0x8422B9C8
report = dict(
    status="running",
    source_hashes=frozen,
    dsp_sha256=hashlib.sha256(blob).hexdigest(),
    hardware_verified=False,
)


def put(w, at, v):
    w[at : at + 2] = v.to_bytes(2, "big")


def raw(e, at, n):
    return bytes(e.core.peek(at + i, 1) for i in range(n))


def extend(image, at, data):
    split = sharcldr.parse_blocks(image)[-1]["offset"]
    return image[:split] + header(at, len(data)) + data + image[split:]


def engine(image):
    e = Dsp(extend(image, POOL - 1024, bytes(4 * 1024 * 1024)))
    load_pcm(e, (ROOT / "out/runs/capicola-panel-05/flexbus.raw").read_bytes())
    return e


def frame(e, w, trig=0):
    put(w, 0x22, trig)
    e.frame(bytes(w), instruction_limit=16_000_000)


def destination(e, lane):
    ptr = e.core.peek(0x24EF2C + lane * 4)
    require(0x80000000 <= ptr < 0xA0000000, "Destination bounds")
    return raw(e, ptr, 128)


def ring(e):
    left, right = read_master_mix_pcm(e.core.peek)
    r = read_ring_a_pcm(e.core.peek, e.core.peek(0x25F780))
    converted = [
        float_to_q31(v) for pair in zip(left, right, strict=True) for v in pair
    ]
    want = [(-v + 2**31) % 2**32 - 2**31 for v in converted]
    require(
        max(abs(x - y) for x, y in zip(r.interleaved_q31(), want, strict=True)) <= 1,
        "Final ring conversion",
    )
    return r.interleaved_q31()


def transfers_raw(transfers):
    data = bytearray()
    for tag, block, swap in transfers:
        data.extend(struct.pack("<I", tag))
        width = 2 if swap else 4
        data.extend(
            b"".join(block[i : i + width][::-1] for i in range(0, len(block), width))
        )
    return bytes(data)


try:
    capture = ROOT / "out/runs/capicola-panel-08/capicola.dtfr"
    require(
        sha256(capture)
        == "3e6a3f0f319ca2c27087a77fb09d73f0b88922c2eabec0bb42651de8a1596290",
        "Capture drift",
    )
    template = next(
        w
        for w in read_frames(capture)
        if int.from_bytes(w[0x94:0x96], "big") == 8
        and int.from_bytes(w[0x22:0x24], "big") & 1
    )
    e = engine(blob)
    stock = engine(runtime.STOCK_BLOB.read_bytes())
    w = bytearray(template)
    for t in range(16):
        put(w, 0x94 + t * 2, 2)
        put(w, 2 + t * 2, 60 * 256)
        put(w, 0x34 + t * 2, 100 * 256)
        base = 0xDA + t * 0x60
        w[base : base + 0x60] = template[0xDA:0x13A]
        for off, v in [
            (0, 16384),
            (2, (t % 4) * 256),
            (4, 0),
            (6, 1000 + t),
            (12, 0),
            (14, 30720),
            (16, 0),
            (18, 25600),
        ]:
            put(w, base + off, v)
    for x in [e, stock]:
        frame(x, w)
    sources = []
    for t in range(16):
        left = [int(10000 * math.sin(i * (t + 1) * 0.043)) for i in range(4096)]
        right = [
            int(9000 * math.sin(i * (t + 2) * 0.071) + 1500 * math.cos(i * 0.17))
            for i in range(4096)
        ]
        pcm = struct.pack(
            ">" + str(len(left) * 2) + "h",
            *[v for pair in zip(left, right, strict=True) for v in pair],
        )
        native = pd.build_native_sample(pcm, True)
        transfer = transfers_raw(
            lp0.native_sample_transfers(
                native, 1000 + t, lp0.COLDFIRE_BLOCK_BASE + 0x20000 + t * 0x4000
            )
        )
        sources.append(transfer)
        for x in [e, stock]:
            load_pcm(x, transfer)
    for i in range(8):
        frame(e, w, 65535 if i == 0 else 0)
        frame(stock, w, 65535 if i == 0 else 0)
        require(
            all(destination(e, lane) == destination(stock, lane) for lane in range(32)),
            "OFF voice parity",
        )
        require(ring(e) == ring(stock), "OFF final parity")
    report["stock_off_exact"] = dict(tracks=16, channels=32, blocks=8, final_ring=True)
    for t in range(16):
        put(w, 0xDE + t * 0x60, 256)
    different = 0
    statuses = []
    for i in range(40):
        frame(e, w, 65535 if i in [0, 20] else 0)
        frame(stock, w, 65535 if i in [0, 20] else 0)
        different += sum(
            destination(e, lane) != destination(stock, lane) for lane in range(32)
        )
        ring(e)
        page = e.core.peek(0x261CA4) & 1
        word = e.core.peek(0x26623A + (page << 12), 2)
        require(word & 0xF000 == 0xD000, "Status tag")
        statuses.append(word)
    require(different > 0, "Vacuous ON routing")
    require(
        all(e.core.peek(VOICE_BASE + lane * 0x400) != 0 for lane in range(32)),
        "Missing author voice states",
    )
    report["native_stereo"] = dict(
        tracks=16,
        channels=32,
        blocks=40,
        changed_lane_blocks=different,
        retrigger=True,
        lp0_loader=True,
        statuses=statuses,
    )
    print("Native stereo/stock routing passed", flush=True)
    # Other machines and all six Plaits models must remain sample exact.
    baseline = ROOT / "out/runs/combined-package-03/firmware/PLAITS_BLOB.bin"
    require(
        sha256(baseline)
        == "0cfb6c8315bd2db0e7346527c2834907fa7d131b0b55faf04f047d2ebb801faf",
        "R3 baseline drift",
    )
    parity = []
    for machine in [0, 1, 3, 4, 5, 6, 7, 8]:
        for model in range(6) if machine == 7 else [0]:
            r3 = engine(baseline.read_bytes())
            candidate = engine(blob)
            z = bytearray(template)
            for t in range(16):
                put(z, 0x94 + t * 2, 0)
            put(z, 0x94, machine)
            if machine == 7:
                put(z, 0xDE, model * 256)
            peak = 0
            for b in range(8):
                for x in [r3, candidate]:
                    frame(x, z, 1 if b == 3 else 0)
                require(
                    candidate.source == r3.source,
                    f"Machine/model parity {machine}/{model}",
                )
                peak = max(peak, max(map(abs, candidate.source)))
            if machine == 7:
                require(peak > 1e-7, "Vacuous Plaits parity")
            parity.append(dict(machine=machine, model=model, exact=True, peak=peak))
            del r3, candidate
    report["preserved_machine_parity"] = parity
    # Causal mute replaces only ON entry in a separate emulated image.
    mute = assemble(
        ".SECTION/PM seg_pmco;\n"
        "R0=0x2559ba; I4=R0; R0=DM(0,I4); R1=65535; R0=R0 AND R1;\n"
        "R1=128; COMP(R0,R1); IF LT JUMP 0x1c5576;\n"
        "R1=256; COMP(R0,R1); IF GT JUMP 0x1c5576;\n"
        "I4=R8; R0=0;\n"
        + "DM(0,I4)=R0; I4=MODIFY(I4,1)(NW);\n" * 32
        + "I12=DM(M7,I6); NOP; JUMP(M14,I12)(DB); NOP; RFRAME;\n"
    ).boot_bytes
    negative = bytearray(blob)
    blocks = sharcldr.parse_blocks(negative)
    off = sharcldr.offset_for_address(blocks, 0x1C6AF1)
    negative[off : off + 6] = assemble(
        ".SECTION/PM seg_pmco;\nCJUMP 0xbf8000 (DB);\n"
    ).boot_bytes
    negative = extend(bytes(negative), 0x200F0000, mute + bytes(-len(mute) % 4))
    engines = {"on": engine(blob), "off": engine(blob), "muted": engine(negative)}
    outputs = {k: [] for k in engines}
    z = bytearray(w)
    for t in range(16):
        put(z, 0x94 + t * 2, 0)
    put(z, 0x94, 2)
    for x in engines.values():
        frame(x, z)
        load_pcm(x, sources[0])
    for b in range(300):
        for name, x in engines.items():
            q = bytearray(z)
            put(q, 0xDE, 0 if name == "off" else 256)
            frame(x, q, 1 if b in [0, 150] else 0)
            outputs[name].extend(ring(x))
    levels = {
        k: math.sqrt(sum((v / 2**31) ** 2 for v in values) / len(values))
        for k, values in outputs.items()
    }
    require(
        levels["on"] > 1e-7
        and levels["off"] > 1e-7
        and levels["muted"] < levels["on"] * 0.01,
        "Final-ring causal mute",
    )
    require(outputs["on"] != outputs["off"], "Final-ring ON/OFF identical")
    for name, values in outputs.items():
        with wave.open(str(out / (name + ".wav")), "wb") as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(48000)
            f.writeframes(
                struct.pack(
                    "<" + str(len(values)) + "h",
                    *[max(-32768, min(32767, v >> 16)) for v in values],
                )
            )
    report["final_ring"] = dict(
        blocks=300, frames=9600, rms=levels, causal_mute=True, pcm_unchanged=True
    )
    require(source_hashes() == frozen, "Source drift")
    report["status"] = "passed"
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
