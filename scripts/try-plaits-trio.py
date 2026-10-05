# ruff: noqa: E402
"""Repeat the bounded VA/FM/BD source, target and prepared firmware checks."""

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
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--stage", choices=("core", "firmware", "all"), default="all")
p.add_argument(
    "--capture", type=Path, help="Passing capture-plaits-trio.py run directory"
)
args = p.parse_args()
if args.stage in ("all", "firmware") and not args.capture:
    p.error("Firmware replay requires --capture from capture-plaits-trio.py")
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.dsp import Dsp
from lab.formats import read_frames
from lab.metrics import distribution
from lab.plaits import build_blob, build_cpu, command

machine = ROOT / "machines/plaits-trio"
source = ROOT / ".local/sources/eurorack"
lock = json.loads((machine / "source-lock.json").read_text())
for name, digest in lock["files"].items():
    require(sha256(source / name) == digest, f"Upstream drift: {name}")
for name, digest in lock["reuse_sha256"].items():
    require(sha256(ROOT / name) == digest, f"Reused VA drift: {name}")
for path, revision in (
    (source, lock["revision"]),
    (source / "stmlib", lock["stmlib_revision"]),
):
    require(
        command(["git", "-C", path, "rev-parse", "HEAD"]).strip() == revision,
        "Wrong source revision",
    )
    require(
        not command(["git", "-C", path, "status", "--porcelain"]).strip(),
        "Dirty upstream",
    )
fingerprint = source_hashes()
report = {
    "source_sha256": fingerprint,
    "source_lock": lock,
    "control_sha256": sha256(machine / "controls.json"),
    "cpu_load_percent": None,
    "dsp_load_percent": None,
    "boundary": "Prepared emulator and voice-buffer PCM; no physical timing, final mix, full Plaits voice or clean-startup claim.",
}
started = time.monotonic()
TIMELINE = [
    (48, 0.25, 0.3, 0.4),
    (60, 0.7, 0.8, 0.2),
    (36, 0.9, 0.1, 0.8),
    (48, 0.25, 0.3, 0.4),
]
MODELS = ("VA", "FM", "BD")
STATE = 0x200E1000
VOICES = (0x2412CC, 0x2414A4)


def pcm(values):
    require(bool(values) and all(map(math.isfinite, values)), "Invalid PCM")
    return array.array("f", values).tobytes()


def error(a, b):
    require(len(a) == len(b), "PCM extent mismatch")
    pcm(a)
    pcm(b)
    return max(abs(x - y) for x, y in zip(a, b, strict=True))


