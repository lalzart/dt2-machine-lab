#!/usr/bin/env python3
"""Host signal and state gates for STRETCH R1; never claims hardware timing."""

import argparse
import ctypes as ct
import hashlib
import importlib.util
import itertools
import json
import math
import random
import subprocess
from pathlib import Path

from capicola_stretch_reference import Reader

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "machines/capicola"
spec = importlib.util.spec_from_file_location(
    "capacity_check", ROOT / "scripts/check-capicola-capacity.py"
)
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


class Stretch(ct.Structure):
    _fields_ = [("core", capacity.State)] + [
        (name, ct.c_int)
        for name in (
            "start",
            "end",
            "reverse",
            "loop",
            "first_key",
            "key_count",
            "ideal_key",
            "actual_key",
            "incoming_key",
        )
    ]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def build(out):
    capacity.ref.verify_sources()
    contract = json.loads(
        (MACHINE / "stretch-contract/implementation-contract.json").read_text()
    )
    proposal = contract["proposal"]
    require(
        hashlib.sha256((ROOT / proposal["path"]).read_bytes()).hexdigest()
        == proposal["sha256"],
        "Frozen proposal drift",
    )
    lock = json.loads(
        (MACHINE / "stretch-contract/source-equivalence.json").read_text()
    )
    for name, digest in lock["baseline_files"].items():
        require(
            hashlib.sha256((MACHINE / name).read_bytes()).hexdigest() == digest,
            "Baseline drift: " + name,
        )
    helper = out / "host.c"
    helper.write_text(
        f'#include "{MACHINE / "stretch.c"}"\nint cap_test_duration(int n,unsigned rate){{return exact_duration(n,rate);}}\n'
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
            str(out / "stretch.dylib"),
        ],
        check=True,
    )
    lib = capacity.bind_api(ct.CDLL(str(out / "stretch.dylib")))
    for name, args, result in [
        ("cap_stretch_init", [ct.POINTER(Stretch)], None),
        (
            "cap_stretch_start",
            [
                ct.POINTER(Stretch),
                ct.POINTER(capacity.Bank),
                ct.c_int,
                ct.c_int,
                ct.c_int,
                ct.c_int,
                ct.c_float,
                ct.c_float,
                ct.c_int,
            ],
            ct.c_int,
        ),
        ("cap_stretch_update", [ct.POINTER(Stretch), ct.c_float, ct.c_float], ct.c_int),
        (
            "cap_stretch_process",
            [ct.POINTER(Stretch), ct.POINTER(ct.c_float), ct.c_int],
            None,
        ),
        ("cap_stretch_stop", [ct.POINTER(Stretch)], None),
    ]:
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = args, result
    return lib


def start(lib, sample, region, reverse, loop, pitch, advance):
    state = Stretch()
    result = lib.cap_stretch_start(
        ct.byref(state),
        ct.byref(sample.bank),
        *region,
        reverse,
        loop,
        pitch,
        advance,
        128,
    )
    require(
        result == 0,
        f"Start rejected {(region, reverse, loop, pitch, advance)}: {result}",
    )
    return state


def process(lib, state, frames):
    output = (ct.c_float * frames)()
    lib.cap_stretch_process(ct.byref(state), output, frames)
    return list(output)


def model(sample, region, reverse, loop, pitch, advance):
    times = [
        sample.arrays[1][i] + sample.arrays[2][i] / 2**24
        for i in range(sample.bank.count)
    ]
    values = list(sample.arrays[0])[: sample.bank.count]
    return Reader(
        values, times, sample.bank.frames, *region, reverse, loop, pitch, advance
    )


def compare(actual, expected):
    errors = [abs(a - b) for a, b in zip(actual, expected, strict=True)]
    maximum = max(errors, default=0)
    rms = math.sqrt(sum(e * e for e in errors) / max(1, len(errors)))
    require(maximum <= 1e-4 and rms <= 1e-5, f"Oracle error max={maximum}, rms={rms}")
    require(
        all(math.isfinite(v) and abs(v) <= 1.00001 for v in actual),
        "Non-finite or unsafe peak",
    )
    return maximum, rms


