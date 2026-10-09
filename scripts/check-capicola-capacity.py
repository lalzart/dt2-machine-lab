#!/usr/bin/env python3
"""Twelve-second Capicola bank/reader capacity and signal comparisons."""

import argparse
import array
import ctypes as ct
import importlib.util
import json
import math
import random
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "machines/capicola"
spec = importlib.util.spec_from_file_location(
    "split_check", ROOT / "scripts/check-capicola-split.py"
)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
ref = previous.ref
MAX_FRAMES = 576000
MAX_KEYS = 576004


class Bank(ct.Structure):
    _fields_ = (
        [
            ("value", ct.POINTER(ct.c_float)),
            ("whole", ct.POINTER(ct.c_int)),
            ("fraction", ct.POINTER(ct.c_uint)),
        ]
        + [(n, ct.c_int) for n in ["capacity", "count", "frames", "error"]]
        + [("generation", ct.c_uint)]
    )


class State(ct.Structure):
    _fields_ = (
        [("bank", ct.POINTER(Bank)), ("generation", ct.c_uint)]
        + [(n, ct.c_int) for n in ["ideal_w", "actual_w", "incoming_w"]]
        + [
            (n, ct.c_uint)
            for n in ["ideal_f", "actual_f", "incoming_f", "pitch_q", "advance_q"]
        ]
        + [(n, ct.c_float) for n in ["pitch", "advance", "phase", "increment"]]
        + [
            (n, ct.c_int)
            for n in ["leash", "splicing", "position", "duration", "active"]
        ]
    )


def bind_api(lib):
    signatures = {
        "cap_bank_init": ([ct.POINTER(Bank)], None),
        "cap_bank_bind": (
            [
                ct.POINTER(Bank),
                ct.POINTER(ct.c_float),
                ct.POINTER(ct.c_int),
                ct.POINTER(ct.c_uint),
                ct.c_int,
            ],
            ct.c_int,
        ),
        "cap_measure": ([ct.POINTER(ct.c_float), ct.c_int], ct.c_int),
        "cap_load": ([ct.POINTER(Bank), ct.POINTER(ct.c_float), ct.c_int], ct.c_int),
        "cap_init": ([ct.POINTER(State)], None),
        "cap_attach": ([ct.POINTER(State), ct.POINTER(Bank)], None),
        "cap_start": ([ct.POINTER(State), ct.c_float, ct.c_float, ct.c_int], ct.c_int),
        "cap_process": ([ct.POINTER(State), ct.POINTER(ct.c_float), ct.c_int], None),
        "cap_stop": ([ct.POINTER(State)], None),
        "cap_test_duration": ([ct.c_int, ct.c_uint], ct.c_int),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(lib, name)
        fn.argtypes = args
        fn.restype = result
    return lib


def build(out):
    ref.verify_sources()
    lock = json.loads(
        (MACHINE / "capacity-contract/source-equivalence.json").read_text()
    )
    for name, digest in lock["baseline_files"].items():
        ref.require(ref.sha(MACHINE / name) == digest, "Baseline drift: " + name)
    proposal = json.loads(
        (MACHINE / "capacity-contract/implementation-contract.json").read_text()
    )["proposal"]
    ref.require(
        ref.sha(ROOT / proposal["path"]) == proposal["sha256"], "Proposal drift"
    )
    scratch = out / "reference"
    scratch.mkdir()
    (scratch / "core.c").write_bytes((MACHINE / "core.c").read_bytes())
    (scratch / "core.h").write_text(
        (MACHINE / "core.h")
        .read_text()
        .replace("#define CAP_CAPACITY 4096", "#define CAP_CAPACITY 576004")
        .replace("#define CAP_MAX_INPUT 48000", "#define CAP_MAX_INPUT 576000")
    )
    helper = out / "capacity-host.c"
    helper.write_text(
        '#include "'
        + str(MACHINE / "capacity.c")
        + '"\nint cap_test_duration(int frames,unsigned rate){return exact_duration(frames,rate);}\n'
    )
    for name, src in [
        ("reference", scratch / "core.c"),
        ("capacity", helper),
        ("previous", MACHINE / "split.c"),
    ]:
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
                str(src),
                "-o",
                str(out / (name + ".dylib")),
            ],
            check=True,
        )
    return (
        bind_api(ct.CDLL(str(out / "capacity.dylib"))),
        ref.Engine(ct.CDLL(str(out / "reference.dylib")), "cap"),
        ref.Engine(ct.CDLL(str(out / "previous.dylib")), "cap"),
    )


