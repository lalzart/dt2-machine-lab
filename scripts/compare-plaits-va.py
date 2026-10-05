# ruff: noqa: E402
"""Compare optional Plaits optimizations on identical host and emulator inputs."""

import argparse
import array
import ctypes
import hashlib
import itertools
import json
import math
import os
import re
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument(
    "--stage", choices=("host", "target", "firmware", "all"), default="all"
)
args = parser.parse_args()
doctor()
out = args.output.resolve()
if not out.is_relative_to(ROOT / "out/runs"):
    raise ValueError("Output must be below out/runs")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.dsp import Dsp
from lab.formats import read_frames
from lab.metrics import distribution
from lab.plaits import MACHINE, build_blob, command

source = ROOT / ".local/sources/eurorack"
lock = json.loads((MACHINE / "source-lock.json").read_text())
for name, digest in lock["files"].items():
    if sha256(source / name) != digest:
        raise ValueError(f"Upstream source drift: {name}")
for path, revision in (
    (source, lock["revision"]),
    (source / "stmlib", lock["stmlib_revision"]),
):
    if command(["git", "-C", path, "rev-parse", "HEAD"]).strip() != revision:
        raise ValueError("Wrong upstream revision")
    if command(["git", "-C", path, "status", "--porcelain"]).strip():
        raise ValueError("Dirty upstream source")
fingerprint = source_hashes()
report = {
    "stage": args.stage,
    "source_sha256": fingerprint,
    "source_lock": lock,
    "contract_sha256": sha256(ROOT / "docs/PLAITS-OPTIMIZATION.md"),
    "cpu_load_percent": None,
    "dsp_load_percent": None,
    "boundary": "Prepared emulator work and voice-buffer PCM; no physical timing, final mix or hardware claim.",
}
started = time.monotonic()
TIMELINE = (
    (60, 0.5, 0.5, 0.5),
    (48, 0.2, 0.15, 0.8),
    (67, 0.8, 0.9, 0.2),
    (60, 0.5, 0.5, 0.5),
)
CORNERS = list(itertools.product((0, 127), (0, 1), (0, 1), (0, 1)))
VARIANTS = ("reference", "main-only", "shared")
STATE = 0x200E1000
CACHE = 0x200E2000
VOICES = (0x2412CC, 0x2414A4)
CAPTURE_SHA = "f4b6e802a45b0577da14a956949d891b588a6b8c892bf7be3ccb7878581746e5"
REFERENCE_PCM_SHA = "48f2adba0303ee4170b8014332030bc24f8ba17b2b898f63a671aca21c5508ff"


def require(value, message):
    if not value:
        raise ValueError(message)


def raw(values):
    require(all(map(math.isfinite, values)), "Nonfinite PCM")
    require(max(map(abs, values), default=0) < 4, "PCM out of bounds")
    return array.array("f", values).tobytes()


def equal(a, b, label):
    require(a == b, f"Exact comparison failed: {label}")


def peek_bytes(core, addr, size):
    return struct.pack(
        f"<{size // 4}I", *(core.peek(addr + i) for i in range(0, size, 4))
    )