def wav(name, values, channels=1, gain=0.2):
    data = pcm(values)
    (out / (name + ".f32")).write_bytes(data)
    require(max(map(abs, values)) < 4, "Preview exceeds bound")
    shorts = array.array(
        "h", (round(max(-1, min(1, v * gain)) * 32767) for v in values)
    )
    with wave.open(str(out / (name + ".wav")), "wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(2)
        f.setframerate(48000)
        f.writeframes(shorts.tobytes())
    return hashlib.sha256(data).hexdigest()


def peek(core, addr, size):
    return struct.pack(
        f"<{size // 4}I", *(core.peek(addr + i) for i in range(0, size, 4))
    )


def core_checks():
    common = ["-O2", "-ffp-contract=off", "-shared"]
    sources = [
        source / ("plaits/dsp/engine/" + n + "_engine.cc")
        for n in ("virtual_analog", "fm", "bass_drum")
    ]
    command(
        [
            "clang++",
            "-std=c++11",
            *common,
            "-DTEST",
            "-I" + str(source),
            machine / "oracle.cc",
            *sources,
            source / "plaits/resources.cc",
            source / "stmlib/dsp/units.cc",
            source / "stmlib/utils/random.cc",
            "-o",
            out / "oracle.dylib",
        ]
    )
    command(
        ["clang", "-std=c99", *common, machine / "core.c", "-o", out / "core.dylib"]
    )
    oracle = ctypes.CDLL(str(out / "oracle.dylib"))
    port = ctypes.CDLL(str(out / "core.dylib"))
    f4, f12 = ctypes.c_float * 4, ctypes.c_float * 12
    port.trio_render.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int,
        ctypes.c_float,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int,
    ]
    oracle.oracle_render.argtypes = [
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int,
        ctypes.c_float,
        ctypes.POINTER(ctypes.c_float),
    ]
    require(port.trio_size() == 256, "State ABI mismatch")
    state = ctypes.create_string_buffer(256)
    engine = Dsp(build_blob(family="trio", output=out / "target"))
    results = []
    demo = []
    report["core"] = results
    corners = list(itertools.product((0, 127), (0, 1), (0, 1), (0, 1)))
    for model, name in enumerate(MODELS):
        print("Comparing " + name, flush=True)
        host_max = 0
        audio = []
        for case in range(17):
            oracle.oracle_init(model)
            port.trio_init(state, model)
            for i in range(4000 if case == 0 else 120):
                parameters = TIMELINE[i // 1000] if case == 0 else corners[case - 1]
                trig = int(i % (1000 if case == 0 else 120) == 0)
                aa, bb = f12(), f12()
                oracle.oracle_render(f4(*parameters), trig, 0.8, aa)
                port.trio_render(state, f4(*parameters), trig, 0.8, bb, 12)
                host_max = max(host_max, error(aa, bb))
                require(
                    host_max <= 1e-5, f"{name} host mismatch {case}/{i}: {host_max}"
                )
                if case == 0:
                    audio.extend(bb)
        port.trio_init(state, model)
        repeat = []
        for i in range(4000):
            bb = f12()
            port.trio_render(
                state, f4(*TIMELINE[i // 1000]), int(i % 1000 == 0), 0.8, bb, 12
            )
            repeat.extend(bb)
        require(pcm(audio) == pcm(repeat), f"{name} host repeat failed")
        host_sha = wav("host-" + name.lower(), audio)
        demo.extend(audio)
        demo.extend([0.0] * 4800)
        target_runs = []
        costs = []
        target_max = 0
        for repeat_index in range(2):
            port.trio_init(state, model)
            samples = []
            for i in range(120):
                parameters = TIMELINE[i // 30]
                trig = int(i % 30 == 0)
                bb = f12()
                port.trio_render(state, f4(*parameters), trig, 0.8, bb, 12)
                engine.core.poke(
                    0x200E0000,
                    struct.pack(
                        "<8f",
                        *parameters,
                        float(i == 0),
                        float(model),
                        float(trig),
                        0.8,
                    ),
                    1,
                )
                before = engine.core.stats()["instructions"]
                engine.call(0xBC0000, 500000)
                if repeat_index == 0:
                    costs.append(engine.core.stats()["instructions"] - before)
                actual = struct.unpack("<12f", peek(engine.core, 0x200E0400, 48))
                samples.extend(actual)
                target_max = max(target_max, error(bb, actual))
                require(
                    target_max <= 2e-3, f"{name} target mismatch at {i}: {target_max}"
                )
            target_runs.append(pcm(samples))
        require(target_runs[0] == target_runs[1], f"{name} target repeat failed")
        (out / ("target-" + name.lower() + ".f32")).write_bytes(target_runs[0])
        require(max(map(abs, audio)) > 1e-4, f"{name} silent negative failed")
        results.append(
            {
                "model": name,
                "host_max_error": host_max,
                "host_blocks": 4000,
                "host_corners": 16,
                "host_repeat_exact": True,
                "host_pcm_sha256": host_sha,
                "target_blocks": 120,
                "target_max_error": target_max,
                "target_repeat_exact": True,
                "target_pcm_sha256": hashlib.sha256(target_runs[0]).hexdigest(),
                "instructions_per_12_samples": distribution(costs),
            }
        )
    report["host_demo_sha256"] = wav("plaits-trio-host", demo)


def adapter_checks(blob):
    import sharc_trace as st

    listing = (out / "firmware/listing.txt").read_text()
    entry = int(re.search(r"(?m)^machine\.:\n\s+([0-9a-f]+)", listing)[1], 16)

    def invoke(engine, lane, model=0, trigger=0, note=48, typ=7, va=False, pc=entry):
        c = engine.core
        regs = {
            "M5": 0,
            "M6": 1,
            "M7": -1,
            "M14": 1,
            "I6": 0x200DFF00,
            "I7": 0x200DFEF8,
            "R4": VOICES[lane],
        }
        regs.update({f"L{i}": 0 for i in range(16)})
        for k, v in regs.items():
            c.set_reg(st.UREG_CODES[k], st.Const(v))
        c.poke(0x200DFEFC, struct.pack("<II", 0, 0), 1)
        # Binary-exact macro fractions shared by both control scalings.
        vals = {
            0x255970: typ,
            0x24F0CC: trigger << (lane * 8),
            0x2558DE: (note + 55) * 256,
            0x2559B6: 0,
            0x2559B8: 16384 if va else 384,
            0x2559BA: model * 256,
            0x2559BC: 0,
            0x2559BE: 16384,
            0x2559C2: 8192,
            0x2559C4: 1229,
            0x2559C8: 16384,
        }
        for addr, v in vals.items():
            c.poke(addr, struct.pack("<I", v), 1)
        engine.call(pc, 500000)
        return peek(c, VOICES[lane] + 4, 256)

    a, b = Dsp(blob), Dsp(blob)
    for model in range(3):
        first = []
        for repeat_index in range(2):
            blocks = [invoke(a, 0, model, int(i == 0)) for i in range(20)]
            if repeat_index == 0:
                first = blocks
            else:
                require(first == blocks, f"{MODELS[model]} adapter reset mismatch")
        require(
            any(struct.unpack("<64f", x) != (0.0,) * 64 for x in first),
            "Silent adapter",
        )
    # Compare selected model with a deliberately wrong model on the same trigger.
    aa = b"".join(invoke(a, 0, 0, int(i == 0)) for i in range(4))
    bb = b"".join(invoke(b, 0, 1, int(i == 0)) for i in range(4))
    require(aa != bb, "Wrong-model negative failed")
    invoke(a, 0, 0, 1)
    invoke(b, 0, 0, 1)
    for _ in range(5):
        require(
            invoke(a, 0, 2) == invoke(b, 0, 0), "Selector changed sound without trigger"
        )
        require(
            peek(a.core, STATE, 348) == peek(b.core, STATE, 348),
            "Selector changed active state",
        )
    invoke(a, 1, 2, 1, note=36)
    untouched = peek(a.core, STATE + 348, 348)
    invoke(a, 0, 1, 1, note=72)
    require(peek(a.core, STATE + 348, 348) == untouched, "Cross-lane state mutation")
    require(
        a.core.peek(STATE + 252) == 1 and a.core.peek(STATE + 348 + 252) == 2,
        "Unequal models not retained",
    )
    invoke(a, 0, typ=6)
    require(a.core.peek(STATE + 332) == 0, "Type switch failed to clear activity")
    require(invoke(a, 0) == bytes(256), "Return without trigger was not silent")
    # Existing VA source and common adapter must agree on semantic inputs.
    va = Dsp(build_blob(True, variant="main-only", output=out / "va-compatibility"))
    va_entry = int(
        re.search(
            r"(?m)^machine\.:\n\s+([0-9a-f]+)",
            (out / "va-compatibility/listing.txt").read_text(),
        )[1],
        16,
    )
    for i in range(20):
        require(
            invoke(a, 0, 0, int(i == 0))
            == invoke(va, 0, 0, int(i == 0), va=True, pc=va_entry),
            "Existing VA adapter PCM changed",
        )
    report["adapter"] = {
        "reset_repeat_exact": True,
        "model_latched_until_trigger": True,
        "unequal_lane_models_isolated": True,
        "switch_away_clears": True,
        "silent_return": True,
        "wrong_model_negative_detected": True,
        "existing_va_pcm_exact": True,
        "scope": "Direct compiled adapter calls with explicit synthetic controls",
    }


def replay(blob, frames):
    engine = Dsp(blob)
    audio = []
    events = []
    previous = 0
    for i, f in enumerate(frames):
        audio.extend(engine.frame(f))
        age = engine.core.peek(STATE + 324)
        if age and (not previous or age < previous):
            events.append({"frame": i, "model": engine.core.peek(STATE + 252)})
        previous = age
    return engine, audio, events


def cpu_model_check():
    """Execute the small discrete-control shim; all stock types must be unchanged."""
    from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc
    from unicorn import m68k_const as k

    data = (out / "PLAITS_MAIN_OS.bin").read_bytes()
    uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    uc.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
    for addr, size in (
        (0x40311000, 0x1000),
        (0x400D9000, 0x1000),
        (0x80003000, 0x1000),
        (0x80005000, 0x2000),
    ):
        uc.mem_map(addr, size)
    start = 0x40311D04
    uc.mem_write(start, data[start - 0x40000400 : start - 0x40000400 + 40])
    regs = [
        getattr(k, f"UC_M68K_REG_{prefix}{n}")
        for prefix in ("D", "A")
        for n in range(8)
    ]
    for typ in range(8):
        for model in (0, 256, 512):
            for n, reg in enumerate(regs):
                uc.reg_write(reg, 0x12340000 + n)
            uc.mem_write(0x80003CD0, bytes([typ]))
            uc.mem_write(0x80003398, struct.pack(">H", model))
            before = bytes([0x5A]) * 0x1000
            uc.mem_write(0x80005B50, before)
            uc.emu_start(start, 0x400D934C, count=40)
            expected = bytearray(before)
            if typ == 7:
                expected[0x58:0x5A] = struct.pack(">H", model)
            require(
                bytes(uc.mem_read(0x80005B50, len(before))) == expected,
                "MODEL shim changed wrong memory",
            )
            require(
                uc.reg_read(k.UC_M68K_REG_D0) == 0x80005B50,
                "MODEL shim changed return value",
            )
            require(
                all(
                    uc.reg_read(reg) == 0x12340000 + n
                    for n, reg in enumerate(regs)
                    if n
                ),
                "MODEL shim clobbered a register",
            )
    report["cpu_model_shim"] = {
        "cases": 24,
        "stock_types_unchanged": True,
        "only_track1_model_bypasses_smoothing": True,
        "other_registers_preserved": True,
    }


def firmware_checks():
    report["cpu_candidate"] = build_cpu(family="trio")
    cpu_model_check()
    blob = build_blob(True, family="trio", output=out / "firmware")
    print("Checking compiled adapter state and existing VA compatibility", flush=True)
    adapter_checks(blob)
    capture = args.capture.resolve()
    meta = json.loads((capture / "capture.json").read_text())
    require(meta["status"] == "passed", "Capture did not pass")
    require(sha256(capture / "models.dtfr") == meta["capture_sha256"], "Capture drift")
    require(
        meta["cpu_candidate"]["sha256"] == report["cpu_candidate"]["sha256"],
        "CPU build differs from capture",
    )
    frames = read_frames(capture / "models.dtfr")
    start, end = meta["preview_start"], meta["preview_end"]
    frames = [
        bytearray(f)
        for f in [frames[start - 1]] * 150 + frames[start:end] + [frames[end - 1]] * 350
    ]
    for f in frames:
        for off in (0x22, 0x24, 0x26, 0x28):
            f[off : off + 2] = (int.from_bytes(f[off : off + 2], "big") & 1).to_bytes(
                2, "big"
            )
    require(
        all(
            f[o : o + 2] == b"\0\0"
            for f in (frames[0], frames[-1])
            for o in (0x22, 0x24, 0x26, 0x28)
        ),
        "Event-bearing padding",
    )
    report["capture"] = {
        "path": str(capture),
        "sha256": meta["capture_sha256"],
        "adaptation": "150 pre-roll and 350 tail frames; other-track event bits masked; model and parameter values unchanged",
        "prepared_sha256": hashlib.sha256(b"".join(frames)).hexdigest(),
    }
    print(f"Replaying {len(frames)} real CPU capture frames", flush=True)
    engine, audio, events = replay(blob, frames)
    report["events"] = events
    require(
        [e["model"] for e in events] == [0, 1, 2, 0], f"Wrong rendered models: {events}"
    )
    require(max(map(abs, audio)) > 1e-4, "Silent integrated render")
    first, second, _, fourth = [e["frame"] * 64 for e in events]
    span = min(second - first, len(audio) - fourth)
    require(
        pcm(audio[first : first + span]) == pcm(audio[fourth : fourth + span]),
        "VA lock recall differs",
    )
    print("Repeating capture; checking stock and disabled-hook comparators", flush=True)
    _, repeat, _ = replay(blob, frames)
    require(pcm(audio) == pcm(repeat), "Firmware exact repeat failed")
    import sharcldr

    disabled = bytearray(blob)
    off = sharcldr.offset_for_address(sharcldr.parse_blocks(disabled), 0x1C4F15)
    disabled[off : off + 6] = bytes.fromhex("5499a801408c")
    short = frames[: min(len(frames), events[1]["frame"] + 40)]
    stock = [bytearray(f) for f in short]
    for f in stock:
        f[0x94:0x96] = b"\0\6"
    _, aa, _ = replay(blob, stock)
    _, bb, _ = replay(bytes(disabled), stock)
    require(pcm(aa) == pcm(bb), "Stock hook changed PCM")
    _, negative, _ = replay(bytes(disabled), short)
    difference = error(audio[: len(negative)], negative)
    require(difference > 1e-5, "Disabled-hook negative failed")
    report["firmware"] = {
        "frames": len(frames),
        "repeat_exact": True,
        "va_lock_equal_samples": span,
        "stock_hook_exact": True,
        "disabled_hook_difference": difference,
        "pcm_sha256": wav("plaits-trio", audio, channels=2, gain=1),
        "block_handler_instructions": sum(engine.block_instructions),
        "instructions_per_frame": distribution(engine.block_instructions),
    }


try:
    if args.stage in ("core", "all"):
        core_checks()
    if args.stage in ("firmware", "all"):
        firmware_checks()
    require(source_hashes() == fingerprint, "Source changed during run")
    report["status"] = "passed"
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    report["host_seconds"] = time.monotonic() - started
    report["outputs"] = {
        str(p.relative_to(out)): sha256(p)
        for p in out.rglob("*")
        if p.is_file() and p.suffix in (".f32", ".wav", ".bin", ".dxe", ".dylib")
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
