#!/usr/bin/env python3
"""Complete-start Capicola source oracle, transport and grain handoff checks."""

# ruff: noqa: E402
import argparse
import ctypes as ct
import importlib.util
import itertools
import math
import os
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from lab.project import require, settings, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
from lab.capicola_source import prepare


def build(out):
    spec = importlib.util.spec_from_file_location(
        "quality_source_helpers", ROOT / "scripts/check-capicola-quality.py"
    )
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    q.prepare = prepare
    h, libs = q.build(out)
    subprocess.run(
        [
            "clang++",
            "-std=c++17",
            "-O2",
            "-ffp-contract=off",
            "-shared",
            "-I" + str(ROOT / ".local/sources/capicola/lib"),
            "-I" + str(ROOT / "machines/capicola"),
            str(ROOT / "machines/capicola/source-oracle.cc"),
            str(out / "quality.o"),
            "-o",
            str(out / "source-oracle.dylib"),
        ],
        check=True,
    )
    lib = libs["quality"]
    ref = ct.CDLL(str(out / "source-oracle.dylib"))
    ptr = ct.POINTER(ct.c_float)
    ref.source_audit.argtypes = [
        ptr,
        *([ct.c_int] * 5),
        ct.c_float,
        ct.c_float,
        ct.c_int,
        ptr,
        ptr,
        ptr,
        ptr,
    ]
    ref.source_audit.restype = ct.c_int
    ref.source_pair_audit.argtypes = [ptr, ct.c_int, ct.c_int, ptr, ptr]
    ref.source_pair_audit.restype = ct.c_int
    lib.cap_live_retrigger.argtypes = lib.cap_live_start.argtypes
    lib.cap_live_retrigger.restype = ct.c_int
    return q, h, lib, libs["old"], ref


def signal(kind, n):
    data = (ct.c_float * n)()
    rng = random.Random(619)
    lp = 0.0
    for i in range(n):
        t = i / 48000
        if kind == "silence":
            v = 0
        elif kind == "impulse":
            v = 0.7 if i == n // 2 else 0
        elif kind == "noise":
            lp = 0.4 * lp + 0.6 * rng.uniform(-1, 1)
            v = 0.5 * lp
        elif kind == "percussion":
            lp = 0.4 * lp + 0.6 * rng.uniform(-1, 1)
            v = (0.5 * lp + 0.4 * math.sin(2 * math.pi * 73 * t)) * math.exp(
                -(t % 0.125) * 35
            )
        elif kind == "chord":
            v = 0.2 * sum(
                math.sin(2 * math.pi * 110 * r * t) for r in [1, 1.25992105, 1.49830708]
            )
        elif kind == "complex":
            v = 0.15 * sum(
                math.sin(2 * math.pi * (419 + 137 * j + 0.371 * j * j) * t) / (j + 2)
                for j in range(12)
            )
        else:
            v = 0.5 * math.sin(2 * math.pi * (55 if kind == "bass" else 220) * t)
        data[i] = int(max(-0.999, min(0.999, v)) * 32767) / 32768
    return data


