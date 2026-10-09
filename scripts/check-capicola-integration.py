#!/usr/bin/env python3
"""Combined Plaits/Flex MAIN and prepared-bank Capicola DSP integration checks."""

# ruff: noqa: E402, I001
import argparse
import array
import ctypes as ct
import hashlib
import importlib.util
import json
import math
import os
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import settings, doctor, require, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--native-prep", action="store_true")
p.add_argument("--owned-memory", action="store_true")
args = p.parse_args()
if args.owned_memory:
    args.native_prep = True
family = (
    "capicola-owned"
    if args.owned_memory
    else "capicola-prep"
    if args.native_prep
    else "capicola"
)
from lab.capicola_memory import BANK_BASE, patch_cpu as memory_cpu

bank_base = BANK_BASE if args.owned_memory else 0x83000000
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = out.name
doctor()
from lab.plaits import build_blob, build_cpu
from lab.flex_native_build import patch_cpu as flex_cpu
from lab.plaits_menu import patch_cpu as menu_cpu
from lab.dsp import Dsp, header
from lab.runtime import STOCK_BLOB
import sharcldr
import sharc_trace as st

report = {
    "status": "running",
    "scope": "Prepared-bank compiled integration; no CPU Capicola menu, native loader, installable package or hardware claim",
    "cases": [],
}
try:
    sources = source_hashes()
    build_cpu(family="integration")
    main, flex = flex_cpu((out / "PLAITS_MAIN_OS.bin").read_bytes())
    main, menu = menu_cpu(main)
    previous = ROOT / "out/runs/flex-20sec-menu-package-02"
    require(
        main == (previous / "PLAITS_R3_FLEX_MAIN_OS.bin").read_bytes(),
        "Existing combined MAIN changed",
    )
    if args.owned_memory:
        main, memory_metadata = memory_cpu(main)
        report["memory_reservation"] = memory_metadata
    (out / "CAPICOLA_TEST_MAIN_OS.bin").write_bytes(main)
    old = build_blob(True, family="integration", output=out / "baseline")
    require(
        old == (previous / "firmware/PLAITS_BLOB.bin").read_bytes(),
        "R3 BLOB baseline drift",
    )
    combined = build_blob(True, family=family, output=out / "combined")
    require(
        combined == build_blob(True, family=family, output=out / "repeat-build"),
        "Combined build not deterministic",
    )
    memory = sharcldr.LoadedMemory.from_stream(STOCK_BLOB.read_bytes())
    for lo, hi in zip(memory._segments[0], memory._segments[1], strict=True):
        require(
            not (lo < (bank_base + 0x697900) and hi > (bank_base - 0x100)),
            "Bank overlaps stock",
        )
        require(
            not (lo < 0x83F10000 and hi > 0x83F00000), "Raw test sample overlaps stock"
        )
    blocks = sharcldr.parse_blocks(combined)
    end = blocks[-1]["offset"]
    rawbytes = bytes(0x10000)
    blob = (
        combined[:end]
        + header((bank_base - 0x100), 0x697A00)
        + bytes(0x697A00)
        + header(0x83F00000, len(rawbytes))
        + rawbytes
        + combined[end:]
    )
    (out / "CAPICOLA_TEST_BLOB.bin").write_bytes(blob)

    def entry(folder):
        return int(
            re.search(
                r"(?m)^machine\.:\n\s+([0-9a-f]+)", (folder / "listing.txt").read_text()
            )[1],
            16,
        )

    pc, oldpc = entry(out / "combined"), entry(out / "baseline")
    spec = importlib.util.spec_from_file_location(
        "capacity_check", ROOT / "scripts/check-capicola-capacity.py"
    )
    cap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cap)
    hostlib, _oracle, _previous = cap.build(out)
    data = cap.fixture("two-tone", 8192)
    data = array.array("f", [round(x * 32767) / 32768 for x in data])
    bank = cap.Sample(hostlib, data)
    require(bank.result == 0, "Host bank load")
    token = 0x83F00000

    def peek(c, address, count):
        return b"".join(
            struct.pack("<I", c.peek(address + i)) for i in range(0, count, 4)
        )

    def poke(c, address, *words):
        c.poke(address, struct.pack("<" + "I" * len(words), *words), 1)

    def publish(e, pitch=1.1, advance=0.7, ready=1):
        c = e.core
        n = bank.capacity
        if not args.native_prep:
            c.poke(bank_base, bank.payload(), 1)
        c.poke(
            token,
            b"".join(
                struct.pack("<hh", round(x * 32768), round(x * 32768)) for x in data
            ),
            1,
        )
        if not args.native_prep:
            poke(
                c,
                0x200E4100,
                bank_base,
                bank_base + n * 4,
                bank_base + n * 8,
                n,
                bank.bank.count,
                len(data),
                0,
                bank.bank.generation,
            )
        c.poke(
            0x200E4000,
            struct.pack(
                "<4I3fiI",
                0x43415031,
                1,
                ready,
                token,
                pitch,
                advance,
                0.125,
                128,
                bank.bank.generation,
            ),
            1,
        )
        for voice in (0x2412CC, 0x2414A4):
            poke(c, voice, token)
            poke(c, voice + 0x188, len(data) * 2)
            c.poke(voice + 0x1B8, b"\x01\0\0\0\0", 1)
            c.poke(voice + 0x17C, bytes(4), 1)
            poke(c, voice + 0x180, 0)
            for offset, position in [
                (0x190, 0),
                (0x198, 0),
                (0x1A0, len(data) * 2),
                (0x1B0, 0),
            ]:
                c.poke(voice + offset, struct.pack("<Q", position << 31), 1)
            c.poke(voice + 0x1A8, struct.pack("<Q", 1 << 31), 1)

    if args.native_prep:
        host_publish = publish
        service_pc = int(
            re.search(
                r"(?m)^cap_service\.:\n\s+([0-9a-f]+)",
                (out / "combined/listing.txt").read_text(),
            )[1],
            16,
        )
        preparation_counts = []

        def service(e, op, count=0):
            c = e.core
            for k, v in {
                "M5": 0,
                "M6": 1,
                "M7": -1,
                "M14": 1,
                "I6": 0x200DFF00,
                "I7": 0x200DFEF8,
                "R4": 0x200E4800,
            }.items():
                c.set_reg(st.UREG_CODES[k], st.Const(v))
            for i in range(16):
                c.set_reg(st.UREG_CODES[f"L{i}"], st.Const(0))
            c.poke(0x200DFEFC, bytes(8), 1)
            poke(c, 0x200E4800, op, token, len(data), 2, count, 0, 0, 0)
            before = c.stats()["instructions"]
            e.call(service_pc, 2000000)
            preparation_counts.append(c.stats()["instructions"] - before)
            return struct.unpack("<3I", peek(c, 0x200E4814, 12))

        def publish(e, pitch=1.1, advance=0.7, ready=1):
            # Cancel before replacing source; host uploads PCM, never keyframes.
            if getattr(e, "cap_prep_initialized", False):
                service(e, 4)
            else:
                service(e, 0)
                e.cap_prep_initialized = True
            host_publish(e, pitch, advance, ready=0)
            e.core.poke(bank_base, bytes(len(bank.payload())), 1)
            require(service(e, 1)[0] == 1, "Native begin")
            while True:
                phase, needed, index = service(e, 2, 256)
                require(e.core.peek(0x200E4008) == 0, "Published during count")
                if phase != 1:
                    break
            require(phase == 2 and needed == bank.bank.count, "Native measured keys")
            require(service(e, 3, needed)[0] == 3, "Native storage bind")
            while True:
                phase, _, index = service(e, 2, 256)
                if phase != 3:
                    break
                require(e.core.peek(0x200E4008) == 0, "Published during write")
            require(phase == 4, "Native bank completion")
            require(
                peek(e.core, bank_base, len(bank.payload())) == bank.payload(),
                "Native keys differ from host",
            )
            if not ready:
                poke(e.core, 0x200E4008, 0)

        report["bank_preparation"] = (
            "Compiled int16 worker; harness schedules and supplies arena storage"
        )

    calls = []

    def invoke(
        e, typ=8, trig=0, lane=0, model=0, wrapped=False, baseline=False, voice=None
    ):
        c = e.core
        voice = voice or (0x2412CC, 0x2414A4)[lane]
        regs = {
            "M5": 0,
            "M6": 1,
            "M7": -1,
            "M14": 1,
            "I6": 0x200DC000 if wrapped else 0x200DFF00,
            "I7": 0x200DBFF8 if wrapped else 0x200DFEF8,
            "R4": voice,
            "R12": 0,
        }
        regs.update({f"L{i}": 0 for i in range(16)})
        for k, v in regs.items():
            c.set_reg(st.UREG_CODES[k], st.Const(v))
        c.poke(0x200DBFFC if wrapped else 0x200DFEFC, bytes(8), 1)
        for address, value in {
            0x255970: typ,
            0x24F0CC: trig << (lane * 8),
            0x2558DE: 103 * 256,
            0x2559B6: 0,
            0x2559B8: 8192,
            0x2559BA: model * 256,
            0x2559BC: 16384,
            0x2559C2: 24576,
            0x2559C4: 2304,
            0x2559C8: 16384,
        }.items():
            poke(c, address, value)
        before = c.stats()["instructions"]
        e.call(
            e.profile.voice_render if wrapped else (oldpc if baseline else pc), 2000000
        )
        calls.append(c.stats()["instructions"] - before)
        result = peek(c, voice + 4, 256)
        require(
            all(map(math.isfinite, struct.unpack("<64f", result))), "Nonfinite output"
        )
        return result

    # All unchanged Plaits models, both lanes, direct compiled adapter parity.
    for model in range(6):
        a, b = Dsp(blob), Dsp(old)
        for lane in (0, 1):
            for i in range(12):
                require(
                    invoke(a, 7, i == 0, lane, model)
                    == invoke(b, 7, i == 0, lane, model, baseline=True),
                    "Plaits parity",
                )
    report["plaits_models_both_lanes"] = 6
    print("Plaits parity passed", flush=True)
    # Full short sample at non-binary rates, retrigger, independent lanes, terminal silence.
    for pitch, advance in [(1.1, 0.7), (0.7, 1), (1, 2)]:
        engine = Dsp(blob)
        publish(engine, pitch, advance)
        ref = cap.Reader(bank)
        require(ref.start(pitch, advance) == 0, "Reference start")
        count = math.ceil(len(data) / ct.c_float(advance).value)
        blocks = (count + 31) // 32 + 2
        expected = ref.render(blocks * 32)
        samples = array.array("f")
        samples.frombytes(expected)
        expected = array.array(
            "f", [x * 0.125 for x in samples for _ in range(2)]
        ).tobytes()
        actual = b"".join(invoke(engine, trig=i == 0) for i in range(blocks))
        mx, rms = cap.previous.error(expected, actual)
        require(mx <= 1e-4 and rms <= 1e-5, "Capicola parity")
        again = b"".join(invoke(engine, trig=i == 0) for i in range(blocks))
        require(actual == again, "Retrigger repeat")
        require(invoke(engine) == bytes(256), "Terminal silence")
        # Other lane starts independently from zero.
        require(invoke(engine, trig=1, lane=1) == actual[:256], "Lane parity")
        report["cases"].append(
            dict(
                pitch=pitch,
                advance=advance,
                frames=blocks * 32,
                max_error=mx,
                rms_error=rms,
            )
        )
        print("Capicola direct", pitch, advance, "passed", flush=True)
    # Execute stock prologue -> patched jump -> compiled dispatcher -> stock epilogue.
    direct, hooked = Dsp(blob), Dsp(blob)
    publish(direct)
    publish(hooked)
    hookpcm = []
    for i in range(100):
        a = invoke(direct, trig=i == 0)
        b = invoke(hooked, trig=i == 0, wrapped=True)
        require(a == b, "Actual voice hook differs from direct adapter")
        hookpcm.append(b)
    report["stock_voice_hook_blocks"] = 100
    (out / "capicola-voice.f32").write_bytes(b"".join(hookpcm))
    pcm = array.array("f")
    pcm.frombytes(b"".join(hookpcm))
    cap.ref.save_wav(out / "capicola-voice.wav", array.array("f", pcm[::2]).tobytes())
    print("Actual voice hook passed", flush=True)
    # Fail-closed handoff cases; start from a valid audible state each time.
    negatives = [
        (0x200E4000, 0),
        (0x200E4004, 2),
        (0x200E4008, 0),
        (0x200E400C, token + 4),
        (0x200E4020, 999),
        (0x200E4100, 0),
        (0x200E410C, 576005),
        (0x200E4110, 1),
        (0x200E4114, 576001),
        (0x200E4118, 1),
        (0x200E4010, 0x7FC00000),
    ]
    e = Dsp(blob)
    for address, value in negatives:
        publish(e)
        invoke(e, trig=1)
        invoke(e)
        poke(e.core, address, value)
        require(invoke(e) == bytes(256), "Invalid/stale bank did not silence")
        require(invoke(e, trig=1) == bytes(256), "Invalid bank retrigger")
    report["handoff_negative_cases"] = len(negatives)
    publish(e)
    first = invoke(e, trig=1)
    invoke(e, 7, trig=1)
    require(invoke(e) == bytes(256), "Switch leaked old voice")
    require(invoke(e, trig=1) == first, "Switch retrigger")
    require(
        peek(e.core, bank_base, len(bank.payload())) == bank.payload(), "Bank mutated"
    )
    # Unsupported track/voice must leave caller destination and track-1 state untouched.
    sentinel = 0x24167C
    e.core.poke(sentinel + 4, bytes.fromhex("ab") * 256, 1)
    before = peek(e.core, 0x200E4200, 168)
    invoke(e, voice=sentinel)
    require(
        peek(e.core, sentinel + 4, 256) == bytes.fromhex("ab") * 256
        and peek(e.core, 0x200E4200, 168) == before,
        "Unsupported voice touched state",
    )
    # Stock fallback through the same real voice entry remains identical to original R3.
    a, b = Dsp(blob), Dsp(old)
    publish(a)
    (host_publish if args.native_prep else publish)(b)
    stock_pcm = []
    for _i in range(8):
        x = invoke(a, 6, wrapped=True)
        require(x == invoke(b, 6, wrapped=True, baseline=True), "Stock fallback parity")
        stock_pcm.extend(struct.unpack("<64f", x))
    require(max(abs(v) for v in stock_pcm) > 1e-5, "Vacuous silent stock comparator")
    report["stock_fallback_blocks"] = 8
    from lab.formats import read_frames

    frames = read_frames(config["fixture"] / "captures/sine-type-7.dtfr")
    frame_engine = Dsp(blob)
    frame_outputs = []
    for frame in frames[:80]:
        patched = bytearray(frame)
        patched[0x94:0x96] = b"\0\x08"
        frame_outputs.extend(frame_engine.frame(bytes(patched)))
    require(
        (frame_engine.core.peek(0x255970) & 65535) == 8,
        "Frame selector did not reach DSP",
    )
    require(
        all(v == 0 for v in frame_outputs),
        "Unpublished bank was not silent in frame replay",
    )
    report["prepared_frame_replay"] = {
        "frames": min(80, len(frames)),
        "selector": "injected type 8",
        "bank": "unpublished",
        "result": "silent, no interpreter faults",
    }
    if args.native_prep:
        report["max_preparation_instructions"] = max(preparation_counts)
    require(source_hashes() == sources, "Source drift during check")
    report.update(
        status="passed",
        sources=sources,
        main_unchanged=not args.owned_memory,
        main_sha256=hashlib.sha256(main).hexdigest(),
        combined_blob_sha256=hashlib.sha256(blob).hexdigest(),
        max_call_instructions=max(calls),
        bank_bytes=len(bank.payload()),
        repeat_build_exact=True,
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))