def pcm_array(samples):
    return (ct.c_float * len(samples)).from_buffer_copy(array.array("f", samples))


class Sample:
    def __init__(self, lib, samples, capacity=None):
        self.lib = lib
        self.bank = Bank()
        lib.cap_bank_init(ct.byref(self.bank))
        data = pcm_array(samples)
        self.measured = lib.cap_measure(data, len(data))
        ref.require(self.measured >= 2, "Measurement failed")
        self.capacity = self.measured if capacity is None else capacity
        self.backing = []
        self.arrays = []
        for kind in [ct.c_float, ct.c_int, ct.c_uint]:
            raw = (ct.c_uint * (self.capacity + 2))()
            raw[0] = raw[-1] = 0x12345678
            self.backing.append(raw)
            self.arrays.append((kind * self.capacity).from_buffer(raw, 4))
        ref.require(
            lib.cap_bank_bind(ct.byref(self.bank), *self.arrays, self.capacity) == 0,
            "Bind failed",
        )
        self.result = lib.cap_load(ct.byref(self.bank), data, len(data))
        self.guards()

    def guards(self):
        ref.require(
            all(a[0] == a[-1] == 0x12345678 for a in self.backing), "Storage overrun"
        )

    def keys(self):
        return b"".join(
            struct.pack(
                "<fd", self.arrays[0][i], self.arrays[1][i] + self.arrays[2][i] / 2**24
            )
            for i in range(self.bank.count)
        )

    def payload(self):
        return b"".join(bytes(a) for a in self.arrays)


class Reader:
    def __init__(self, sample):
        self.sample = sample
        self.lib = sample.lib
        self.state = State()
        self.lib.cap_attach(ct.byref(self.state), ct.byref(sample.bank))

    def start(self, pitch=1, advance=1, leash=128):
        return self.lib.cap_start(ct.byref(self.state), pitch, advance, leash)

    def render(self, count, block=4096):
        result = bytearray()
        for offset in range(0, count, block):
            n = min(block, count - offset)
            out = (ct.c_float * (n + 2))()
            out[0] = out[-1] = 123
            self.lib.cap_process(
                ct.byref(self.state),
                ct.cast(ct.byref(out, 4), ct.POINTER(ct.c_float)),
                n,
            )
            ref.require(out[0] == out[-1] == 123, "Output overrun")
            result.extend(bytes(out)[4:-4])
        return bytes(result)


def fixture(name, n=MAX_FRAMES):
    data = ref.generate(name, n, 1)
    if name == "impulse":
        if n > 4800:
            data[4800] = 0
        data[min(n - 1, 552000)] = 0.75
    return data


