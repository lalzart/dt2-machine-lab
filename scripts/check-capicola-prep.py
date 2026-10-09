#!/usr/bin/env python3
"""Host parity and lifecycle checks for bounded native bank preparation."""

import argparse
import ctypes as ct
import hashlib
import importlib.util
import json
import math
import random
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "capacity_check", ROOT / "scripts/check-capicola-capacity.py"
)
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)


class Prep(ct.Structure):
    _fields_ = (
        [
            ("bank", ct.POINTER(ref.Bank)),
            ("input", ct.POINTER(ct.c_short)),
            ("token", ct.c_uint),
            ("generation", ct.c_uint),
        ]
        + [
            (n, ct.c_int)
            for n in ("frames", "stride", "phase", "index", "count", "needed", "wp")
        ]
        + [
            ("raw", ct.c_float * 8),
            ("deriv", ct.c_float),
            ("last_value", ct.c_float),
            ("last_whole", ct.c_int),
            ("last_fraction", ct.c_uint),
        ]
    )


def build(out):
    ref.build(out)
    helper = out / "prep-host.c"
    helper.write_text(
        '#include "'
        + str(ROOT / "machines/capicola/capacity.c")
        + '"\n#include "'
        + str(ROOT / "machines/capicola/prepare.c")
        + '"\nint cap_test_duration(int n,unsigned q){return exact_duration(n,q);}\n'
    )
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
            str(helper),
            "-o",
            str(out / "prep.dylib"),
        ],
        check=True,
    )
    lib = ref.bind_api(ct.CDLL(str(out / "prep.dylib")))
    for name, args, result in [
        ("init", [ct.POINTER(Prep), ct.POINTER(ref.Bank)], None),
        ("cancel", [ct.POINTER(Prep)], None),
        (
            "begin",
            [ct.POINTER(Prep), ct.POINTER(ct.c_short), ct.c_int, ct.c_int, ct.c_uint],
            ct.c_int,
        ),
        (
            "storage",
            [
                ct.POINTER(Prep),
                ct.POINTER(ct.c_float),
                ct.POINTER(ct.c_int),
                ct.POINTER(ct.c_uint),
                ct.c_int,
            ],
            ct.c_int,
        ),
        ("step", [ct.POINTER(Prep), ct.c_uint, ct.c_int], ct.c_int),
    ]:
        f = getattr(lib, "cap_prepare_" + name)
        f.argtypes = args
        f.restype = result
    return lib, ref


def fingerprints():
    paths = [
        ROOT / name
        for name in (
            "machines/capicola/capacity.c",
            "machines/capicola/capacity.h",
            "machines/capicola/prepare.c",
            "machines/capicola/prepare.h",
            "machines/capicola/prepare-target.c",
            "scripts/check-capicola-prep.py",
            "scripts/check-capicola-prep-target.py",
        )
    ]
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
    }


