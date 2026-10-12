#!/usr/bin/env python3
"""Host PCM, transport continuity and safety for live STRETCH R3 controls."""

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

from capicola_live_reference import LiveReader

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "stretch", ROOT / "scripts/check-capicola-stretch.py"
)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class Live(ct.Structure):
    _fields_ = (
        [("current", base.Stretch), ("outgoing", base.Stretch)]
        + [(n, ct.c_int) for n in ("fade_left", "start", "end", "reverse", "loop")]
        + [("pitch", ct.c_float), ("advance", ct.c_float), ("pending", ct.c_int)]
    )


def build(out):
    base.capacity.ref.verify_sources()
    contract = ROOT / "machines/capicola/stretch-live-contract"
    lock = json.loads((contract / "source-equivalence.json").read_text())
    for path, digest in lock["integration_baseline_files"].items():
        if path.startswith("machines/"):
            base.require(
                hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest,
                "Baseline drift: " + path,
            )
    helper = out / "host.c"
    helper.write_text(
        f'#include "{ROOT / "machines/capicola/live.c"}"\nint cap_test_duration(int n,unsigned q){{return exact_duration(n,q);}}\n'
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
            str(out / "live.dylib"),
        ],
        check=True,
    )
    lib = base.capacity.bind_api(ct.CDLL(str(out / "live.dylib")))
    for name, args, result in [
        ("cap_live_init", [ct.POINTER(Live)], None),
        ("cap_live_stop", [ct.POINTER(Live)], None),
        (
            "cap_live_start",
            [
                ct.POINTER(Live),
                ct.POINTER(base.capacity.Bank),
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
        (
            "cap_live_update",
            [
                ct.POINTER(Live),
                ct.c_int,
                ct.c_int,
                ct.c_int,
                ct.c_int,
                ct.c_float,
                ct.c_float,
            ],
            ct.c_int,
        ),
        (
            "cap_live_process",
            [ct.POINTER(Live), ct.POINTER(ct.c_float), ct.c_int],
            None,
        ),
    ]:
        fn = getattr(lib, name)
        fn.argtypes = args
        fn.restype = result
    return lib


def start(lib, sample, reverse=0, loop=1, pitch=1, advance=1):
    s = Live()
    base.require(
        lib.cap_live_start(
            ct.byref(s),
            ct.byref(sample.bank),
            0,
            sample.bank.frames,
            reverse,
            loop,
            pitch,
            advance,
            128,
        )
        == 0,
        "Live start rejected",
    )
    return s


def process(lib, state, n):
    out = (ct.c_float * n)()
    lib.cap_live_process(ct.byref(state), out, n)
    return list(out)


def update(lib, state, region, reverse, loop, pitch, advance):
    return lib.cap_live_update(ct.byref(state), *region, reverse, loop, pitch, advance)


def run(out):
    lib = build(out)
    rows = []
    maximum = rms = 0.0
    rng = random.Random(1)
    signals = {
        "silence": [0.0] * 4096,
        "impulse": [0.8 if i == 1500 else 0.0 for i in range(4096)],
        "tone": [0.6 * math.sin(i * 0.08) for i in range(4096)],
        "noise": [rng.uniform(-0.5, 0.5) for _ in range(4096)],
    }
    for name, data in signals.items():
        sample = base.capacity.Sample(lib, data)
        for before, after, region, rates in itertools.product(
            range(4),
            range(4),
            ((0, 4096), (512, 3000), (1800, 2000)),
            ((0.5, 0.125), (2, 0.5), (32, 16)),
        ):
            reverse, loop = before < 2, before in (1, 2)
            state = start(lib, sample, int(reverse), int(loop), *rates)
            model = LiveReader(
                base.model(sample, (0, 4096), int(reverse), int(loop), *rates)
            )
            base.compare(process(lib, state, 128), model.process(128))
            reverse, loop = int(after < 2), int(after in (1, 2))
            base.require(
                update(lib, state, region, reverse, loop, *rates) == 0,
                "Live control rejected",
            )
            model.update(*region, reverse, loop, *rates)
            actual = process(lib, state, 256)
            expected = model.process(256)
            m, e = base.compare(actual, expected)
            maximum = max(maximum, m)
            rms = max(rms, e)
            rows.append(
                dict(
                    signal=name,
                    before=before,
                    after=after,
                    region=region,
                    rates=rates,
                    maximum_error=m,
                    rms_error=e,
                )
            )
        sample.guards()
    sample = base.capacity.Sample(lib, signals["tone"])
    # Changing no region/mode must preserve the exact old reader samples.
    for reverse, loop in itertools.product((0, 1), repeat=2):
        live = start(lib, sample, reverse, loop)
        old = base.model(sample, (0, 4096), reverse, loop, 1, 1)
        base.compare(process(lib, live, 1024), old.process(1024))
        # Two independently initialized C wrappers are bit exact under partition.
        a = start(lib, sample, reverse, loop)
        b = start(lib, sample, reverse, loop)
        process(lib, a, 128)
        process(lib, b, 128)
        update(lib, a, (512, 3000), 1 - reverse, 1, 2, 0.5)
        update(lib, b, (512, 3000), 1 - reverse, 1, 2, 0.5)
        full = process(lib, a, 256)
        parts = []
        for n in (1, 7, 32, 127, 89):
            parts.extend(process(lib, b, n))
        base.require(full == parts, "Live block partition changed PCM")
    # Latest-only queue exercised at intervals below a full transition.
    for interval in (7, 32):
        state = start(lib, sample)
        model = LiveReader(base.model(sample, (0, 4096), 0, 1, 1, 1))
        for i in range(64):
            region = ((0, 4096), (400, 2000), (800, 900))[i % 3]
            reverse, loop = i % 2, 1
            update(lib, state, region, reverse, loop, 2, 0.5)
            model.update(*region, reverse, loop, 2, 0.5)
            base.compare(process(lib, state, interval), model.process(interval))
    # Latched-control comparator must falsify the central live behavior claim.
    state = start(lib, sample)
    old = base.model(sample, (0, 4096), 0, 1, 1, 1)
    process(lib, state, 128)
    old.process(128)
    update(lib, state, (1800, 2400), 1, 1, 1, 1)
    wrong = max(
        abs(a - b)
        for a, b in zip(process(lib, state, 256), old.process(256), strict=True)
    )
    base.require(wrong > 0.005, "Latched negative comparator did not fail")
    # Finite completion must stay stopped despite later valid mode/trim changes.
    state = start(lib, sample, 0, 0, 1, 32)
    process(lib, state, 256)
    base.require(not state.current.core.active, "Finite note did not finish")
    update(lib, state, (0, 4096), 1, 1, 1, 1)
    base.require(process(lib, state, 32) == [0.0] * 32, "Completed note resurrected")
    invalid = 0
    for region, reverse, loop, p, a in [
        ((-1, 100), 0, 1, 1, 1),
        ((0, 0), 0, 1, 1, 1),
        ((0, 5000), 0, 1, 1, 1),
        ((0, 4096), 2, 1, 1, 1),
        ((0, 4096), 0, 2, 1, 1),
        ((0, 4096), 0, 1, float("nan"), 1),
        ((0, 4096), 0, 1, 1, float("inf")),
    ]:
        state = start(lib, sample)
        base.require(
            update(lib, state, region, reverse, loop, p, a) != 0,
            "Invalid live controls accepted",
        )
        base.require(
            process(lib, state, 32) == [0.0] * 32, "Invalid live state not silent"
        )
        invalid += 1
    state = start(lib, sample)
    update(lib, state, (512, 3000), 1, 1, 1, 1)
    sample.bank.generation += 1
    base.require(
        process(lib, state, 32) == [0.0] * 32 and not state.fade_left,
        "Retired fade read old bank",
    )
    (out / "cases.json").write_text(json.dumps(rows, indent=2) + "\n")
    report = dict(
        status="passed",
        cases=len(rows),
        maximum_error=maximum,
        rms_error=rms,
        rapid_intervals=[7, 32],
        partition_exact=True,
        latched_negative_maximum=wrong,
        invalid_rejections=invalid,
        hardware_verified=False,
    )
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    out = args.output.resolve()
    base.require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
    out.mkdir(parents=True, exist_ok=False)
    print(json.dumps(run(out), indent=2))
