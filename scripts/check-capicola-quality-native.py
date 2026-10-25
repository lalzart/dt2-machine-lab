#!/usr/bin/env python3
"""Execute the actual packaged SHARC reader against original Granule and host.

Bank preparation and initial seek are explicit fixtures. This is direct target
render execution, separate from native frame routing and cold-start checks.
"""

# ruff: noqa: E402, I001
import argparse
import ctypes as ct
import hashlib
import importlib.util
import itertools
import json
import math
import os
import re
import struct
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
p.add_argument("--package", type=Path, required=True)
p.add_argument(
    "--baseline-package",
    type=Path,
    help="Preserved capped DSP for a causal target negative and paired instruction counts",
)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab import runtime  # noqa: F401 - installs pinned DigiKit imports before native modules
import sharc_trace as st
import sharcldr

from lab.capicola_layout import STATE_BASE
from lab.capicola_memory import BANK_BASE
from lab.dsp import Dsp, header

spec = importlib.util.spec_from_file_location(
    "quality_host", ROOT / "scripts/check-capicola-quality.py"
)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
manifest = json.loads((a.package / "manifest.json").read_text())
require(
    manifest["capicola_quality"] and manifest["source_hashes"] == source_hashes(),
    "Wrong/stale quality package",
)
blob = (a.package / manifest["dsp"]["path"]).read_bytes()
require(hashlib.sha256(blob).hexdigest() == manifest["dsp"]["sha256"], "Changed DSP")
listing = (a.package / "firmware/listing.txt").read_text()
pc = int(re.search(r"(?m)^cap_stretch_process\.:\n\s+([0-9a-f]+)", listing)[1], 16)
# Fixture storage inside the already reserved bank arena; no new device ownership.
split = sharcldr.parse_blocks(blob)[-1]["offset"]
extra = header(BANK_BASE - 256, STATE_BASE - (BANK_BASE - 256)) + bytes(
    STATE_BASE - (BANK_BASE - 256)
)
engine = Dsp(blob[:split] + extra + blob[split:])
core = engine.core
baseline_engine = None
if a.baseline_package:
    baseline_manifest = json.loads((a.baseline_package / "manifest.json").read_text())
    baseline_blob = (a.baseline_package / baseline_manifest["dsp"]["path"]).read_bytes()
    require(
        hashlib.sha256(baseline_blob).hexdigest()
        == "cee93f5173313dabba145c9c0869f4133a700d1f09d8657305c1f3f593faf8d7",
        "Unknown baseline DSP",
    )
    baseline_listing = (a.baseline_package / "firmware/listing.txt").read_text()
    baseline_pc = int(
        re.search(r"(?m)^cap_stretch_process\.:\n\s+([0-9a-f]+)", baseline_listing)[1],
        16,
    )
    baseline_split = sharcldr.parse_blocks(baseline_blob)[-1]["offset"]
    baseline_engine = Dsp(
        baseline_blob[:baseline_split] + extra + baseline_blob[baseline_split:]
    )
h, libs = host.build(out)
lib = libs["quality"]
bptr = BANK_BASE + 0x20000
sptr = BANK_BASE + 0x21000
dest = BANK_BASE + 0x22004


def poke(at, data):
    require(core.poke(at, data, 1) == len(data), "Fixture write failed")


def raw(at, n):
    return bytes(core.peek(at + i, 1) for i in range(n))


def native_state(s):
    require(ct.sizeof(s.core) == 80, "Unexpected host core ABI")
    return (
        struct.pack("<I", bptr)
        + bytes(s.core)[8:]
        + struct.pack(
            "<9i",
            *[
                getattr(s, n)
                for n in [
                    "start",
                    "end",
                    "reverse",
                    "loop",
                    "first_key",
                    "key_count",
                    "ideal_key",
                    "actual_key",
                    "incoming_key",
                ]
            ],
        )
    )


def install(bank, arrays, state):
    count = bank.count
    poke(BANK_BASE, b"".join(bytes(v) for v in arrays))
    poke(
        bptr,
        struct.pack(
            "<3I4iI",
            BANK_BASE,
            BANK_BASE + count * 4,
            BANK_BASE + count * 8,
            bank.capacity,
            bank.count,
            bank.frames,
            bank.error,
            bank.generation,
        ),
    )
    payload = native_state(state)
    require(len(payload) == 112, "Target state ABI")
    poke(sptr - 4, b"GUAR" + payload + b"END!")


def render(n):
    poke(dest - 4, b"OUT!" + bytes(n * 4) + b"LAST")
    for name, value in {
        "I7": STATE_BASE + 0x17F00,
        "I6": STATE_BASE + 0x17F00,
        "M5": 0,
        "M6": 1,
        "M7": 0xFFFFFFFF,
        "M13": 0,
        "M14": 1,
        "M15": 0xFFFFFFFF,
        "R4": sptr,
        "R8": dest,
        "R12": n,
    }.items():
        core.set_reg(st.UREG_CODES[name], st.Const(value))
    before = core.stats()["instructions"]
    engine.call(pc, 600_000_000)
    used = core.stats()["instructions"] - before
    require(
        raw(dest - 4, 4) == b"OUT!" and raw(dest + n * 4, 4) == b"LAST",
        "Target output overrun",
    )
    require(
        raw(sptr - 4, 4) == b"GUAR" and raw(sptr + 112, 4) == b"END!",
        "Target state overrun",
    )
    return struct.unpack("<" + str(n) + "f", raw(dest, n * 4)), used


