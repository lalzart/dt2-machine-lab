#!/usr/bin/env python3
"""Build and compare the finite Capicola experiment with original-header C++."""

import argparse
import array
import ctypes as ct
import hashlib
import itertools
import json
import math
import struct
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "machines/capicola"
BUNDLE = MACHINE / "contract"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def verify_sources():
    source = ROOT / ".local/sources/capicola"
    lock = json.loads((BUNDLE / "source-equivalence.json").read_text())
    actual = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    require(actual == lock["source_authority"]["revision"], "Capicola revision drift")
    require(
        not subprocess.check_output(
            ["git", "-C", str(source), "status", "--porcelain"], text=True
        ).strip(),
        "Dirty Capicola reference",
    )
    for item in lock["files"]:
        require(
            sha(source / item["path"]) == item["sha256"],
            f"Reference drift: {item['path']}",
        )
    proposal = json.loads((BUNDLE / "implementation-contract.json").read_text())[
        "proposal"
    ]
    require(sha(ROOT / proposal["path"]) == proposal["sha256"], "Proposal drift")
    return source, lock


def fingerprint():
    paths = list(MACHINE.rglob("*")) + [
        Path(__file__),
        ROOT / "docs/CAPICOLA-PROTOTYPE.md",
    ]
    return {str(p.relative_to(ROOT)): sha(p) for p in paths if p.is_file()}


