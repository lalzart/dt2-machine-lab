# ruff: noqa: E402
"""Bounded Plaits VA host, SHARC-kernel, or prepared firmware experiment."""

import argparse
import array
import ctypes
import hashlib
import itertools
import json
import math
import os
import struct
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(
        str(config["python"]),
        [str(config["python"]), str(Path(__file__).resolve()), *sys.argv[1:]],
    )
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--mode", choices=["host", "target", "firmware"], default="target")
parser.add_argument(
    "--variant",
    choices=["reference", "main-only", "shared"],
    default="reference",
    help="Firmware mode only: full reference, omit AUX, or also share matching lanes",
)
parser.add_argument(
    "--blocks",
    type=int,
    default=16000,
    help="Standalone 12-sample blocks; 16000 = four seconds",
)
args = parser.parse_args()
if args.variant != "reference" and args.mode != "firmware":
    parser.error(
        "Optimized variants here require --mode firmware; use compare-plaits-va.py for core comparisons"
    )
if not 120 <= args.blocks <= 16000:
    raise ValueError("Use 120..16000 bounded blocks")
doctor()
out = args.output.resolve()
if not out.is_relative_to(ROOT / "out/runs"):
    raise ValueError("Output must be below out/runs")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.dsp import Dsp
from lab.formats import read_frames
from lab.plaits import MACHINE, build_blob, build_cpu, command

source = ROOT / ".local/sources/eurorack"
lock = json.loads((MACHINE / "source-lock.json").read_text())
for name, digest in lock["files"].items():
    if sha256(source / name) != digest:
        raise ValueError(f"Plaits source drift: {name}")
for path, revision in [
    (source, lock["revision"]),
    (source / "stmlib", lock["stmlib_revision"]),
]:
    if command(["git", "-C", path, "rev-parse", "HEAD"]).strip() != revision:
        raise ValueError("Plaits source revision mismatch")
    if command(["git", "-C", path, "status", "--porcelain"]).strip():
        raise ValueError("Reference checkout is dirty")
fingerprint = source_hashes()
report = {
    "mode": args.mode,
    "variant": args.variant,
    "source_sha256": fingerprint,
    "source_lock": lock,
    "cpu_load_percent": None,
    "dsp_load_percent": None,
}
started = time.monotonic()