def save_pcm(name, values):
    data = raw(values)
    (out / f"{name}.f32").write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def host():
    print("Host MAIN equivalence against original C++ and full C", flush=True)
    common = ["-O2", "-ffp-contract=off", "-shared"]
    command(
        [
            "clang++",
            "-std=c++11",
            *common,
            "-DTEST",
            "-I" + str(source),
            MACHINE / "oracle.cc",
            source / "plaits/dsp/engine/virtual_analog_engine.cc",
            source / "stmlib/dsp/units.cc",
            "-o",
            out / "oracle.dylib",
        ]
    )
    libs = []
    for name in VARIANTS[:2]:
        defines = ["-DPLAITS_MAIN_ONLY=1"] if name == "main-only" else []
        command(
            [
                "clang",
                "-std=c99",
                *common,
                *defines,
                MACHINE / "core.c",
                "-o",
                out / f"{name}.dylib",
            ]
        )
        libs.append(ctypes.CDLL(str(out / f"{name}.dylib")))
    oracle = ctypes.CDLL(str(out / "oracle.dylib"))
    states = [ctypes.create_string_buffer(252) for _ in libs]
    f12, f4 = ctypes.c_float * 12, ctypes.c_float * 4
    pcm = []
    samples = 0
    for case in range(17):
        for lib, state in zip(libs, states, strict=True):
            lib.va_init(state)
        oracle.oracle_init()
        for i in range(16000 if case == 0 else 120):
            p = f4(*(TIMELINE[i // 4000] if case == 0 else CORNERS[case - 1]))
            aa, ab = f12(), f12()
            oracle.oracle_render(p, aa, ab)
            for n, (lib, state) in enumerate(zip(libs, states, strict=True)):
                bb, bc = f12(), f12(*([123.0] * 12))
                lib.va_render(state, p, bb, bc, 12)
                equal(bytes(aa), bytes(bb), f"host case {case} block {i} {n}")
                equal(
                    bytes(ab) if n == 0 else bytes(f12(*([123.0] * 12))),
                    bytes(bc),
                    "AUX reference/sentinel",
                )
            raw(aa)
            samples += 12
            if case == 0:
                pcm.extend(aa)
    report["host"] = {
        "main_bit_exact": True,
        "aux_untouched": True,
        "samples_per_variant": samples,
        "main_pcm_sha256": save_pcm("host-main", pcm),
    }


def target():
    print("Standalone SHARC reference versus MAIN-only", flush=True)
    engines = [
        Dsp(build_blob(variant=v, output=out / ("target-" + v))) for v in VARIANTS[:2]
    ]
    costs = [[], []]
    pcm = []
    for case in range(17):
        for i in range(16000 if case == 0 else 120):
            p = TIMELINE[i // 4000] if case == 0 else CORNERS[case - 1]
            blocks = []
            for n, engine in enumerate(engines):
                engine.core.poke(0x200E0000, struct.pack("<5f", *p, float(i == 0)), 1)
                before = engine.core.stats()["instructions"]
                engine.call(0xBC0000, 500000)
                if case == 0:
                    costs[n].append(engine.core.stats()["instructions"] - before)
                blocks.append(peek_bytes(engine.core, 0x200E0400, 48))
            equal(*blocks, f"target case {case} block {i}")
            samples = struct.unpack("<12f", blocks[0])
            raw(samples)
            if case == 0:
                pcm.extend(samples)
            if case == 0 and i % 4000 == 0:
                print(f"  SHARC blocks {i}/16000", flush=True)
    report["target"] = {
        "main_bit_exact": True,
        "corners": 16,
        "main_pcm_sha256": save_pcm("target-main", pcm),
        "instructions_per_12_sample_block": {
            v: distribution(c) for v, c in zip(VARIANTS[:2], costs, strict=True)
        },
        "instruction_reduction_percent": 100 * (1 - sum(costs[1]) / sum(costs[0])),
    }


def frames():
    capture = ROOT / "out/runs/controls-final-capture"
    equal(sha256(capture / "controls.dtfr"), CAPTURE_SHA, "real control capture hash")
    meta = json.loads((capture / "capture.json").read_text())
    data = read_frames(capture / "controls.dtfr")
    a, b = meta["play_start"], meta["play_end"]
    result = [
        bytearray(f) for f in [data[a - 1]] * 150 + data[a:b] + [data[b - 1]] * 500
    ]
    for f in result:
        for off in (0x22, 0x24, 0x26, 0x28):
            f[off : off + 2] = (int.from_bytes(f[off : off + 2], "big") & 1).to_bytes(
                2, "big"
            )
    for f in (result[0], result[-1]):
        require(
            not any(f[o : o + 2] != b"\0\0" for o in (0x22, 0x24, 0x26, 0x28)),
            "Event-bearing padding",
        )
    equal(len(result), 801, "prepared capture length")
    report["capture"] = {
        "sha256": CAPTURE_SHA,
        "frames": len(result),
        "prepared_sha256": hashlib.sha256(b"".join(result)).hexdigest(),
        "adaptation": "150 preroll + captured preview + 500 tail frames; other-track event bits masked",
    }
    return result


def replay(blob, inputs):
    engine = Dsp(blob)
    pcm, events = [], []
    old_age = 0
    for i, f in enumerate(inputs):
        pcm.extend(engine.frame(f))
        age = engine.core.peek(STATE + 368)
        if age and (age < old_age or not old_age):
            events.append(i)
        old_age = age
    return engine, pcm, events


def cache_counts(engine):
    return {"hits": engine.core.peek(CACHE + 4), "misses": engine.core.peek(CACHE + 8)}


def machine_calls(blobs):
    """Synthetic adapter events; not a claim about firmware scheduler ordering."""
    import sharc_trace as st

    engines = [Dsp(blobs[v]) for v in ("main-only", "shared")]
    entries = []
    for v in ("main-only", "shared"):
        listing = (out / ("firmware-" + v) / "listing.txt").read_text()
        entries.append(
            int(re.search(r"(?m)^machine\.:\n\s+([0-9a-f]+)", listing)[1], 16)
        )

    def invoke(engine, entry, lane, trigger=0, note=60, macros=(0.5, 0.5, 0.5), typ=7):
        core = engine.core
        # Same private-stack ABI as the build wrapper, with a synthetic top-level return.
        registers = {
            "M5": 0,
            "M6": 1,
            "M7": -1,
            "M14": 1,
            "I6": 0x200DFF00,
            "I7": 0x200DFEF8,
            "R4": VOICES[lane],
        }
        registers.update({f"L{i}": 0 for i in range(16)})
        for key, value in registers.items():
            core.set_reg(st.UREG_CODES[key], st.Const(value))
        core.poke(0x200DFEFC, struct.pack("<II", 0, 0), 1)
        values = {
            0x255970: typ,
            0x24F0CC: trigger << (8 * lane),
            0x2558DE: (note + 55) * 256,
            0x2559B6: 0,
            0x2559B8: round(macros[0] * 32768),
            0x2559BC: round(macros[1] * 32768),
            0x2559BE: round(macros[2] * 32768),
            0x2559C4: 1229,
            0x2559C8: 16384,
        }
        for addr, value in values.items():
            core.poke(addr, struct.pack("<I", value), 1)
        # A downstream-mutated source buffer must never become the cache's authority.
        core.poke(VOICES[lane] + 4, struct.pack("<64f", *([0.123] * 64)), 1)
        engine.call(entry, 500000)
        return peek_bytes(core, VOICES[lane] + 4, 256), peek_bytes(core, STATE, 768)

    scenarios = [
        ("matching", [(0, 1), (1, 1)] + [(n, 0) for _ in range(5) for n in (0, 1)]),
        ("reversed", [(1, 1), (0, 1)] + [(n, 0) for _ in range(5) for n in (1, 0)]),
        ("skipped/repeated", [(0, 0), (0, 0), (1, 0), (1, 0), (1, 0), (0, 0)]),
        ("unequal trigger", [(0, 1, 72, (0.1, 0.8, 0.3)), (1, 0), (0, 0), (1, 0)]),
        ("other lane control", [(1, 1, 40, (0.9, 0.2, 0.8)), (0, 0), (1, 0)]),
        (
            "switch away/back",
            [(0, 0, 60, (0.5, 0.5, 0.5), 6), (1, 0), (0, 0), (0, 1), (1, 1)],
        ),
        ("tail completion", [(n, 0) for _ in range(25) for n in (0, 1)]),
    ]
    calls = 0
    for label, events in scenarios:
        for event in events:
            results = [
                invoke(e, entry, *event)
                for e, entry in zip(engines, entries, strict=True)
            ]
            if results[0] != results[1]:
                write_json(
                    out / "lane-mismatch.json",
                    {
                        "scenario": label,
                        "event": event,
                        "calls_before_failure": calls,
                        "cache": cache_counts(engines[1]),
                        "cache_words": struct.unpack(
                            "<259I", peek_bytes(engines[1].core, CACHE, 1036)
                        ),
                        "buffers_and_states": [
                            [list(struct.unpack(f"<{len(b) // 4}I", b)) for b in r]
                            for r in results
                        ],
                    },
                )
            equal(*results, f"machine state/buffer: {label} {event}")
            calls += 1
    counts = cache_counts(engines[1])
    require(
        counts["hits"] and counts["misses"],
        "Cache cases did not exercise both branches",
    )
    # Force the exact cached pre-state into lane 1, then poison one cached sample.
    # This proves the comparison detects a wrong cache hit, even for a quiet tail.
    before = peek_bytes(engines[1].core, CACHE + 12, 384)
    for e in engines:
        e.core.poke(STATE + 384, before, 1)
    engines[1].core.poke(CACHE + 780, struct.pack("<f", 0.75), 1)
    aa, bb = [invoke(e, entry, 1) for e, entry in zip(engines, entries, strict=True)]
    require(aa != bb, "Corrupted-cache negative was not detected")
    report["lane_cases"] = {
        "calls": calls,
        "scenarios": [s[0] for s in scenarios],
        "state_and_buffers_bit_exact": True,
        "cache": counts,
        "corrupted_cache_negative_detected": True,
    }


def firmware():
    print("Building three firmware variants", flush=True)
    blobs = {
        v: build_blob(True, variant=v, output=out / ("firmware-" + v)) for v in VARIANTS
    }
    machine_calls(blobs)
    inputs = frames()
    results = {}
    reference = None
    for v in VARIANTS:
        print(f"Replaying 801 identical frames: {v}", flush=True)
        engine, pcm, events = replay(blobs[v], inputs)
        digest = save_pcm("firmware-" + v, pcm)
        equal(digest, REFERENCE_PCM_SHA, f"baseline PCM hash: {v}")
        equal(events, [158, 210, 260], f"preview events: {v}")
        if reference is None:
            reference = pcm
        equal(raw(reference), raw(pcm), f"firmware {v}")
        first, second, third = [i * 64 for i in events]
        span = min(second - first, len(pcm) - third)
        equal(
            pcm[first : first + span], pcm[third : third + span], f"locked recall: {v}"
        )
        results[v] = {
            "pcm_sha256": digest,
            "events": events,
            "locked_equal_samples": span,
            "block_handler_instructions": sum(engine.block_instructions),
            "instructions_per_frame": distribution(engine.block_instructions),
        }
        if v == "shared":
            results[v]["cache"] = cache_counts(engine)
            require(results[v]["cache"]["hits"] > 0, "Real replay never shares")
    print("Shared repeat, stock-hook parity and disabled-hook negative", flush=True)
    _, repeat, _ = replay(blobs["shared"], inputs)
    equal(raw(reference), raw(repeat), "shared repeat")
    import sharcldr

    bypass = bytearray(blobs["shared"])
    at = sharcldr.offset_for_address(sharcldr.parse_blocks(bypass), 0x1C4F15)
    bypass[at : at + 6] = bytes.fromhex("5499a801408c")
    stock_frames = [bytearray(f) for f in inputs[:240]]
    for f in stock_frames:
        f[0x94:0x96] = b"\0\6"
    _, aa, _ = replay(blobs["shared"], stock_frames)
    _, bb, _ = replay(bytes(bypass), stock_frames)
    equal(raw(aa), raw(bb), "stock hook parity")
    _, negative, _ = replay(bytes(bypass), inputs[:240])
    difference = max(
        abs(a - b) for a, b in zip(reference[: len(negative)], negative, strict=True)
    )
    require(difference > 1e-5, "Disabled-hook negative failed")
    for v in VARIANTS[1:]:
        results[v]["instruction_reduction_percent"] = 100 * (
            1
            - results[v]["block_handler_instructions"]
            / results["reference"]["block_handler_instructions"]
        )
    report["firmware"] = {
        "variants": results,
        "repeat_bit_exact": True,
        "stock_hook_bit_exact": True,
        "disabled_hook_difference": difference,
    }


try:
    if args.stage in ("all", "host"):
        host()
    if args.stage in ("all", "target"):
        target()
    if args.stage in ("all", "firmware"):
        firmware()
    equal(source_hashes(), fingerprint, "source freshness")
    report["status"] = "passed"
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    report["host_seconds"] = time.monotonic() - started
    report["outputs"] = {
        str(p.relative_to(out)): sha256(p)
        for p in out.rglob("*")
        if p.is_file() and p.suffix in (".f32", ".bin", ".dxe", ".dylib")
    }
    write_json(out / "report.json", report)
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("source_sha256", "source_lock", "outputs")
            },
            indent=2,
        ),
        flush=True,
    )