def source_cases(q, h, lib, old, ref, out):
    rows = []
    for kind, pitch, advance, reverse, loop, trim in itertools.product(
        ["tone", "chord", "noise", "percussion", "complex", "silence", "impulse"],
        [0.5, 1.0, 2.0],
        [0.425, 1.0, 2.0],
        [0, 1],
        [0, 1],
        [False, True],
    ):
        data = signal(kind, 4096)
        n = 8192
        start, end = (1024, 3072) if trim else (0, 4096)
        up, port, event = [(ct.c_float * n)() for _ in range(3)]
        stats = (ct.c_float * 7)()
        code = ref.source_audit(
            data,
            len(data),
            start,
            end,
            reverse,
            loop,
            pitch,
            advance,
            n,
            up,
            port,
            event,
            stats,
        )
        require(code == 0, f"Original source fixture failed: {code}")
        require(
            stats[0] == stats[1]
            and stats[2] == 0
            and stats[3] < 1e-6
            and stats[4] <= 6e-8,
            "Analyzer/guard mismatch",
        )
        maximum, rms = q.error(up, port)
        require(
            maximum <= 1e-4 and rms <= 1e-5,
            f"Source PCM mismatch: {kind, pitch, reverse, loop, trim, maximum, rms}",
        )
        again = (ct.c_float * n)()
        bank, arrays = q.sample(h, lib, data)
        s = h.base.Stretch()
        require(
            lib.cap_stretch_start(
                ct.byref(s),
                ct.byref(bank),
                start,
                end,
                reverse,
                loop,
                pitch,
                advance,
                128,
            )
            == 0,
            "Start",
        )
        at = 0
        for block in itertools.cycle([1, 7, 32, 127]):
            count = min(block, n - at)
            lib.cap_stretch_process(
                ct.byref(s),
                ct.cast(ct.byref(again, at * 4), ct.POINTER(ct.c_float)),
                count,
            )
            at += count
            if at == n:
                break
        require(bytes(again) == bytes(port), "Partition/repeat mismatch")
        require(
            all(math.isfinite(x) and abs(x) <= 1.001 for x in port), "Signal safety"
        )
        row = dict(
            kind=kind,
            pitch=pitch,
            advance=advance,
            reverse=reverse,
            loop=loop,
            trim=trim,
            maximum_error=maximum,
            rms_error=rms,
            splices=sum(v > 0 for v in event),
        )
        rows.append(row)
        if (
            not reverse
            and loop
            and not trim
            and pitch in [1, 2]
            and advance == 0.425
            and kind in ["chord", "percussion", "noise"]
        ):
            name = f"{kind}-pitch{pitch}"
            q.wav(out / f"{name}-source.wav", port)
            q.wav(out / f"{name}-original.wav", up)
            b, storage = q.sample(h, old, data)
            state = h.base.Stretch()
            old.cap_stretch_start(
                ct.byref(state),
                ct.byref(b),
                start,
                end,
                reverse,
                loop,
                pitch,
                advance,
                128,
            )
            neg = (ct.c_float * n)()
            old.cap_stretch_process(ct.byref(state), neg, n)
            q.wav(out / f"{name}-legacy.wav", neg)
            row["legacy_max_difference"] = q.error(port, neg)[0]
    require(
        any(row.get("legacy_max_difference", 0) > 0.001 for row in rows),
        "Legacy negative failed to distinguish former playback policy",
    )
    return rows


