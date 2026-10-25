#!/usr/bin/env python3
"""Author golden replays, relocated SHARC entry PCM, and all-feature frame routing."""

# ruff: noqa: E402, I001
import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import require, settings, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--package", type=Path)
p.add_argument("--c-entry", action="store_true")
p.add_argument(
    "--probe", type=Path, help="Developer-only DSP build before final source freeze"
)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab import runtime
import sharc_trace as st
import sharcldr

from lab.capicola_layout import STATE_BASE
from lab.capicola_reddit import SOURCE, VOICE_BASE, validate_sources
from lab.dsp import Dsp, header

frozen = source_hashes()
if a.package:
    manifest = json.loads((a.package / "manifest.json").read_text())
    require(
        manifest.get("capicola_reddit") and manifest["source_hashes"] == frozen,
        "Wrong/stale author package",
    )
    firmware = a.package / "firmware"
else:
    require(a.probe, "Package or probe required")
    firmware = a.probe
blob = (firmware / "PLAITS_BLOB.bin").read_bytes()
metadata = json.loads((firmware / "build.json").read_text())
report = dict(
    status="running",
    source_hashes=frozen,
    dsp_sha256=hashlib.sha256(blob).hexdigest(),
    author_archive_sha256=validate_sources()["sha256"],
    target_cases=[],
    hardware_verified=False,
)


def raw(e, at, n):
    return bytes(e.core.peek(at + i, 1) for i in range(n))


def poke(e, at, data):
    require(e.core.poke(at, data, 1) == len(data), f"Fixture write {at:#x}")


def put(w, at, v):
    w[at : at + 2] = v.to_bytes(2, "big")


def extend(image, at, data):
    split = sharcldr.parse_blocks(image)[-1]["offset"]
    return image[:split] + header(at, len(data)) + data + image[split:]


def metric(got, expected):
    require(
        len(got) == len(expected) and all(math.isfinite(v) for v in got),
        "Nonfinite/short audio",
    )
    err = [abs(x - y) for x, y in zip(got, expected, strict=True)]
    return dict(maximum=max(err), rms=math.sqrt(sum(x * x for x in err) / len(err)))


def floats(e, at, n):
    return struct.unpack("<" + str(n) + "f", raw(e, at, n * 4))


def call(e, pc, voice, dest):
    for reg, val in dict(
        I7=STATE_BASE + 0x17EF8,
        I6=STATE_BASE + 0x17F00,
        M5=0,
        M6=1,
        M7=0xFFFFFFFF,
        M13=0,
        M14=1,
        M15=0xFFFFFFFF,
        R4=0x2412CC + voice * 0x1D8,
        R8=dest,
        R12=32,
    ).items():
        e.core.set_reg(st.UREG_CODES[reg], st.Const(val))
    before = e.core.stats()["instructions"]
    e.call(pc, 20_000_000)
    return e.core.stats()["instructions"] - before