def checks(lib):
    n = 2400
    rng = random.Random(1)
    signals = {
        "silence": [0.0] * n,
        "impulse": [0.0] * 300 + [0.8] + [0.0] * (n - 301),
        "sine": [0.8 * math.sin(2 * math.pi * 220 * i / 48000) for i in range(n)],
        "two-tone": [
            0.4
            * (
                math.sin(2 * math.pi * 220 * i / 48000)
                + math.sin(2 * math.pi * 331 * i / 48000)
            )
            for i in range(n)
        ],
        "noise": [rng.uniform(-0.8, 0.8) for _ in range(n)],
        "dense": [0.8 if i % 2 else -0.8 for i in range(n)],
    }
    matrix = list(
        itertools.product(
            (0, 1),
            (0, 1),
            (0.03125, 0.5, 1, 2, 32),
            (1 / 1024, 0.02125, 0.5, 1, 2, 16),
            ((0, n), (600, 1800), (1200, 2400)),
        )
    )
    worst_max = worst_rms = 0
    cases = 0
    retained = None
    for name, audio in signals.items():
        sample = capacity.Sample(lib, audio)
        for reverse, loop, pitch, advance, region in matrix:
            state = start(lib, sample, region, reverse, loop, pitch, advance)
            expected = model(sample, region, reverse, loop, pitch, advance).process(
                1024
            )
            actual = process(lib, state, 1024)
            try:
                maximum, rms = compare(actual, expected)
            except AssertionError as exc:
                raise AssertionError(
                    f"{name} {(reverse, loop, pitch, advance, region)}: {exc}"
                ) from exc
            worst_max, worst_rms = max(worst_max, maximum), max(worst_rms, rms)
            if name == "sine" and (reverse, loop, pitch, advance, region) == (
                0,
                0,
                1,
                1,
                (0, n),
            ):
                retained = actual
            sample.guards()
            cases += 1
        print(f"{name}: {len(matrix)} oracle cases passed", flush=True)
    require(retained is not None, "Missing negative-control signal")
    negative = 0
    negative_sample = capacity.Sample(lib, signals["sine"])
    wrong_pitch = model(negative_sample, (0, n), 0, 0, 0.5, 1).process(1024)
    for wrong in ([0.0] + retained[:-1], wrong_pitch):
        try:
            compare(retained, wrong)
        except AssertionError:
            negative += 1
    require(negative == 2, "Negative comparator accepted wrong output")
    sample = capacity.Sample(lib, signals["noise"])
    # Original forward reader compatibility, including noninteger rates.
    compatibility = 0
    for pitch, advance in itertools.product((0.5, 0.7, 1, 1.3, 2), repeat=2):
        state = start(lib, sample, (0, n), 0, 0, pitch, advance)
        old = capacity.State()
        lib.cap_attach(ct.byref(old), ct.byref(sample.bank))
        require(
            lib.cap_start(ct.byref(old), pitch, advance, 128) == 0,
            "Old reader rejected",
        )
        output = (ct.c_float * 2048)()
        lib.cap_process(ct.byref(old), output, 2048)
        require(
            process(lib, state, 2048) == list(output), "Original forward reader drift"
        )
        compatibility += 1
    # Every partition must retain identical musical state and PCM.
    partition = 0
    for reverse, loop in itertools.product((0, 1), repeat=2):
        baseline = start(lib, sample, (600, 1800), reverse, loop, 2, 0.02125)
        expected = process(lib, baseline, 4096)
        for size in (1, 7, 32, 127):
            state = start(lib, sample, (600, 1800), reverse, loop, 2, 0.02125)
            actual = []
            while len(actual) < 4096:
                actual.extend(process(lib, state, min(size, 4096 - len(actual))))
            require(
                actual == expected and bytes(state) == bytes(baseline),
                "Block partition drift",
            )
            partition += 1
    # Fractional wrap and tiny regions, including a slow timing cursor that
    # becomes negative relative to the normalized ideal position.
    wraps = 0
    negative_cursor = False
    for reverse, pitch, advance, length in itertools.product(
        (0, 1), (0.03125, 32), (0.03125, 64), (1, 7, 49, 127)
    ):
        state = start(lib, sample, (600, 600 + length), reverse, 1, pitch, advance)
        reference = model(sample, (600, 600 + length), reverse, 1, pitch, advance)
        for _ in range(8):
            compare(process(lib, state, 2048), reference.process(2048))
            require(
                0 <= state.core.ideal_w < length and state.core.position == 48,
                "Unbounded looping transport",
            )
            negative_cursor |= state.core.actual_w < 0
        wraps += 1
    require(negative_cursor, "Lagging loop cursor case not exercised")
    # Live updates keep cursors and splice state, while recomputing the exact end.
    updates = 0
    for reverse, loop in itertools.product((0, 1), repeat=2):
        state = start(lib, sample, (0, n), reverse, loop, 2, 0.02125)
        reference = model(sample, (0, n), reverse, loop, 2, 0.02125)
        for pitch, advance in ((2, 0.02125), (0.5, 0.5), (32, 2), (0.03125, 0.03125)):
            before = (
                state.core.ideal_w,
                state.core.ideal_f,
                state.core.actual_w,
                state.core.actual_f,
                state.core.phase,
                state.core.position,
            )
            require(
                lib.cap_stretch_update(ct.byref(state), pitch, advance) == 0,
                "Live update rejected",
            )
            after = (
                state.core.ideal_w,
                state.core.ideal_f,
                state.core.actual_w,
                state.core.actual_f,
                state.core.phase,
                state.core.position,
            )
            require(before == after, "Live update reset state")
            reference.update(pitch, advance)
            compare(process(lib, state, 1024), reference.process(1024))
            updates += 1
    # Full 12-second source with a 128-second output duration.
    large = capacity.Sample(lib, [0.0] * 576000)
    long = start(lib, large, (0, 576000), 0, 0, 1, 0.09375)
    require(long.core.duration == 6144000, "128-second exact duration failed")
    require(
        lib.cap_stretch_start(
            ct.byref(Stretch()),
            ct.byref(large.bank),
            0,
            576000,
            0,
            0,
            1,
            1 / 65536,
            128,
        )
        != 0,
        "Overlong finite playback accepted",
    )
    finite = start(lib, sample, (0, n), 1, 0, 1, 1.3)
    expected_duration = math.ceil(n * 2**24 / int(ct.c_float(1.3).value * 2**24))
    require(
        finite.core.duration == expected_duration, "Fractional exact duration failed"
    )
    process(lib, finite, expected_duration)
    require(
        not finite.core.active and process(lib, finite, 32) == [0.0] * 32,
        "Terminal silence failed",
    )
    # Invalid input and generation checks happen before reading bank arrays.
    rejects = 0
    for pitch, advance in (
        (float("nan"), 1),
        (float("inf"), 1),
        (1, float("nan")),
        (0, 1),
        (33, 1),
        (1, 0),
        (1, 65),
    ):
        state = Stretch()
        require(
            lib.cap_stretch_start(
                ct.byref(state), ct.byref(sample.bank), 0, n, 0, 1, pitch, advance, 128
            )
            != 0,
            "Invalid control accepted",
        )
        rejects += 1
    for region in ((-1, n), (0, 0), (1000, 999), (0, n + 1)):
        require(
            lib.cap_stretch_start(
                ct.byref(Stretch()), ct.byref(sample.bank), *region, 0, 0, 1, 1, 128
            )
            != 0,
            "Invalid region accepted",
        )
        rejects += 1
    state = start(lib, sample, (0, n), 0, 1, 1, 1)
    saved = sample.bank.value
    sample.bank.generation += 1
    sample.bank.value = ct.POINTER(ct.c_float)()
    require(
        process(lib, state, 32) == [0.0] * 32 and not state.core.active,
        "Stale bank read",
    )
    sample.bank.value = saved
    require(
        lib.cap_stretch_update(ct.byref(state), float("nan"), 1) != 0,
        "Nonfinite update accepted",
    )
    sample.guards()
    return {
        "status": "PASS",
        "oracle_cases": cases,
        "maximum_error": worst_max,
        "rms_error": worst_rms,
        "old_reader_exact_cases": compatibility,
        "partition_cases": partition,
        "loop_boundary_cases": wraps,
        "live_updates": updates,
        "invalid_rejections": rejects,
        "negative_controls_rejected": negative,
        "max_input_frames": 576000,
        "max_output_frames": 6144000,
        "hardware_verified": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        result = checks(build(args.out))
    except Exception as exc:
        (args.out / "report.json").write_text(
            json.dumps({"status": "FAIL", "error": str(exc)}, indent=2) + "\n"
        )
        raise
    (args.out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