def lifecycle(q, h, lib):
    data = signal("complex", 8192)
    bank, arrays = q.sample(h, lib, data)
    rows = []
    for reverse, loop, pitch, advance in itertools.product(
        [0, 1], [0, 1], [0.03125, 32], [0.0009765625, 16]
    ):
        s = h.base.Stretch()
        require(
            lib.cap_stretch_start(
                ct.byref(s),
                ct.byref(bank),
                600,
                2400,
                reverse,
                loop,
                pitch,
                advance,
                128,
            )
            == 0,
            "Extreme start",
        )
        buf = (ct.c_float * 4096)()
        lib.cap_stretch_process(ct.byref(s), buf, len(buf))
        require(
            all(math.isfinite(x) and abs(x) <= 1.001 for x in buf), "Extreme safety"
        )
        rows.append(dict(reverse=reverse, loop=loop, pitch=pitch, advance=advance))
    live = h.Live()
    require(
        lib.cap_live_start(ct.byref(live), ct.byref(bank), 0, 8192, 0, 1, 1, 0.425, 128)
        == 0,
        "Live start",
    )
    buf = (ct.c_float * 1024)()
    lib.cap_live_process(ct.byref(live), buf, 512)
    require(
        lib.cap_live_update(ct.byref(live), 1024, 7168, 1, 1, 2, 0.5) == 0, "Transition"
    )
    require(
        live.fade_left == 960
        and live.outgoing.core.pitch == 1
        and live.current.core.pitch == 2,
        "Original outgoing rates/fade",
    )
    lib.cap_live_process(ct.byref(live), buf, 32)
    require(
        lib.cap_live_update(ct.byref(live), 600, 7400, 0, 1, 0.5, 1) == 0, "Queued edit"
    )
    require(
        live.pending and live.fade_left == 928 and live.outgoing.core.pitch == 1,
        "Audible outgoing grain overwritten",
    )
    lib.cap_live_process(ct.byref(live), buf, 928)
    require(live.fade_left == 0, "Handoff duration")
    lib.cap_live_process(ct.byref(live), buf, 1)
    require(
        live.fade_left == 959 and live.current.start == 600,
        "Queued geometry not applied",
    )
    require(
        lib.cap_live_retrigger(ct.byref(live), ct.byref(bank), 0, 8192, 0, 1, 1, 1, 128)
        == 0
        and live.fade_left == 960,
        "Retrigger handoff",
    )
    require(
        lib.cap_live_update(ct.byref(live), 0, 8192, 0, 1, float("nan"), 1) != 0,
        "NaN accepted",
    )
    lib.cap_live_process(ct.byref(live), buf, 1024)
    require(not any(buf), "Invalid control did not silence")
    lib.cap_live_start(ct.byref(live), ct.byref(bank), 0, 8192, 0, 1, 1, 1, 128)
    bank.generation += 1
    lib.cap_live_process(ct.byref(live), buf, 1024)
    require(not any(buf), "Generation did not silence")
    return dict(
        extremes=rows,
        source_handoff_samples=960,
        outgoing_rates_preserved=True,
        queued_geometry=True,
        retrigger=True,
        invalid_generation_silence=True,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    require(out.is_relative_to(ROOT / "out/runs"), "Use ignored output")
    out.mkdir(parents=True, exist_ok=False)
    frozen = source_hashes()
    report = dict(
        status="running",
        source_hashes=frozen,
        scope="Host complete-start periodic source adapter; unmodified original Analyzer/SparseLine/Granule; not physical/listening",
    )
    try:
        q, h, lib, old, ref = build(out)
        report["cases"] = source_cases(q, h, lib, old, ref, out)
        report["lifecycle"] = lifecycle(q, h, lib)
        data = signal("noise", 4096)
        original, actual = [(ct.c_float * 4096)() for _ in range(2)]
        require(
            ref.source_pair_audit(data, len(data), len(actual), original, actual) == 0,
            "Original KeyframeRecorder pair fixture",
        )
        maximum, rms = q.error(original, actual)
        require(
            maximum <= 1e-4 and rms <= 1e-5,
            f"Original ReadPair handoff mismatch: {maximum, rms}",
        )
        report["original_pair"] = dict(
            maximum_error=maximum,
            rms_error=rms,
            source="Unmodified KeyframeRecorder::Punch/ReadPair; immutable-host Spawn placement",
        )
        # Three-second equal-gain audition against the preceding quality port.
        from lab.capicola_quality import prepare as prepare_quality

        previous = prepare_quality(out / "previous-quality-source")
        subprocess.run(
            [
                "clang",
                "-std=c99",
                "-O2",
                "-ffp-contract=off",
                "-shared",
                str(previous / "machines/capicola/live.c"),
                "-o",
                str(out / "previous-quality.dylib"),
            ],
            check=True,
        )
        prior = ct.CDLL(str(out / "previous-quality.dylib"))
        for name in (
            "cap_bank_init",
            "cap_bank_bind",
            "cap_measure",
            "cap_load",
            "cap_stretch_start",
            "cap_stretch_process",
        ):
            getattr(prior, name).argtypes = getattr(old, name).argtypes
            getattr(prior, name).restype = getattr(old, name).restype
        report["audition"] = []
        for kind in ("chord", "percussion"):
            data = signal(kind, 48000)
            n = 144000
            original, actual, events = [(ct.c_float * n)() for _ in range(3)]
            stats = (ct.c_float * 7)()
            require(
                ref.source_audit(
                    data,
                    len(data),
                    0,
                    len(data),
                    0,
                    1,
                    2,
                    0.425,
                    n,
                    original,
                    actual,
                    events,
                    stats,
                )
                == 0
                and stats[2] == 0,
                "Audition original source fixture",
            )
            maximum, rms = q.error(original, actual)
            require(maximum <= 1e-4 and rms <= 1e-5, "Audition source parity")
            bank, arrays = q.sample(h, prior, data)
            state = h.base.Stretch()
            prior.cap_stretch_start(
                ct.byref(state), ct.byref(bank), 0, len(data), 0, 1, 2, 0.425, 128
            )
            former = (ct.c_float * n)()
            prior.cap_stretch_process(ct.byref(state), former, n)
            for label, pcm in (
                ("original", original),
                ("source", actual),
                ("previous-quality", former),
            ):
                q.wav(out / f"audition-{kind}-{label}.wav", pcm)
            report["audition"].append(
                dict(
                    kind=kind,
                    frames=n,
                    original_maximum_error=maximum,
                    original_rms_error=rms,
                    previous_quality_maximum_difference=q.error(actual, former)[0],
                    normalization="none; identical gain",
                )
            )
        require(source_hashes() == frozen, "Source drift")
        report["status"] = "passed"
        print(
            f"PASS {len(report['cases'])} complete-start source comparisons and lifecycle"
        )
    except BaseException as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        write_json(out / "report.json", report)


if __name__ == "__main__":
    main()