def wav(name, values, channels=2, gain=0.2):
    if not all(map(math.isfinite, values)) or max(map(abs, values), default=0) >= 4:
        raise ValueError("Invalid audio; refusing preview")
    raw = array.array("f", values).tobytes()
    (out / f"{name}.f32").write_bytes(raw)
    pcm = array.array("h", [round(max(-1, min(1, v * gain)) * 32767) for v in values])
    with wave.open(str(out / f"{name}.wav"), "wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(2)
        f.setframerate(48000)
        f.writeframes(pcm.tobytes())
    return hashlib.sha256(raw).hexdigest()


def delta(a, b):
    if len(a) != len(b) or not a or not all(map(math.isfinite, [*a, *b])):
        raise ValueError("Invalid comparison samples")
    errors = [abs(x - y) for x, y in zip(a, b, strict=True)]
    return {
        "max_error": max(errors),
        "rms_error": math.sqrt(sum(e * e for e in errors) / len(errors)),
        "samples": len(a),
    }


def run():
    if args.mode == "firmware":
        report["cpu_candidate"] = build_cpu()
        blob = build_blob(integrated=True, variant=args.variant)
        engine = Dsp(blob)
        # The real stored-lock CPU capture is unchanged except explicit event isolation.
        capture = ROOT / "out/runs/controls-final-capture"
        meta = json.loads((capture / "capture.json").read_text())
        raw = read_frames(capture / "controls.dtfr")
        a, b = meta["play_start"], meta["play_end"]
        frames = [raw[a - 1]] * 150 + raw[a:b] + [raw[b - 1]] * 500
        frames = [bytearray(f) for f in frames]
        for f in frames:
            for off in (0x22, 0x24, 0x26, 0x28):
                f[off : off + 2] = (
                    int.from_bytes(f[off : off + 2], "big") & 1
                ).to_bytes(2, "big")
        for f in (frames[0], frames[-1]):
            if any(f[off : off + 2] != b"\0\0" for off in (0x22, 0x24, 0x26, 0x28)):
                raise ValueError("Event-bearing padding")
        audio = []
        events = []
        old_age = 0
        for i, f in enumerate(frames):
            audio.extend(engine.frame(f))
            age = engine.core.peek(0x200E1000 + 368)
            if age and (age < old_age or not old_age):
                values = [
                    struct.unpack(
                        "<f",
                        struct.pack("<I", engine.core.peek(0x200E1000 + 252 + 4 * j)),
                    )[0]
                    for j in range(4)
                ]
                events.append(
                    {
                        "frame": i,
                        "params": values,
                        "length_source_samples": engine.core.peek(0x200E1000 + 372),
                        "gain": struct.unpack(
                            "<f", struct.pack("<I", engine.core.peek(0x200E1000 + 380))
                        )[0],
                    }
                )
            old_age = age
        if not max(map(abs, audio)) > 1e-4:
            raise ValueError("Integrated output is silent")
        if (
            len(events) != 3
            or events[0]["params"] != events[2]["params"]
            or events[0]["params"] == events[1]["params"]
        ):
            raise ValueError("Expected three locked/unlocked/locked previews")
        first, second, third = [v["frame"] * 64 for v in events]
        span = min(second - first, len(audio) - third)
        if audio[first : first + span] != audio[third : third + span]:
            raise ValueError("Recalled locked preview differs")
        report["locked_preview_equal_samples"] = span
        # Repeat the same real-control render, then use the identical input as
        # stock type 6 with and without the hook. This checks the saved-register
        # wrapper against stock behavior rather than only checking compilation.
        repeat = Dsp(blob)
        repeat_pcm = []
        for f in frames:
            repeat_pcm.extend(repeat.frame(f))
        if audio != repeat_pcm:
            raise ValueError("Integrated repeat mismatch")
        report["firmware_repeat_exact"] = True
        import sharcldr

        bypass = bytearray(blob)
        off = sharcldr.offset_for_address(sharcldr.parse_blocks(blob), 0x1C4F15)
        bypass[off : off + 6] = bytes.fromhex("5499a801408c")
        custom_stock = Dsp(blob)
        original_stock = Dsp(bytes(bypass))
        peak_difference = 0.0
        # Short stock window spans initial trigger and the following unlocked note.
        for f in frames[:240]:
            f = bytearray(f)
            f[0x94:0x96] = b"\0\6"
            aa = custom_stock.frame(f)
            bb = original_stock.frame(f)
            peak_difference = max(
                peak_difference, max(abs(x - y) for x, y in zip(aa, bb, strict=True))
            )
        if peak_difference:
            raise ValueError(f"Stock hook changed PCM: {peak_difference}")
        report["stock_hook_max_error"] = peak_difference
        disabled = Dsp(bytes(bypass))
        negative = []
        for f in frames[:240]:
            negative.extend(disabled.frame(f))
        error = delta(audio[: len(negative)], negative)["max_error"]
        if error <= 1e-5:
            raise ValueError("Disabling the new source did not change PCM")
        report["disabled_hook_difference"] = error
        report.update(
            {
                "pcm_sha256": wav("plaits-va", audio, gain=1),
                "frames": len(frames),
                "events": events,
                "capture_sha256": sha256(capture / "controls.dtfr"),
                "boundary": "Prepared firmware track-1 voice-buffer tap; inherited SINE type-7 CPU capture, other-track events masked. Macro panel controls, final mix, hardware and continuous playback unverified.",
                "emulated_instructions": engine.core.stats()["instructions"],
            }
        )
        return

    command(
        [
            "clang++",
            "-std=c++11",
            "-O2",
            "-ffp-contract=off",
            "-DTEST",
            "-shared",
            "-I" + str(source),
            MACHINE / "oracle.cc",
            source / "plaits/dsp/engine/virtual_analog_engine.cc",
            source / "stmlib/dsp/units.cc",
            "-o",
            out / "oracle.dylib",
        ]
    )
    command(
        [
            "clang",
            "-std=c99",
            "-O2",
            "-ffp-contract=off",
            "-shared",
            MACHINE / "core.c",
            "-o",
            out / "candidate.dylib",
        ]
    )
    lib = ctypes.CDLL(str(out / "oracle.dylib"))
    port = ctypes.CDLL(str(out / "candidate.dylib"))
    f12 = ctypes.c_float * 12
    f4 = ctypes.c_float * 4
    state = ctypes.create_string_buffer(252)

    def init():
        lib.oracle_init()
        port.va_init(state)

    def host(p):
        aa, ab, ba, bb = f12(), f12(), f12(), f12()
        pp = f4(*p)
        lib.oracle_render(pp, aa, ab)
        port.va_render(state, pp, ba, bb, 12)
        return [v for pair in zip(aa, ab, strict=True) for v in pair], [
            v for pair in zip(ba, bb, strict=True) for v in pair
        ]

    timeline = [
        (60, 0.5, 0.5, 0.5),
        (48, 0.2, 0.15, 0.8),
        (67, 0.8, 0.9, 0.2),
        (60, 0.5, 0.5, 0.5),
    ]
    # Corner comparisons are host tests of the translation, not target claims.
    corners = []
    for note in (0, 127):
        for h, t, m in itertools.product((0, 1), repeat=3):
            init()
            aa = []
            bb = []
            for _ in range(120):
                a, b = host((note, h, t, m))
                aa += a
                bb += b
            check = delta(aa, bb)
            check["params"] = [note, h, t, m]
            corners.append(check)
            if check["max_error"] > 1e-5:
                raise ValueError(f"Host corner failed: {check}")
    report["host_corners"] = corners
    engine = Dsp(build_blob()) if args.mode == "target" else None
    init()
    reference = []
    candidate = []
    target = []
    short_ref = []
    short_target = []
    costs = []
    for i in range(args.blocks):
        p = timeline[min(3, i // (args.blocks // 4))]
        a, b = host(p)
        reference += a
        candidate += b
        if engine:
            engine.core.poke(0x200E0000, struct.pack("<5f", *p, float(i == 0)), 1)
            before = engine.core.stats()["instructions"]
            engine.call(0xBC0000, 500000)
            costs.append(engine.core.stats()["instructions"] - before)
            left = [
                struct.unpack(
                    "<f", struct.pack("<I", engine.core.peek(0x200E0400 + 4 * j))
                )[0]
                for j in range(12)
            ]
            right = [
                struct.unpack(
                    "<f", struct.pack("<I", engine.core.peek(0x200E0500 + 4 * j))
                )[0]
                for j in range(12)
            ]
            target.extend(v for pair in zip(left, right, strict=True) for v in pair)
        if i % 4000 == 0:
            print(f"Rendered {i}/{args.blocks} blocks", flush=True)
    check = delta(reference, candidate)
    report["host_comparison"] = check
    if check["max_error"] > 1e-5:
        raise ValueError(f"Host comparison failed: {check}")
    report["reference_pcm_sha256"] = wav("reference", reference)
    report["candidate_pcm_sha256"] = wav("candidate", candidate)
    # Reset/repeat and a falsifying silent comparator, without a new test framework.
    init()
    repeat = []
    for i in range(args.blocks):
        _, b = host(timeline[min(3, i // (args.blocks // 4))])
        repeat += b
    if array.array("f", repeat).tobytes() != array.array("f", candidate).tobytes():
        raise ValueError("Host reset/repeat mismatch")
    report["host_repeat_exact"] = True
    report["silent_negative_error"] = delta(reference, [0.0] * len(reference))[
        "max_error"
    ]
    if report["silent_negative_error"] <= 1e-5:
        raise ValueError("Negative comparator did not fail")
    if engine:
        report["target_pcm_sha256"] = wav("plaits-va", target)
        report["long_target_comparison"] = delta(candidate, target)
        # Fresh 120-block target comparison includes all four parameter settings.
        init()
        for i in range(120):
            p = timeline[i // 30]
            _, b = host(p)
            short_ref += b
            engine.core.poke(0x200E0000, struct.pack("<5f", *p, float(i == 0)), 1)
            engine.call(0xBC0000, 500000)
            for j in range(12):
                for base in (0x200E0400, 0x200E0500):
                    short_target.append(
                        struct.unpack(
                            "<f", struct.pack("<I", engine.core.peek(base + 4 * j))
                        )[0]
                    )
        check = delta(short_ref, short_target)
        report["short_target_comparison"] = check
        if check["max_error"] > 2e-3:
            raise ValueError(f"Target comparison failed: {check}")
        repeated = []
        for i in range(120):
            p = timeline[i // 30]
            engine.core.poke(0x200E0000, struct.pack("<5f", *p, float(i == 0)), 1)
            engine.call(0xBC0000, 500000)
            for j in range(12):
                for base in (0x200E0400, 0x200E0500):
                    repeated.append(
                        struct.unpack(
                            "<f", struct.pack("<I", engine.core.peek(base + 4 * j))
                        )[0]
                    )
        if repeated != short_target:
            raise ValueError("Target reset/repeat mismatch")
        report["target_repeat_exact"] = True
        target_corners = []
        for item in corners:
            p = item["params"]
            init()
            aa = []
            bb = []
            for i in range(120):
                _, b = host(p)
                aa += b
                engine.core.poke(0x200E0000, struct.pack("<5f", *p, float(i == 0)), 1)
                engine.call(0xBC0000, 500000)
                for j in range(12):
                    for base in (0x200E0400, 0x200E0500):
                        bb.append(
                            struct.unpack(
                                "<f", struct.pack("<I", engine.core.peek(base + 4 * j))
                            )[0]
                        )
            check = delta(aa, bb)
            check["params"] = p
            target_corners.append(check)
            if check["max_error"] > 2e-3:
                raise ValueError(f"Target corner failed: {check}")
        report["target_corners"] = target_corners
        report["instructions_per_12_sample_block"] = {
            "min": min(costs),
            "max": max(costs),
            "mean": sum(costs) / len(costs),
        }
    report["boundary"] = (
        "Original C++ vs C99 host; optional standalone compiled SHARC in prepared native core. No firmware callback, CPU controls, physical timing or full Plaits voice proof."
    )


try:
    run()
    if source_hashes() != fingerprint:
        raise ValueError("Lab source changed during run")
    report["status"] = "passed"
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    report["host_seconds"] = time.monotonic() - started
    report["outputs"] = {
        p.name: sha256(p)
        for p in out.iterdir()
        if p.is_file() and p.suffix in (".f32", ".wav", ".bin", ".dxe")
    }
    write_json(out / "report.json", report)
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("source_sha256", "source_lock", "host_corners", "outputs")
            },
            indent=2,
        ),
        flush=True,
    )