try:
    # Execute the unchanged published tests in a retained copy, never in vendor.
    ref = out / "author-reference"
    shutil.copytree(SOURCE, ref)
    host = subprocess.run(
        [sys.executable, str(ref / "test/run_tests.py"), "host"],
        env=dict(os.environ, SELACHE=str(runtime.SELACHE), GEN_BUILD="0"),
        capture_output=True,
        text=True,
    )
    (out / "host-goldens.log").write_text(host.stdout + host.stderr)
    require(
        host.returncode == 0,
        "Author published host tests failed: " + host.stdout[-1000:],
    )
    report["host_goldens"] = dict(passed=14, log="host-goldens.log")
    spec = importlib.util.spec_from_file_location(
        "author_tests", ref / "test/run_tests.py"
    )
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    mono, stereo = tests.test_signal()
    binary = ref / "build/test/host/gen_host"
    cases = [
        (
            n,
            blocks,
            ref / "test/golden" / f"{n}.rec",
            stereo if "STEREO=1" in cfg else mono,
            cfg,
        )
        for n, (blocks, cfg) in tests.OURS.items()
        if n.startswith("stretch")
    ]
    cases += [
        (n, 600, ref / "test/rec_st.txt", ref / "test/tone.i16", "STEREO=1 " + cfg)
        for n, cfg in tests.TONE.items()
    ]
    for name, blocks, record, sample, cfg in cases:
        values = tests.run_host(binary, blocks, record, sample, cfg)
        expected = struct.unpack(
            "<" + str(len(values)) + "f",
            struct.pack("<" + str(len(values)) + "I", *values),
        )
        words = [int(x, 16) for x in record.read_text().split()]
        vr = [words[:118], words[173:291]]
        pr = [words[118:173], words[291:346]]
        opts = tests.env_of(cfg)
        channels = 2 if opts.get("STEREO") else 1
        for v in range(2):
            if "HTUNE" in opts:
                pr[v][0] = struct.unpack(
                    "<I", struct.pack("<f", (64 + float(opts["HTUNE"])) / 128)
                )[0]
            if "HEND" in opts:
                end = int(opts["HEND"])
                vr[v][0x68] = (end & 1) << 31
                vr[v][0x69] = end >> 1
            if "HPLAY" in opts:
                pm = int(opts["HPLAY"])
                rv = pm & 1
                lp = (pm >> 1) & 1
                vr[v][0x6E] = (vr[v][0x6E] & 0xFFFFFF) | (rv << 24)
                vr[v][0x6F] = (vr[v][0x6F] & ~255) | lp
                start = vr[v][0x67] * 2 + (vr[v][0x66] >> 31)
                end = vr[v][0x69] * 2 + (vr[v][0x68] >> 31)
                seed = end - 1 if rv else start
                vr[v][0x6C] = (seed & 1) << 31
                vr[v][0x6D] = seed >> 1
            if "HSTRETCH" in opts:
                vr[v][0x72] = struct.unpack(
                    "<I", struct.pack("<f", float(opts["HSTRETCH"]))
                )[0]
        image = extend(blob, 0x310000, sample.read_bytes() + bytes(4))
        e = Dsp(image)
        dest = STATE_BASE + 0x15000
        for v in range(channels):
            poke(e, 0x2412CC + v * 0x1D8, struct.pack("<118I", *vr[v]))
            poke(e, 0x2506EC + v * 0xDC, struct.pack("<55I", *pr[v]))
        poke(e, 0x2559BA, struct.pack("<H", 256))
        if len(words) >= 349:
            poke(e, 0x252D50, struct.pack("<I", words[346]))
            for page in [0, 1]:
                for offset, value in [(0xDC, words[347]), (0xE8, words[348])]:
                    poke(e, 0x264220 + page * 0x1000 + offset, struct.pack("<I", value))
        retrigs = {int(x) for x in opts.get("RETRIG", "").split(",") if x}
        got = []
        counts = []
        for b in range(blocks):
            if b in retrigs:
                for v in range(channels):
                    poke(
                        e,
                        0x2412CC + v * 0x1D8 + 0x1B0,
                        struct.pack("<2I", vr[v][0x66], vr[v][0x67]),
                    )
            for v in range(channels):
                poke(e, dest, b"OUT!" + bytes(128) + b"LAST")
                counts.append(
                    call(
                        e,
                        metadata["symbols"][
                            "cc_dt2_stretch." if a.c_entry else "cc_dt2_entry."
                        ],
                        v,
                        dest + 4,
                    )
                )
                require(
                    raw(e, dest, 4) == b"OUT!" and raw(e, dest + 132, 4) == b"LAST",
                    "Output canary",
                )
                got.extend(floats(e, dest + 4, 32))
        (out / (name + "-native.f32")).write_bytes(
            struct.pack("<" + str(len(got)) + "f", *got)
        )
        (out / (name + "-host.f32")).write_bytes(
            struct.pack("<" + str(len(expected)) + "f", *expected)
        )
        m = metric(got, expected)
        write_json(
            out / (name + "-debug.json"),
            dict(
                source=[hex(e.core.peek(0x310000 + i * 4)) for i in range(4)],
                voice=[hex(e.core.peek(0x2412CC + i * 4)) for i in range(118)],
                state=[hex(e.core.peek(VOICE_BASE + i * 4)) for i in range(32)],
                raw_switch=[hex(e.core.peek(0x2559B8)), hex(e.core.peek(0x2559BA))],
                calls=counts[:8],
            ),
        )
        row = dict(
            case=name,
            frames=blocks * 32,
            channels=channels,
            **m,
            max_call_instructions=max(counts),
        )
        report["target_cases"].append(row)
        write_json(out / "report.json", report)
        require(m["maximum"] <= 1e-4 and m["rms"] <= 1e-5, f"Native {name}: {m}")
        print("Native", name, m, flush=True)
        (out / (name + "-native.f32")).write_bytes(
            struct.pack("<" + str(len(got)) + "f", *got)
        )
        del e
    report["status"] = "native-oracle-passed"
    require(source_hashes() == frozen, "Source drift during native checks")
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