def source_hashes():
    result = previous.fingerprint()
    for name in [
        "docs/CAPICOLA-TWELVE-SECONDS.md",
        "scripts/check-capicola-capacity.py",
        "scripts/check-capicola-capacity-target.py",
        "tests/test_capicola_capacity.py",
    ]:
        p = ROOT / name
        if p.exists():
            result[name] = ref.sha(p)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    out = args.output.resolve()
    ref.require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "running",
        "cases": [],
        "banks": [],
        "boundary": "Host capacity and numerical evidence; no firmware memory or physical timing claim",
    }
    try:
        lib, oracle, old = build(out)
        report["source_hashes"] = source_hashes()
        report["adapted_reference_hashes"] = {
            p.name: ref.sha(p) for p in (out / "reference").iterdir()
        }
        report["host_reader_bytes"] = ct.sizeof(State)
        report["host_bank_metadata_bytes"] = ct.sizeof(Bank)
        rng = random.Random(1)
        for _ in range(10000):
            frames = rng.randrange(1, MAX_FRAMES + 1)
            rate = struct.unpack(
                "<f", struct.pack("<I", rng.randrange(0x3F000000, 0x40000001))
            )[0]
            ref.require(
                lib.cap_test_duration(frames, int(rate * 2**24))
                == math.ceil(frames / rate),
                "Duration overflow",
            )
        old_product = ((8192 * 960000) & 0xFFFFFFFF) >> 12
        ref.require(
            old_product != 1920000, "Negative duration comparator is not falsifying"
        )
        report["duration_cases"] = 10000
        report["old_duration_negative"] = {"actual": old_product, "expected": 1920000}
        for name in ["silence", "impulse", "sine", "two-tone", "drums", "noise"]:
            data = fixture(name)
            sample = Sample(lib, data)
            ref.require(
                sample.result == 0 and sample.bank.count == sample.measured,
                "Measured load failed",
            )
            report["banks"].append(
                dict(
                    signal=name,
                    frames=len(data),
                    keys=sample.bank.count,
                    storage_bytes=sample.bank.count * 12,
                )
            )
            ref.require(oracle.load(data) == 0, "Oracle capacity failure")
            ak, bk = (
                list(struct.iter_unpack("<fd", oracle.keys())),
                list(struct.iter_unpack("<fd", sample.keys())),
            )
            ref.require(len(ak) == len(bk), "Keyframe count mismatch")
            ref.require(
                all(
                    a[0] == b[0] and abs(a[1] - b[1]) <= 2**-24
                    for a, b in zip(ak, bk, strict=True)
                ),
                "Keyframe mismatch",
            )
            reader = Reader(sample)
            bank_before = sample.payload()
            for pitch, advance in [(1, 0.7), (0.7, 1), (1.1, 0.7), (0.5, 2), (2, 0.5)]:
                pitch, advance = ct.c_float(pitch).value, ct.c_float(advance).value
                n = math.ceil(MAX_FRAMES / advance)
                ref.require(reader.start(pitch, advance) == 0, "Start failed")
                oracle.call("start", pitch, advance, 128)
                expected = oracle.render(n + 64, 4096)
                actual = reader.render(n + 64)
                mx, rms = previous.error(expected, actual)
                values = array.array("f")
                values.frombytes(actual)
                ref.require(
                    max(abs(v) for v in values) <= max(abs(v) for v in data) + 1e-6,
                    "Peak bound",
                )
                ref.require(
                    reader.state.position == n
                    and reader.state.ideal_w + reader.state.ideal_f / 2**24
                    == n * advance,
                    "Duration/cursor drift",
                )
                reader.start(pitch, advance)
                ref.require(
                    reader.render(n + 64, 127) == actual, "Partition/repeat mismatch"
                )
                case = dict(
                    signal=name,
                    pitch=pitch,
                    advance=advance,
                    frames=n,
                    max_error=mx,
                    rms_error=rms,
                    passed=mx <= 1e-4 and rms <= 1e-5,
                )
                report["cases"].append(case)
            ref.require(sample.payload() == bank_before, "Reader mutated bank")
            sample.guards()
            if name in ["sine", "drums", "noise"]:
                ref.save_wav(out / (name + "-twelve-seconds.wav"), actual)
            print(json.dumps(report["banks"][-1]), flush=True)
            # Existing one-second behavior remains byte-identical where capacity permits.
            short = fixture(name, 48000)
            if old.load(short) == 0:
                small = Reader(Sample(lib, short))
                small.start(1.1, 0.7)
                old.call("start", 1.1, 0.7, 128)
                ref.require(
                    small.render(68636) == old.render(68636, 4096),
                    "Previous split compatibility",
                )
        negative = Reader(Sample(lib, fixture("sine", 48000)))
        negative.start(0.5, 0.7)
        oracle.load(fixture("sine", 48000))
        oracle.call("start", 1.1, 0.7, 128)
        wrong_max, _ = previous.error(negative.render(4096), oracle.render(4096, 4096))
        ref.require(wrong_max > 1e-4, "Wrong-pitch negative comparator failed")
        report["wrong_pitch_negative_max_error"] = wrong_max
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
                    if k not in ["source_hashes", "cases"]
                },
                indent=2,
            )
        )
    return report["status"] != "passed"


if __name__ == "__main__":
    raise SystemExit(main())