class Engine:
    def __init__(self, lib, prefix):
        self.lib, self.prefix = lib, prefix
        self.methods = {}
        signatures = {
            "load": ([ct.c_void_p, ct.POINTER(ct.c_float), ct.c_int], ct.c_int),
            "start": ([ct.c_void_p, ct.c_float, ct.c_float, ct.c_int], ct.c_int),
            "process": ([ct.c_void_p, ct.POINTER(ct.c_float), ct.c_int], None),
            "stop": ([ct.c_void_p], None),
            "count": ([ct.c_void_p], ct.c_int),
            "value": ([ct.c_void_p, ct.c_int], ct.c_float),
            "time": ([ct.c_void_p, ct.c_int], ct.c_double),
            "position": ([ct.c_void_p], ct.c_int),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(lib, prefix + "_" + name)
            fn.argtypes, fn.restype = args, result
            self.methods[name] = fn
        if prefix == "cap":
            lib.cap_state_size.restype = ct.c_int
            self.state = ct.create_string_buffer(lib.cap_state_size())
            lib.cap_init.argtypes = [ct.c_void_p]
            lib.cap_init(self.state)
        else:
            lib.oracle_new.restype = ct.c_void_p
            self.state = lib.oracle_new()
            lib.oracle_delete.argtypes = [ct.c_void_p]

    def call(self, name, *args):
        return self.methods[name](self.state, *args)

    def load(self, samples):
        data = (ct.c_float * len(samples))(*samples)
        return self.call("load", data, len(samples))

    def render(self, count, block=64):
        result = bytearray()
        for at in range(0, count, block):
            n = min(block, count - at)
            out = (ct.c_float * n)()
            self.call("process", out, n)
            result.extend(bytes(out))
        return bytes(result)

    def keys(self):
        return b"".join(
            struct.pack("<fd", self.call("value", i), self.call("time", i))
            for i in range(self.call("count"))
        )

    def close(self):
        if self.prefix == "oracle" and self.state:
            self.lib.oracle_delete(self.state)
            self.state = None


def generate(name, n, seed):
    r = seed
    values = []
    for i in range(n):
        t = i / 48000
        if name == "silence":
            x = 0
        elif name == "impulse":
            x = 0.75 if i == 4800 else 0
        elif name == "sine":
            x = 0.5 * math.sin(2 * math.pi * 220 * t)
        elif name == "two-tone":
            x = 0.25 * (
                math.sin(2 * math.pi * 220 * t) + math.sin(2 * math.pi * 331 * t)
            )
        elif name == "noise":
            r ^= (r << 13) & 0xFFFFFFFF
            r ^= r >> 17
            r ^= (r << 5) & 0xFFFFFFFF
            x = 0.5 * ((r >> 8) / 8388608 - 1)
        elif name == "drums":
            t = (i % 12000) / 48000
            x = 0.7 * math.sin(2 * math.pi * 60 * t) * math.exp(-30 * t)
        else:
            raise ValueError(name)
        values.append(x)
    return array.array("f", values)


def save_wav(path, pcm):
    vals = array.array("f")
    vals.frombytes(pcm)
    with wave.open(str(path), "wb") as w:
        w.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        w.writeframes(
            b"".join(struct.pack("<h", round(max(-1, min(1, x)) * 32767)) for x in vals)
        )


def pitch_estimate(pcm, splice):
    vals = array.array("f")
    vals.frombytes(pcm)
    # Median single-cycle intervals rejects occasional splice-displaced crossings.
    edges = [
        i - vals[i] / (vals[i + 1] - vals[i])
        for i in range(4800, len(vals) - 4801)
        if vals[i] <= 0 < vals[i + 1]
    ]
    periods = sorted(
        b - a
        for a, b in zip(edges, edges[1:], strict=False)
        if not any(splice[math.floor(a) : math.ceil(b) + 1])
    )
    return 48000 / periods[len(periods) // 2] if periods else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.is_relative_to(ROOT / "out/runs"), "Use a unique output below out/runs")
    out.mkdir(parents=True, exist_ok=False)
    source, lock = verify_sources()
    frozen = fingerprint()
    experiment = json.loads((BUNDLE / "experiment.json").read_text())
    report = {
        "status": "running",
        "boundary": "Host mono source equivalence, not firmware, real-time or listening",
        "source_hashes": frozen,
        "source_lock": lock,
        "cases": [],
        "pitch_acceptance_failures": [],
    }
    engines = []
    try:
        flags = ["-O2", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror", "-shared"]
        commands = [
            [
                "clang",
                "-std=c99",
                *flags,
                str(MACHINE / "core.c"),
                "-o",
                str(out / "candidate.dylib"),
            ],
            [
                "clang++",
                "-std=c++17",
                *flags,
                "-I" + str(source / "lib"),
                str(MACHINE / "oracle.cc"),
                "-o",
                str(out / "oracle.dylib"),
            ],
        ]
        for cmd in commands:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        report["build_commands"] = commands
        report["compiler"] = subprocess.check_output(["clang", "--version"], text=True)
        libs = [
            ct.CDLL(str(out / "candidate.dylib")),
            ct.CDLL(str(out / "oracle.dylib")),
        ]
        engines = [Engine(libs[0], "cap"), Engine(libs[1], "oracle")]
        a, b = engines
        for name in experiment["recipes"]:
            x = generate(name, experiment["input_frames"], experiment["seed"])
            statuses = [e.load(x) for e in engines]
            require(statuses[0] == statuses[1], f"{name}: load status {statuses}")
            if name == "noise":
                require(
                    statuses == [2, 2], "Dense source must report capacity overflow"
                )
                require(a.render(128) == bytes(512), "Overflow must remain silent")
                report["cases"].append({"signal": name, "expected_overflow": True})
                continue
            require(statuses == [0, 0], f"{name}: unexpected overflow/error")
            require(a.keys() == b.keys(), f"{name}: analyzer mismatch")
            keys = a.keys()
            (out / f"{name}-keyframes.bin").write_bytes(keys)
            for pitch, advance, leash in itertools.product(
                experiment["pitches"], experiment["advances"], experiment["leashes"]
            ):
                duration = math.ceil(len(x) / advance)
                for e in engines:
                    require(e.call("start", pitch, advance, leash) == 0, "Start failed")
                aa, bb = [e.render(duration + 137) for e in engines]
                require(
                    aa == bb,
                    f"{name}: PCM mismatch p={pitch} a={advance} leash={leash}",
                )
                vals = array.array("f")
                vals.frombytes(aa)
                peak = max(map(abs, vals))
                require(all(map(math.isfinite, vals)), "Nonfinite output")
                require(
                    peak <= max(map(abs, x)) + experiment["tolerances"]["peak_slack"],
                    "Gain excursion",
                )
                require(a.call("position") == duration, "Wrong terminal position")
                require(not any(vals[duration:]), "Nonzero tail")
                if name == "silence":
                    require(not any(vals), "Silence leaked")
                hz = None
                if name == "sine":
                    a.call("start", pitch, advance, leash)
                    trace_pcm = (ct.c_float * duration)()
                    trace_mask = (ct.c_int * duration)()
                    libs[0].cap_process_trace.argtypes = [
                        ct.c_void_p,
                        ct.POINTER(ct.c_float),
                        ct.POINTER(ct.c_int),
                        ct.c_int,
                    ]
                    libs[0].cap_process_trace(a.state, trace_pcm, trace_mask, duration)
                    require(bytes(trace_pcm) == aa[: duration * 4], "Trace changed PCM")
                    hz = pitch_estimate(bytes(trace_pcm), trace_mask)
                if (
                    hz is not None
                    and abs(hz - 220 * pitch) > experiment["tolerances"]["pitch_hz"]
                ):
                    report["pitch_acceptance_failures"].append(
                        {
                            "pitch": pitch,
                            "advance": advance,
                            "leash": leash,
                            "measured_hz": hz,
                            "reason": "no complete unspliced cycles"
                            if hz == 0
                            else "outside frozen 2 Hz tolerance",
                        }
                    )
                tag = f"case-{name}-p{pitch}-a{advance}-l{leash}"
                (out / (tag + ".f32")).write_bytes(aa)
                if leash == 128:
                    save_wav(out / (tag + ".wav"), aa[: duration * 4])
                require(a.call("start", pitch, advance, leash) == 0, "Reset failed")
                require(
                    a.render(duration + 137, 127) == aa, "Repeat/partition mismatch"
                )
                report["cases"].append(
                    {
                        "signal": name,
                        "pitch": pitch,
                        "advance": advance,
                        "leash": leash,
                        "keyframes": len(keys) // 12,
                        "frames": duration,
                        "peak": peak,
                        "hz": hz,
                        "sha256": hashlib.sha256(aa).hexdigest(),
                    }
                )
            print(f"{name}: analyzer exact; 18 PCM cases exact", flush=True)
        # Decimal controls exercise accumulation that binary-fraction cases miss.
        report["decimal_rate_cases"] = []
        for pitch, advance in [(1, 0.7), (0.7, 1), (1.1, 0.7)]:
            x = generate("sine", 48000, 1)
            for e in engines:
                require(e.load(x) == 0, "Decimal reload")
                require(e.call("start", pitch, advance, 128) == 0, "Decimal start")
            aa, bb = [e.render(96000, 127) for e in engines]
            require(aa == bb, "Decimal-rate oracle mismatch")
            report["decimal_rate_cases"].append(
                {"pitch": pitch, "advance": advance, "pcm_exact": True}
            )
        # State, parameter, edge, and independence checks.
        x = generate("sine", 48000, 1)
        for e in engines:
            require(e.load(x) == 0, "Reload failed")
            require(e.call("start", 1, 0.75, 128) == 0, "Fractional advance")
        aa, bb = [e.render(65000, 32) for e in engines]
        require(aa == bb and a.call("position") == 64000, "Fractional duration/output")
        require(a.call("start", 1, 0.75, 128) == 0, "Reset failed")
        require(a.render(65000, 1) == aa, "Single-frame partition mismatch")
        a.call("start", 1, 1, 128)
        a.render(101)
        pos = a.call("position")
        a.call("stop")
        require(
            a.render(500) == bytes(2000) and a.call("position") == pos,
            "Stop advances or leaks",
        )
        for control in [
            (float("nan"), 1, 128),
            (1, float("inf"), 128),
            (0, 1, 128),
            (1, 2.1, 128),
            (1, 1, 15),
        ]:
            require(a.call("start", *control) == 3, "Invalid control accepted")
            require(a.render(64) == bytes(256), "Invalid control not silent")
        for invalid in [[], [float("nan")], [float("inf")], [1.1], [0] * 48001]:
            require(a.load(invalid) == 1, "Invalid input accepted")
            require(
                a.call("start", 1, 1, 128) != 0 and a.render(64) == bytes(256),
                "Invalid load retained sample",
            )
        for n in [1, 2, 3, 31, 64, 127]:
            xx = array.array("f", [0.25] * n)
            require(a.load(xx) == b.load(xx) == 0, "Short input failed")
            require(a.keys() == b.keys(), "Short analyzer mismatch")
            a.call("start", 1, 0.5, 128)
            b.call("start", 1, 0.5, 128)
            require(a.render(n * 2 + 5) == b.render(n * 2 + 5), "Short PCM mismatch")
        second = Engine(libs[0], "cap")
        engines.append(second)
        a.load(x)
        second.load(generate("drums", 48000, 1))
        a.call("start", 1, 1, 128)
        second.call("start", 2, 0.5, 16)
        first = a.render(1000)
        second.render(3000)
        second.load(x)
        tail = a.render(1000)
        a.call("start", 1, 1, 128)
        require(first + tail == a.render(2000), "Instance contamination")
        a.call("start", 1, 1, 128)
        good = a.render(10000)
        a.call("start", 2, 1, 128)
        bad = a.render(10000)
        require(good != bad, "Wrong-pitch negative did not differ")
        require(fingerprint() == frozen, "Sources changed during run")
        report.update(
            status="partial" if report["pitch_acceptance_failures"] else "passed",
            host_pcm_bit_exact=True,
            host_keyframes_bit_exact=True,
            state_checks="reset, partition 1/32/64/127, stop, invalid load/control, short input, independent instances",
            wrong_pitch_negative=True,
            state_bytes=libs[0].cap_state_size(),
        )
    except Exception as error:
        report.update(status="failed", error=str(error))
        if isinstance(error, subprocess.CalledProcessError):
            report["build_error"] = error.stderr
        raise
    finally:
        for e in engines:
            e.close()
        report["artifacts"] = {p.name: sha(p) for p in out.iterdir() if p.is_file()}
        write_json(out / "report.json", report)
        print(f"{report['status']}: {out / 'report.json'}", flush=True)

    return 2 if report["status"] == "partial" else 0


if __name__ == "__main__":
    sys.exit(main())
