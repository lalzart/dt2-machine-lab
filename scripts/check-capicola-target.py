#!/usr/bin/env python3
"""Execute the split-time Capicola core in a standalone SHARC arena."""

# ruff: noqa: E402, I001
# lab.runtime must install the pinned DigiKit import paths before SHARC imports.
import argparse
import ctypes as ct
import importlib.util
import math
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, settings


def main():
    config = settings()
    if Path(sys.executable).resolve() != config["python"].resolve():
        os.execv(
            str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]]
        )
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / "out/runs"):
        raise ValueError("Use out/runs/<unique>")
    out.mkdir(parents=True, exist_ok=False)
    doctor()
    os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
    from lab.dsp import Dsp, header
    from lab.runtime import STOCK_BLOB, SELACHE
    from sharc_selache import (
        SelacheError,
        compare_listing,
        find_elf_section,
        swap_parcels,
    )
    import sharcldr

    compiler = ROOT / "out/cache/selache-c99/release/selcc"
    tools = SELACHE / "target/release"
    report = {
        "status": "running",
        "boundary": "Standalone SHARC audio execution, not a firmware voice or physical timing test",
        "compiler_sha256": hashlib.sha256(compiler.read_bytes()).hexdigest(),
        "commands": [],
    }

    def run(cmd):
        cmd = [str(a) for a in cmd]
        report["commands"].append(cmd)
        return subprocess.check_output(
            cmd, text=True, stderr=subprocess.STDOUT, timeout=120
        )

    try:
        run(
            [
                compiler,
                "-proc",
                "ADSP-21569",
                "-double-size-64",
                "-O1",
                "-S",
                "-o",
                out / "original.s",
                ROOT / "machines/capicola/split-target.c",
            ]
        )
        assembly = (out / "original.s").read_text()
        assembly = re.sub(
            r"(?m)^(\s*R\d+ = R\d+ \+ R\d+;)$",
            r".NOCOMPRESS;\n\1\n.COMPRESS;",
            assembly,
        )
        (out / "probe.s").write_text(assembly)
        (out / "wrapper.s").write_text(""".SECTION/PM seg_pmco;
.GLOBAL start;
.EXTERN kernel.;
start:
M5=0; M6=1; M7=-1; M13=0; M14=1; M15=-1;
L0=0; L1=0; L2=0; L3=0; L4=0; L5=0; L6=0; L7=0;
I7=0x200dff00; I6=I7; R4=0x200e0000;
JUMP kernel. (DB);
DM(I7,M7)=0; DM(I7,M7)=done-1;
done: RTS;
""")
        (out / "memory.ldf").write_text("""ARCHITECTURE(ADSP-21569)
MEMORY { code { TYPE(BW RAM) START(0x20080000) END(0x200bffff) WIDTH(8) }
 data { TYPE(BW RAM) START(0x200c0000) END(0x200cffff) WIDTH(8) } }
PROCESSOR core0 { OUTPUT($COMMAND_LINE_OUTPUT_FILE) ENTRY(start)
 SECTIONS { code SW { INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_pmco seg_swco)) } > code
 data BW { INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_dmda seg_l2 seg_l1_bss seg_l2_bss)) } > data } }
""")
        for name in ["wrapper", "probe"]:
            run(
                [
                    tools / "selas",
                    "-proc",
                    "ADSP-21569",
                    "-o",
                    out / (name + ".doj"),
                    out / (name + ".s"),
                ]
            )
        run(
            [
                tools / "seld",
                "-proc",
                "ADSP-21569",
                "-T",
                out / "memory.ldf",
                "-o",
                out / "probe.dxe",
                out / "wrapper.doj",
                out / "probe.doj",
            ]
        )
        listing = run([tools / "seldump", "-ns", "code", out / "probe.dxe"])
        (out / "listing.txt").write_text(listing)
        if not compare_listing(listing).all_extents_agree:
            raise ValueError("Instruction width disagreement")
        code = swap_parcels(find_elf_section(out / "probe.dxe", "code"))
        try:
            data = find_elf_section(out / "probe.dxe", "data")
        except SelacheError as exc:
            if "section 'data' not found" not in str(exc):
                raise
            data = b""
        if len(code) > 0x40000 or len(data) > 0x1000:
            raise ValueError("Linked sections exceed standalone reservation")
        stock = STOCK_BLOB.read_bytes()
        blocks = sharcldr.parse_blocks(stock)
        memory = sharcldr.LoadedMemory.from_stream(stock)
        for lo, hi in zip(memory._segments[0], memory._segments[1], strict=True):
            if lo < 0x200F0000 and hi > 0x20080000:
                raise ValueError("Probe arena overlaps stock loader")
        arena = bytearray(0x70000)
        arena[: len(code)] = code
        arena[0x40000 : 0x40000 + len(data)] = data
        split = blocks[-1]["offset"]
        if blocks[-1]["byte_count"] or blocks[-1]["flags"] != ["bit0", "FINAL"]:
            raise ValueError("Unexpected loader ending")
        blob = stock[:split] + header(0x20080000, len(arena)) + arena + stock[split:]
        engine = Dsp(blob)
        spec = importlib.util.spec_from_file_location(
            "split_check", ROOT / "scripts/check-capicola-split.py"
        )
        check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check)
        base, split_core = check.build(out)
        report["source_hashes"] = check.fingerprint()
        report["code_bytes"] = len(code)
        report["data_bytes"] = len(data)
        report["cases"] = []
        report["max_block_instructions"] = 0
        block_counts = []

        def peek_bytes(address, count):
            return b"".join(
                struct.pack("<I", engine.core.peek(address + i))
                for i in range(0, count, 4)
            )

        def call(command, count=0, leash=128, pitch=1, advance=1):
            engine.core.poke(
                0x200E0000,
                struct.pack("<8i", command, count, leash, 0, -999, -999, -999, -999),
                1,
            )
            engine.core.poke(0x200E0100, struct.pack("<2f", pitch, advance), 1)
            before = engine.core.stats()["instructions"]
            engine.call(0xBC0000, 10000000)
            instructions = engine.core.stats()["instructions"] - before
            if command == 3:
                block_counts.append(instructions)
                report["max_block_instructions"] = max(
                    report["max_block_instructions"], instructions
                )
            return struct.unpack("<4i", peek_bytes(0x200E0010, 16))

        layout = call(0)
        if layout[:3] != (len(split_core.state), 49152, len(split_core.state) - 4):
            raise ValueError(f"Target state layout mismatch: {layout}")
        report["state_bytes"] = layout[0]
        report["analyzer_mismatches"] = []
        report["analyzer_details"] = []
        # Target analyzer exercises raw-buffer indexing, extrema and timestamp encoding.
        for name in ["silence", "sine", "two-tone", "drums"]:
            fixture = check.ref.generate(name, 2048, 1)
            split_core.load(fixture)
            engine.core.poke(0x200E1000, fixture.tobytes(), 1)
            result = call(1, len(fixture))[0]
            actual = peek_bytes(0x200C1000, len(split_core.state))
            expected = bytes(split_core.state)
            count = split_core.call("count")
            target_count = struct.unpack_from("<i", actual, 49152)[0]
            differences = []
            if count == target_count:
                for i in range(count):
                    hv, tv = (
                        struct.unpack_from("<f", expected, i * 4)[0],
                        struct.unpack_from("<f", actual, i * 4)[0],
                    )
                    hw, tw = (
                        struct.unpack_from("<i", expected, 16384 + i * 4)[0],
                        struct.unpack_from("<i", actual, 16384 + i * 4)[0],
                    )
                    hf, tf = (
                        struct.unpack_from("<I", expected, 32768 + i * 4)[0],
                        struct.unpack_from("<I", actual, 32768 + i * 4)[0],
                    )
                    differences.append(
                        (abs(hv - tv), abs((hw - tw) + (hf - tf) / 2**24))
                    )
            report["analyzer_details"].append(
                dict(
                    signal=name,
                    host_count=count,
                    target_count=target_count,
                    max_value_error=max((x[0] for x in differences), default=None),
                    max_time_error=max((x[1] for x in differences), default=None),
                )
            )
            # Unused keyframe slots need not be initialized or zeroed.
            sections = [
                (0, count * 4),
                (16384, count * 4),
                (32768, count * 4),
                (49152, len(expected) - 49152),
            ]
            if result != 0 or any(
                actual[a : a + n] != expected[a : a + n] for a, n in sections
            ):
                (out / (name + "-target-state.bin")).write_bytes(actual)
                (out / (name + "-host-state.bin")).write_bytes(expected)
                report["analyzer_mismatches"].append(name)
        report["target_analyzer_cases"] = 4
        fixtures = [
            ("sine", 1, 0.7, None),
            ("sine", 0.7, 1, None),
            ("sine", 1.1, 0.7, None),
            ("impulse", 1, 0.7, 4096),
            ("two-tone", 1.1, 0.7, 4096),
            ("drums", 0.7, 1, 4096),
        ]
        for index, (name, pitch, advance, limit) in enumerate(fixtures):
            pitch, advance = ct.c_float(pitch).value, ct.c_float(advance).value
            fixture = check.ref.generate(name, 48000, 1)
            if name == "impulse":
                fixture[4800] = 0
                fixture[512] = 0.75
            if base.load(fixture) or split_core.load(fixture):
                raise ValueError("Fixture load failed")
            initial = bytes(split_core.state)
            count = limit or math.ceil(48000 / advance) + 64
            base.call("start", pitch, advance, 128)
            expected = base.render(count)
            repeats = []
            for _repeat in range(2):
                engine.core.poke(0x200C1000, initial, 1)
                if call(2, pitch=pitch, advance=advance)[0]:
                    raise ValueError("Target start failed")
                pcm = bytearray()
                for offset in range(0, count, 64):
                    n = min(64, count - offset)
                    engine.core.poke(0x200E03FC, struct.pack("<I", 0x12345678), 1)
                    engine.core.poke(
                        0x200E0400 + n * 4, struct.pack("<I", 0x12345678), 1
                    )
                    position = call(3, n)[0]
                    if (
                        engine.core.peek(0x200E03FC) != 0x12345678
                        or engine.core.peek(0x200E0400 + n * 4) != 0x12345678
                    ):
                        raise ValueError("Target output overrun")
                    pcm.extend(peek_bytes(0x200E0400, n * 4))
                duration = math.ceil(48000 / advance)
                if position != min(count, duration):
                    raise ValueError("Target duration/position mismatch")
                ideal_w = struct.unpack("<i", peek_bytes(0x200C1000 + 49164, 4))[0]
                ideal_f = struct.unpack("<I", peek_bytes(0x200C1000 + 49176, 4))[0]
                if ideal_w + ideal_f / 2**24 != position * advance:
                    raise ValueError("Target accumulated cursor drift")
                if peek_bytes(0x200C1000, 49152) != initial[:49152]:
                    raise ValueError("Target altered keyframes")
                repeats.append(bytes(pcm))
            if repeats[0] != repeats[1]:
                raise ValueError("Target reset/repeat mismatch")
            mx, rms = check.error(expected, repeats[0])
            case = dict(
                signal=name,
                pitch=pitch,
                advance=advance,
                frames=count,
                max_error=mx,
                rms_error=rms,
                passed=mx <= 1e-4 and rms <= 1e-5,
            )
            report["cases"].append(case)
            (out / f"case-{index}.f32").write_bytes(repeats[0])
            check.ref.save_wav(out / f"case-{index}.wav", repeats[0])
            print(json.dumps(case), flush=True)
            (out / "progress.json").write_text(json.dumps(report, indent=2) + "\n")
        # Invalid controls and explicit stop must silence an otherwise loaded voice.
        engine.core.poke(0x200C1000, initial, 1)
        for pitch, advance, leash in [
            (float("nan"), 1, 128),
            (1, float("inf"), 128),
            (0.1, 1, 128),
            (1, 1, 129),
        ]:
            if call(2, pitch=pitch, advance=advance, leash=leash)[0] != 3:
                raise ValueError("Target accepted invalid control")
            call(3, 64)
            if peek_bytes(0x200E0400, 256) != bytes(256):
                raise ValueError("Target invalid control leaked audio")
        if call(2)[0]:
            raise ValueError("Target restart failed")
        call(3, 64)
        call(4)
        if call(3, 64)[0] != 64 or peek_bytes(0x200E0400, 256) != bytes(256):
            raise ValueError("Target stop leaked or advanced")
        report["target_lifecycle_checks"] = "passed"
        block_counts.sort()
        report["block_instructions"] = dict(
            count=len(block_counts),
            minimum=block_counts[0],
            median=block_counts[len(block_counts) // 2],
            p99=block_counts[int(0.99 * (len(block_counts) - 1))],
            maximum=block_counts[-1],
        )
        report["reader_status"] = (
            "passed" if all(c["passed"] for c in report["cases"]) else "failed"
        )
        report.update(
            status="passed"
            if all(c["passed"] for c in report["cases"])
            and not report["analyzer_mismatches"]
            else "partial",
            core_audio_compiled=True,
            hardware_timing_verified=False,
        )
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        if isinstance(exc, subprocess.CalledProcessError):
            report["output"] = exc.output
        raise
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k not in ("commands", "source_hashes")
                },
                indent=2,
            )
        )

    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    sys.exit(main())
