#!/usr/bin/env python3
"""Independent original-Granule comparison and quality-profile host safety."""

# ruff: noqa: E402
import argparse
import ctypes as ct
import importlib.util
import itertools
import math
import os
import struct
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import require, settings, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
from lab.capicola_quality import prepare


def helpers():
    spec = importlib.util.spec_from_file_location(
        "quality_base", ROOT / "scripts/check-capicola-stretch-live.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(out):
    h = helpers()
    h.base.capacity.ref.verify_sources()
    overlay = prepare(out / "quality-source")
    libs = {}
    for label, base in [("quality", overlay), ("old", ROOT)]:
        obj = out / f"{label}.o"
        dylib = out / f"{label}.dylib"
        subprocess.run(
            [
                "clang",
                "-std=c99",
                "-O2",
                "-ffp-contract=off",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-c",
                str(base / "machines/capicola/live.c"),
                "-o",
                str(obj),
            ],
            check=True,
        )
        subprocess.run(
            [
                "clang++",
                "-std=c++17",
                "-O2",
                "-ffp-contract=off",
                "-shared",
                "-I" + str(ROOT / ".local/sources/capicola/lib"),
                "-I" + str(ROOT / "machines/capicola"),
                str(ROOT / "machines/capicola/quality-oracle.cc"),
                str(obj),
                "-o",
                str(dylib),
            ],
            check=True,
        )
        lib = ct.CDLL(str(dylib))
        ptr = ct.POINTER(ct.c_float)
        lib.audit.argtypes = [
            ptr,
            ct.c_int,
            ct.c_int,
            ct.c_int,
            ct.c_float,
            ct.c_float,
            ptr,
            ptr,
            ptr,
            ptr,
            ptr,
        ]
        lib.audit.restype = ct.c_int
        for name, args, result in [
            ("cap_bank_init", [ct.POINTER(h.base.capacity.Bank)], None),
            (
                "cap_bank_bind",
                [
                    ct.POINTER(h.base.capacity.Bank),
                    ptr,
                    ct.POINTER(ct.c_int),
                    ct.POINTER(ct.c_uint),
                    ct.c_int,
                ],
                ct.c_int,
            ),
            ("cap_measure", [ptr, ct.c_int], ct.c_int),
            ("cap_load", [ct.POINTER(h.base.capacity.Bank), ptr, ct.c_int], ct.c_int),
            (
                "cap_stretch_start",
                [
                    ct.POINTER(h.base.Stretch),
                    ct.POINTER(h.base.capacity.Bank),
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
                "cap_stretch_update",
                [ct.POINTER(h.base.Stretch), ct.c_float, ct.c_float],
                ct.c_int,
            ),
            ("cap_stretch_process", [ct.POINTER(h.base.Stretch), ptr, ct.c_int], None),
            ("cap_stretch_stop", [ct.POINTER(h.base.Stretch)], None),
            ("cap_live_init", [ct.POINTER(h.Live)], None),
            (
                "cap_live_start",
                [
                    ct.POINTER(h.Live),
                    ct.POINTER(h.base.capacity.Bank),
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
                    ct.POINTER(h.Live),
                    ct.c_int,
                    ct.c_int,
                    ct.c_int,
                    ct.c_int,
                    ct.c_float,
                    ct.c_float,
                ],
                ct.c_int,
            ),
            ("cap_live_process", [ct.POINTER(h.Live), ptr, ct.c_int], None),
            ("cap_live_stop", [ct.POINTER(h.Live)], None),
        ]:
            f = getattr(lib, name)
            f.argtypes = args
            f.restype = result
        libs[label] = lib
    return h, libs


def signal(kind, n):
    data = (ct.c_float * n)()
    for i in range(n):
        t = i / 48000
        value = 0.5 * math.sin(2 * math.pi * (55 if kind == "bass" else 220) * t)
        if kind == "chord":
            value = 0.2 * sum(
                math.sin(2 * math.pi * 110 * r * t) for r in [1, 1.25992105, 1.49830708]
            )
        if kind == "silence":
            value = 0
        data[i] = int(value * 32767) / 32768
    return data


def sample(h, lib, data):
    n = lib.cap_measure(data, len(data))
    require(n >= 2, "Key count")
    arrays = ((ct.c_float * n)(), (ct.c_int * n)(), (ct.c_uint * n)())
    bank = h.base.capacity.Bank()
    lib.cap_bank_init(ct.byref(bank))
    require(lib.cap_bank_bind(ct.byref(bank), *arrays, n) == 0, "Bank bind")
    require(lib.cap_load(ct.byref(bank), data, len(data)) == 0, "Analysis")
    return bank, arrays


def error(a, b):
    errors = [abs(x - y) for x, y in zip(a, b, strict=True)]
    return max(errors), math.sqrt(sum(e * e for e in errors) / len(errors))


def wav(path, pcm):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(48000)
        f.writeframes(
            b"".join(
                struct.pack("<h", max(-32768, min(32767, round(v * 32767))))
                for v in pcm
            )
        )


def interior(out, libs):
    rows = []
    for kind in ["bass", "tone", "chord"]:
        data = signal(kind, 576000)
        for pitch in [0.5, 1, 2]:
            name = f"{kind}-pitch{pitch}"
            cases = {}
            for label, lib in libs.items():
                original, actual, ue, pe = [(ct.c_float * 144000)() for _ in range(4)]
                stats = (ct.c_float * 3)()
                require(
                    lib.audit(
                        data,
                        len(data),
                        96000,
                        144000,
                        pitch,
                        0.425,
                        original,
                        actual,
                        ue,
                        pe,
                        stats,
                    )
                    == 0,
                    "Original audit",
                )
                require(
                    stats[0] == stats[1] and stats[2] == 0,
                    "Key mismatch or original boundary rescue",
                )
                maximum, rms = error(original, actual)
                cases[label] = dict(
                    maximum_error=maximum,
                    rms_error=rms,
                    original_events=[(i, ue[i]) for i in range(len(ue)) if ue[i]],
                    candidate_events=[(i, pe[i]) for i in range(len(pe)) if pe[i]],
                )
                if label == "quality":
                    require(
                        maximum <= 1e-4 and rms <= 1e-5,
                        f"{name} original Granule max={maximum} rms={rms}",
                    )
                    wav(out / f"{name}-upstream.wav", original)
                    wav(out / f"{name}-quality.wav", actual)
                else:
                    wav(out / f"{name}-old.wav", actual)
            if cases["quality"]["original_events"]:
                require(
                    cases["old"]["maximum_error"] > 1e-4, "Capped negative did not fail"
                )
            rows.append(dict(name=name, **cases))
            print(name, cases["quality"]["maximum_error"], flush=True)
    return rows


def safety(h, lib):
    rows = 0
    progress = 0
    for kind in ["tone", "silence"]:
        data = signal(kind, 2400)
        bank, arrays = sample(h, lib, data)
        for pitch, advance, reverse, loop, (start, end) in itertools.product(
            [1 / 32, 0.5, 1, 2, 32],
            [1 / 65536, 0.425, 1, 16, 64],
            [0, 1],
            [0, 1],
            [(0, 2400), (600, 1800), (1200, 1341)],
        ):
            states = []
            outputs = []
            for block in [1, 7, 32, 127]:
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
                if status != 0:
                    require(
                        not loop and math.ceil((end - start) / advance) > 6144000,
                        "Unexpected refused control",
                    )
                    break
                result = []
                for i in range(0, 1024, block):
                    n = min(block, 1024 - i)
                    buf = (ct.c_float * (n + 2))()
                    buf[0] = buf[-1] = 123
                    lib.cap_stretch_process(
                        ct.byref(state),
                        ct.cast(ct.byref(buf, 4), ct.POINTER(ct.c_float)),
                        n,
                    )
                    require(buf[0] == buf[-1] == 123, "Output overrun")
                    result.extend(buf[1:-1])
                require(
                    all(math.isfinite(v) and abs(v) <= 0.501 for v in result),
                    "Signal safety",
                )
                states.append(bytes(state))
                outputs.append(result)
                lib.cap_stretch_stop(ct.byref(state))
                buf = (ct.c_float * 32)()
                lib.cap_stretch_process(ct.byref(state), buf, 32)
                require(not any(buf), "Stop silence")
            if outputs:
                require(all(x == outputs[0] for x in outputs), "Block partition drift")
                require(all(x == states[0] for x in states), "Partition state drift")
            rows += 1
        # Every valid slow/extreme rate must advance a long fade near phase1.
        for pitch in [1 / 32, 0.5, 1, 2, 32]:
            s = h.base.Stretch()
            require(
                lib.cap_stretch_start(
                    ct.byref(s), ct.byref(bank), 0, 2400, 0, 1, pitch, 1 / 65536, 128
                )
                == 0,
                "Progress start",
            )
            s.core.splicing = 1
            s.core.increment = 1 / 1_000_000_000
            s.core.phase = ct.c_float(1 - 2**-23).value
            buf = (ct.c_float * 4)()
            lib.cap_stretch_process(ct.byref(s), buf, 4)
            require(not s.core.splicing, "Long fade stalled at phase1")
            progress += 1
        s = h.base.Stretch()
        require(
            lib.cap_stretch_start(
                ct.byref(s), ct.byref(bank), 0, 2400, 0, 1, 1, 0.425, 128
            )
            == 0,
            "Generation start",
        )
        bank.generation += 1
        buf = (ct.c_float * 32)()
        lib.cap_stretch_process(ct.byref(s), buf, 32)
        require(not any(buf) and not s.core.active, "Invalidation failed")
        for bad in [float("nan"), float("inf"), -1, 0]:
            require(
                lib.cap_stretch_start(
                    ct.byref(s), ct.byref(bank), 0, 2400, 0, 1, bad, 1, 128
                )
                != 0,
                "Bad pitch accepted",
            )
        # Exercise live transition and pending edits without changing the wrapper.
        live = h.Live()
        require(
            lib.cap_live_start(
                ct.byref(live), ct.byref(bank), 0, 2400, 0, 1, 1, 0.425, 128
            )
            == 0,
            "Live start",
        )
        for i in range(12):
            require(
                lib.cap_live_update(
                    ct.byref(live),
                    i * 8,
                    2400 - i * 8,
                    i % 2,
                    1,
                    1 + (i % 3) * 0.5,
                    0.425,
                )
                == 0,
                "Live update",
            )
            lib.cap_live_process(ct.byref(live), buf, 32)
            require(
                all(math.isfinite(v) and abs(v) <= 0.501 for v in buf), "Live safety"
            )
        lib.cap_live_stop(ct.byref(live))
        lib.cap_live_process(ct.byref(live), buf, 32)
        require(not any(buf), "Live stop")
    return dict(
        cases=rows,
        phase_progress_cases=progress,
        partition_sizes=[1, 7, 32, 127],
        generation_stop=True,
        live_transitions=True,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    require(out.is_relative_to(ROOT / "out/runs"), "Use fresh ignored run")
    out.mkdir(parents=True, exist_ok=False)
    sources = source_hashes()
    report = dict(
        status="running",
        source_hashes=sources,
        scope="Original upstream Granule and host safety; no subjective or physical claim",
    )
    try:
        h, libs = build(out)
        report["interior"] = interior(out, libs)
        report["safety"] = safety(h, libs["quality"])
        require(source_hashes() == sources, "Source drift")
        report["status"] = "passed"
    except BaseException as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        write_json(out / "report.json", report)
    print("passed", out)


if __name__ == "__main__":
    main()
