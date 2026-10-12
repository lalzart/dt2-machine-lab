#!/usr/bin/env python3
"""Compare split timestamps with the frozen double-precision Capicola core."""

import argparse
import array
import ctypes as ct
import importlib.util
import itertools
import json
import math
import random
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "machines/capicola"
spec = importlib.util.spec_from_file_location(
    "cap_reference", ROOT / "scripts/check-capicola.py"
)
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)


def fingerprint():
    result = ref.fingerprint()
    for relative in [
        "scripts/check-capicola-split.py",
        "scripts/check-capicola-target.py",
        "tests/test_capicola_split.py",
        "docs/CAPICOLA-SPLIT-TIME.md",
    ]:
        result[relative] = ref.sha(ROOT / relative)
    return result


def build(out):
    ref.verify_sources()
    lock = json.loads((MACHINE / "split-contract/source-equivalence.json").read_text())
    for path, digest in lock["baseline_files"].items():
        ref.require(ref.sha(MACHINE / path) == digest, "Baseline drift")
    proposal = json.loads(
        (MACHINE / "split-contract/implementation-contract.json").read_text()
    )["proposal"]
    ref.require(
        ref.sha(ROOT / proposal["path"]) == proposal["sha256"], "Proposal drift"
    )
    engines = []
    for name in ["core", "split"]:
        dest = out / (name + ".dylib")
        subprocess.run(
            [
                "clang",
                "-std=c99",
                "-O2",
                "-ffp-contract=off",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-shared",
                str(MACHINE / (name + ".c")),
                "-o",
                str(dest),
            ],
            check=True,
        )
        engines.append(ref.Engine(ct.CDLL(str(dest)), "cap"))
    return engines


def error(a, b):
    x, y = array.array("f"), array.array("f")
    x.frombytes(a)
    y.frombytes(b)
    ref.require(len(x) == len(y), "Output length")
    ref.require(
        all(math.isfinite(v) for v in x) and all(math.isfinite(v) for v in y),
        "Nonfinite PCM",
    )
    diffs = [abs(i - j) for i, j in zip(x, y, strict=True)]
    return max(diffs, default=0), math.sqrt(
        sum(d * d for d in diffs) / max(1, len(diffs))
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    out = args.output.resolve()
    ref.require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "running",
        "cases": [],
        "boundary": "Host numerical equivalence; no listening, firmware integration or hardware timing claims",
    }
    try:
        base, split = build(out)
        for name in ["duration", "ideal_whole", "ideal_fraction"]:
            fn = getattr(split.lib, "cap_" + name)
            fn.argtypes, fn.restype = [ct.c_void_p], ct.c_int
        report["state_bytes"] = len(split.state)
        report["source_hashes"] = fingerprint()
        for signal in ["silence", "impulse", "sine", "two-tone", "drums"]:
            samples = ref.generate(signal, 48000, 12345)
            for e in [base, split]:
                ref.require(e.load(samples) == 0, "Load failure")
            bk, sk = (
                list(struct.iter_unpack("<fd", base.keys())),
                list(struct.iter_unpack("<fd", split.keys())),
            )
            ref.require(len(bk) == len(sk), "Keyframe count changed")
            ref.require(
                all(a[0] == b[0] for a, b in zip(bk, sk, strict=True)),
                "Keyframe amplitudes changed",
            )
            key_error = max(abs(a[1] - b[1]) for a, b in zip(bk, sk, strict=True))
            ref.require(key_error <= 2**-24, "Keyframe precision exceeded")
            controls = list(itertools.product([0.5, 1, 2], [0.5, 1, 2], [16, 128]))
            controls += [(1, 0.7, 128), (0.7, 1, 128), (1.1, 0.7, 128)]
            controls += [
                (1, struct.unpack("<f", struct.pack("<I", bits))[0], 128)
                for bits in [0x3F000001, 0x3F7FFFFF, 0x3F800001, 0x3FFFFFFF]
            ]
            for pitch, advance, leash in controls:
                pitch, advance = ct.c_float(pitch).value, ct.c_float(advance).value
                n = math.ceil(48000 / advance)
                for e in [base, split]:
                    ref.require(
                        e.call("start", pitch, advance, leash) == 0, "Start failure"
                    )
                expected, actual = base.render(n + 64), split.render(n + 64)
                mx, rms = error(expected, actual)
                ref.require(split.call("position") == n, "Wrong stop time")
                cursor = (
                    split.lib.cap_ideal_whole(split.state)
                    + split.lib.cap_ideal_fraction(split.state) / 2**24
                )
                ref.require(cursor == n * advance, "Accumulated cursor drift")
                split.call("start", pitch, advance, leash)
                ref.require(
                    split.render(n + 64, 137) == actual, "Repeat/partition mismatch"
                )
                record = dict(
                    signal=signal,
                    pitch=pitch,
                    advance=advance,
                    leash=leash,
                    frames=n,
                    max_error=mx,
                    rms_error=rms,
                    key_time_error=key_error,
                    passed=mx <= 1e-4 and rms <= 1e-5,
                )
                report["cases"].append(record)
        rng = random.Random(1)
        for _ in range(3000):
            frames = rng.randrange(1, 48001)
            advance = struct.unpack(
                "<f", struct.pack("<I", rng.randrange(0x3F000000, 0x40000001))
            )[0]
            ref.require(split.load([0] * frames) == 0, "Duration fixture load")
            split.call("start", 1, advance, 128)
            ref.require(
                split.lib.cap_duration(split.state) == math.ceil(frames / advance),
                "Exact duration mismatch",
            )
        report["duration_cases"] = 3000
        report["status"] = (
            "passed" if all(c["passed"] for c in report["cases"]) else "failed"
        )
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        ref.write_json(out / "report.json", report)
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k not in ["cases", "source_hashes"]
                },
                indent=2,
            )
        )
        if report["cases"]:
            print(
                "cases:",
                len(report["cases"]),
                "max error:",
                max(c["max_error"] for c in report["cases"]),
            )
    return report["status"] != "passed"


if __name__ == "__main__":
    raise SystemExit(main())