def fixture(name, n):
    rng = random.Random(1)
    if name == "silence":
        return [0] * n
    if name == "impulse":
        return [24000 if i == n // 2 else 0 for i in range(n)]
    if name == "noise":
        return [rng.randrange(-16000, 16001) for _ in range(n)]
    return [
        int(
            8000
            * (
                math.sin(2 * math.pi * 220 * i / 48000)
                + (math.sin(2 * math.pi * 331 * i / 48000) if name == "two-tone" else 0)
            )
        )
        for i in range(n)
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    out = parser.parse_args().output.resolve()
    assert out.is_relative_to(ROOT / "out/runs")
    out.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "cases": [], "source_hashes": fingerprints()}
    try:
        lib, _ = build(out)
        for n in (1, 1024, 576000):
            for name in ("silence", "impulse", "sine", "two-tone", "noise"):
                values = fixture(name, n)
                expected = ref.Sample(lib, [v / 32768 for v in values])
                for stride in (1, 2):
                    raw = (ct.c_short * (n * stride))(
                        *[x for v in values for x in ([v] if stride == 1 else [v, -v])]
                    )
                    for budget in (1, 32, 256) if n < 576000 else (256,):
                        bank = ref.Bank()
                        lib.cap_bank_init(ct.byref(bank))
                        p = Prep()
                        lib.cap_prepare_init(ct.byref(p), ct.byref(bank))
                        assert (
                            lib.cap_prepare_begin(ct.byref(p), raw, n, stride, 7) == 1
                        )
                        for phase in (1, 3):
                            while p.phase == phase:
                                before = p.index
                                lib.cap_prepare_step(ct.byref(p), 7, budget)
                                assert 0 <= p.index - before <= budget
                                if p.phase != 4:
                                    assert (
                                        bank.error
                                        and not bank.count
                                        and not bank.frames
                                    )
                            if phase == 1:
                                assert p.phase == 2 and p.needed == expected.bank.count
                                count = p.needed
                                value = (ct.c_float * count)()
                                whole = (ct.c_int * count)()
                                fraction = (ct.c_uint * count)()
                                assert (
                                    lib.cap_prepare_storage(
                                        ct.byref(p), value, whole, fraction, count
                                    )
                                    == 3
                                )
                        assert p.phase == 4 and bank.count == count and not p.input
                        assert (
                            bytes(value) + bytes(whole) + bytes(fraction)
                            == expected.payload()
                        ), (name, n, stride, budget)
                        lib.cap_prepare_cancel(ct.byref(p))
                        assert bank.error and bank.count == 0 and not p.input
                        report["cases"].append(
                            dict(
                                name=name,
                                frames=n,
                                stride=stride,
                                budget=budget,
                                keys=count,
                            )
                        )
        # Source identity, stale generation, bad budget and storage must fail closed.
        raw = (ct.c_short * 8)(1, 2, 3, 4, 5, 6, 7, 8)
        for mode in (
            "token",
            "generation",
            "budget0",
            "budget257",
            "small-storage",
            "null-storage",
            "oversize",
            "stride",
        ):
            bank = ref.Bank()
            lib.cap_bank_init(ct.byref(bank))
            p = Prep()
            lib.cap_prepare_init(ct.byref(p), ct.byref(bank))
            phase = lib.cap_prepare_begin(
                ct.byref(p),
                raw,
                576001 if mode == "oversize" else 8,
                3 if mode == "stride" else 1,
                7,
            )
            if mode not in ("oversize", "stride"):
                if mode == "generation":
                    bank.generation += 1
                if "storage" in mode:
                    assert lib.cap_prepare_step(ct.byref(p), 7, 256) == 2
                    phase = lib.cap_prepare_storage(
                        ct.byref(p),
                        None,
                        None,
                        None,
                        1 if mode == "small-storage" else p.needed,
                    )
                else:
                    phase = lib.cap_prepare_step(
                        ct.byref(p),
                        8 if mode == "token" else 7,
                        0 if mode == "budget0" else 257 if mode == "budget257" else 1,
                    )
            assert phase == 5 and bank.error and not p.input and not bank.count, mode
        # An active reader must stop immediately when a replacement begins.
        sample = ref.Sample(lib, [v / 32768 for v in fixture("sine", 1024)])
        original_payload = sample.payload()
        reader = ref.Reader(sample)
        assert reader.start() == 0
        assert any(struct_value != 0 for struct_value in reader.render(64))
        p = Prep()
        lib.cap_prepare_init(ct.byref(p), ct.byref(sample.bank))
        assert lib.cap_prepare_begin(ct.byref(p), raw, 8, 1, 7) == 1
        assert reader.render(64) == bytes(256)
        lib.cap_prepare_cancel(ct.byref(p))
        # A changed-input comparator must be observable in the bank.
        changed = ref.Sample(lib, [v / 32768 for v in fixture("two-tone", 1024)])
        assert original_payload != changed.payload()
        assert fingerprints() == report["source_hashes"], "Source drift"
        report.update(status="passed", negative_cases=8)
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                dict(
                    status=report["status"],
                    cases=len(report["cases"]),
                    error=report.get("error"),
                )
            )
        )


if __name__ == "__main__":
    main()