report = dict(
    status="running",
    source_hashes=source_hashes(),
    dsp_sha256=manifest["dsp"]["sha256"],
    main_sha256=manifest["cpu"]["sha256"],
    scope=__doc__,
    cases=[],
)
try:
    for kind in ["bass", "tone", "chord"]:
        data = host.signal(kind, 576000)
        bank, arrays = host.sample(h, lib, data)
        for pitch in [0.5, 1, 2]:
            # Seek by the host fixture to one sample before the first splice.
            # Target then executes admission, the entire adaptive fade and tail.
            total = 144000
            original, quality, ue, pe = [(ct.c_float * total)() for _ in range(4)]
            stats = (ct.c_float * 3)()
            require(
                lib.audit(
                    data,
                    len(data),
                    96000,
                    total,
                    pitch,
                    0.425,
                    original,
                    quality,
                    ue,
                    pe,
                    stats,
                )
                == 0
                and stats[2] == 0,
                "Original reference",
            )
            events = [(i, ue[i]) for i in range(total) if ue[i]]
            offset = max(0, events[0][0] - 1) if events else 0
            count = math.ceil(events[0][1] / pitch) + 64 if events else 2048
            if offset + count > total:
                total = offset + count
                original, quality, ue, pe = [(ct.c_float * total)() for _ in range(4)]
                require(
                    lib.audit(
                        data,
                        len(data),
                        96000,
                        total,
                        pitch,
                        0.425,
                        original,
                        quality,
                        ue,
                        pe,
                        stats,
                    )
                    == 0
                    and stats[2] == 0,
                    "Extended original reference",
                )

            def initial(bank=bank, pitch=pitch, offset=offset):
                state = h.base.Stretch()
                require(
                    lib.cap_stretch_start(
                        ct.byref(state),
                        ct.byref(bank),
                        0,
                        576000,
                        0,
                        0,
                        pitch,
                        0.425,
                        128,
                    )
                    == 0,
                    "Host start",
                )
                state.core.ideal_w = state.core.actual_w = state.core.incoming_w = 96000
                state.core.position = 48
                if offset:
                    warm = (ct.c_float * offset)()
                    lib.cap_stretch_process(ct.byref(state), warm, offset)
                return state

            state = initial()
            install(bank, arrays, state)
            target, used = render(count)
            expected = (ct.c_float * count)()
            lib.cap_stretch_process(ct.byref(state), expected, count)
            maximum, rms = host.error(target, expected)
            host.wav(out / f"{kind}-pitch{pitch}-target.wav", target)
            require(
                maximum <= 1e-4 and rms <= 1e-5,
                f"{kind}/{pitch} target max={maximum} rms={rms}",
            )
            original_max, original_rms = host.error(
                target, original[offset : offset + count]
            )
            require(
                original_max <= 1e-4 and original_rms <= 1e-5,
                "Target original Granule mismatch",
            )
            install(bank, arrays, initial())
            repeated, _ = render(count)
            require(target == repeated, "Target repeat drift")
            row = dict(
                signal=kind,
                pitch=pitch,
                host_fixture_seek_output_frames=offset,
                frames=count,
                maximum_error=maximum,
                rms_error=rms,
                original_maximum_error=original_max,
                original_rms_error=original_rms,
                instructions=used,
                repeat_exact=True,
            )
            if baseline_engine is not None:
                quality_engine, quality_pc = engine, pc
                engine, core, pc = baseline_engine, baseline_engine.core, baseline_pc
                try:
                    install(bank, arrays, initial())
                    old_pcm, old_instructions = render(count)
                finally:
                    engine, core, pc = quality_engine, quality_engine.core, quality_pc
                old_max, old_rms = host.error(
                    old_pcm, original[offset : offset + count]
                )
                if events:
                    require(old_max > 1e-4, "Capped target negative did not fail")
                row.update(
                    old_maximum_error=old_max,
                    old_rms_error=old_rms,
                    old_instructions=old_instructions,
                    instruction_ratio=used / old_instructions,
                )
            report["cases"].append(row)
            write_json(out / "report.json", report)
            print(row, flush=True)
    boundary = []
    for kind in ["tone", "silence"]:
        data = host.signal(kind, 2400)
        bank, arrays = host.sample(h, lib, data)
        for pitch, advance, reverse, loop, (start, end) in itertools.product(
            [1 / 32, 1, 32],
            [1 / 65536, 0.425, 64],
            [0, 1],
            [0, 1],
            [(0, 2400), (1200, 1341)],
        ):
            state = h.base.Stretch()
            status = lib.cap_stretch_start(
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
            if status:
                continue
            install(bank, arrays, state)
            actual, used = render(256)
            expected = (ct.c_float * 256)()
            lib.cap_stretch_process(ct.byref(state), expected, 256)
            maximum, rms = host.error(actual, expected)
            require(
                maximum <= 1e-4 and rms <= 1e-5,
                f"Boundary {kind}/{pitch}/{advance}/{reverse}/{loop} max={maximum} rms={rms}",
            )
            boundary.append(dict(maximum_error=maximum, rms_error=rms))
        for pitch in [1 / 32, 0.5, 1, 2, 32]:
            state = h.base.Stretch()
            lib.cap_stretch_start(
                ct.byref(state), ct.byref(bank), 0, 2400, 0, 1, pitch, 1 / 65536, 128
            )
            state.core.splicing = 1
            state.core.increment = 1 / 1_000_000_000
            state.core.phase = ct.c_float(1 - 2**-23).value
            install(bank, arrays, state)
            render(4)
            require(core.peek(sptr + 60) == 0, "Target long fade failed to terminate")
    report["boundary_cases"] = len(boundary)
    report["boundary_maximum_error"] = max(x["maximum_error"] for x in boundary)
    report["phase_progress_cases"] = 10
    require(source_hashes() == report["source_hashes"], "Source drift")
    report["status"] = "passed"
except BaseException as e:
    report.update(status="failed", error=f"{type(e).__name__}: {e}")
    raise
finally:
    write_json(out / "report.json", report)
