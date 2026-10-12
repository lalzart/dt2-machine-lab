#!/usr/bin/env python3
"""Execute the twelve-second shared-bank reader in a standalone SHARC arena."""

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
                ROOT / "machines/capicola/capacity-target.c",
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
        external_lo, external_hi = 0x82FFFF00, 0x83000000 + 576004 * 12 + 256
        for lo, hi in zip(memory._segments[0], memory._segments[1], strict=True):
            if lo < external_hi and hi > external_lo:
                raise ValueError("External test bank overlaps stock loader")
        blob = (
            stock[:split]
            + header(0x20080000, len(arena))
            + arena
            + header(external_lo, external_hi - external_lo)
            + bytes(external_hi - external_lo)
            + stock[split:]
        )
        engine = Dsp(blob)
        spec = importlib.util.spec_from_file_location(
            "capacity_check", ROOT / "scripts/check-capicola-capacity.py"
        )
        check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check)
        lib, oracle, _old = check.build(out)
        report.update(
            source_hashes=check.source_hashes(),
            code_bytes=len(code),
            data_bytes=len(data),
            cases=[],
            bank_address="0x83000000",
            bank_placement="Standalone emulator reservation only, not firmware memory ownership",
            analyzer_boundary="Host-analyzed banks; previous target analyzer discrepancy remains unresolved",
        )
        block_counts = []

        def peek_bytes(address, count):
            return b"".join(
                struct.pack("<I", engine.core.peek(address + i))
                for i in range(0, count, 4)
            )

        def call(command, count=0, leash=128, pitch=1, advance=1, generation=0):
            engine.core.poke(
                0x200E0000,
                struct.pack(
                    "<8i", command, count, leash, generation, -999, -999, -999, -999
                ),
                1,
            )
            engine.core.poke(0x200E0100, struct.pack("<2f", pitch, advance), 1)
            before = engine.core.stats()["instructions"]
            engine.call(0xBC0000, 10000000)
            if command == 3:
                block_counts.append(engine.core.stats()["instructions"] - before)
            return struct.unpack("<4i", peek_bytes(0x200E0010, 16))

        layout = call(0)
        if layout[:3] != (76, 32, 72):
            raise ValueError(f"Target layout mismatch: {layout}")
        report.update(
            target_reader_bytes=layout[0], target_bank_metadata_bytes=layout[1]
        )
        duration_cases = 0
        for frames in [1, 48000, 262144, 575999, 576000]:
            for rate in [0.5, 0.7, 1, 1.1, 2]:
                rate = ct.c_float(rate).value
                if call(7, frames, advance=rate)[0] != math.ceil(frames / rate):
                    raise ValueError("Target duration arithmetic")
                duration_cases += 1
        report["target_duration_cases"] = duration_cases
        jobs = [
            ("sine", 0.7, 2, 0, None),
            ("noise", 1.1, 0.7, 0, 4096),
            ("noise", 1.1, 0.7, "tail", 4160),
            ("noise", 1.1, 0.5, "tail", 4160),
            ("sine", 1.1, 0.7, "tail", 4160),
        ]
        for index, (name, pitch, advance, offset, limit) in enumerate(jobs):
            pitch, advance = ct.c_float(pitch).value, ct.c_float(advance).value
            data = check.fixture(name)
            sample = check.Sample(lib, data)
            if sample.result:
                raise ValueError("Bank preparation failed")
            bank_bytes = sample.payload()
            nkeys = sample.bank.count
            engine.core.poke(0x83000000, bank_bytes, 1)
            engine.core.poke(0x82FFFFFC, struct.pack("<I", 0x12345678), 1)
            engine.core.poke(
                0x83000000 + len(bank_bytes), struct.pack("<I", 0x12345678), 1
            )
            if call(1, nkeys, leash=576000, generation=sample.bank.generation)[0]:
                raise ValueError("Target bank bind")
            duration = math.ceil(576000 / advance)
            offset = duration - 4096 if offset == "tail" else offset
            count = limit or duration + 64
            reader = check.Reader(sample)
            reader.start(pitch, advance)
            if offset:
                reader.render(offset)
            # Replace host 64-bit pointer with target pointer; scalar layout is identical.
            target_seed = struct.pack("<I", 0x200C1100) + bytes(reader.state)[8:]
            if len(target_seed) != 76:
                raise ValueError("Checkpoint layout mismatch")
            if oracle.load(data):
                raise ValueError("Oracle load")
            oracle.call("start", pitch, advance, 128)
            if offset:
                oracle.render(offset, 4096)
            expected = oracle.render(count, 4096)
            repeats = []
            for repeat in range(2):
                if call(2, pitch=pitch, advance=advance)[0]:
                    raise ValueError("Target start")
                if offset:
                    engine.core.poke(0x200C1000, target_seed, 1)
                pcm = bytearray()
                for at in range(0, count, 64):
                    n = min(64, count - at)
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
                    if at and at % 65536 == 0:
                        print(
                            f"case {index}, repeat {repeat}: {at}/{count} frames",
                            flush=True,
                        )
                if position != min(duration, offset + count):
                    raise ValueError("Target stop position")
                whole = struct.unpack("<i", peek_bytes(0x200C1008, 4))[0]
                fraction = struct.unpack("<I", peek_bytes(0x200C1014, 4))[0]
                if whole + fraction / 2**24 != position * advance:
                    raise ValueError("Target cursor drift")
                repeats.append(bytes(pcm))
            if repeats[0] != repeats[1]:
                raise ValueError("Target repeat")
            if peek_bytes(0x83000000, len(bank_bytes)) != bank_bytes:
                raise ValueError("Target bank mutated")
            if (
                engine.core.peek(0x82FFFFFC) != 0x12345678
                or engine.core.peek(0x83000000 + len(bank_bytes)) != 0x12345678
            ):
                raise ValueError("Bank guard overwritten")
            mx, rms = check.previous.error(expected, repeats[0])
            values = struct.unpack("<" + str(count) + "f", repeats[0])
            audible_samples = sum(abs(v) > 1e-5 for v in values)
            if name == "noise" and audible_samples < 100:
                raise ValueError("Dense window did not exercise audible output")
            case = dict(
                audible_samples=audible_samples,
                signal=name,
                pitch=pitch,
                advance=advance,
                offset=offset,
                frames=count,
                keys=nkeys,
                bank_bytes=len(bank_bytes),
                seeded=bool(offset),
                max_error=mx,
                rms_error=rms,
                passed=mx <= 1e-4 and rms <= 1e-5,
            )
            report["cases"].append(case)
            (out / f"case-{index}.f32").write_bytes(repeats[0])
            check.ref.save_wav(out / f"case-{index}.wav", repeats[0])
            print(json.dumps(case), flush=True)
            (out / "progress.json").write_text(json.dumps(report, indent=2) + "\n")
        # A bank replacement must silence a currently active reader.
        if call(2)[0]:
            raise ValueError("Restart before invalidation")
        call(3, 64)
        if call(6)[0] != 1:
            raise ValueError("Invalid load accepted")
        if call(3, 64)[0] != 64 or peek_bytes(0x200E0400, 256) != bytes(256):
            raise ValueError("Stale bank read")
        report["target_generation_invalidation"] = "passed"
        block_counts.sort()
        report["block_instructions"] = dict(
            count=len(block_counts),
            median=block_counts[len(block_counts) // 2],
            p99=block_counts[int(0.99 * (len(block_counts) - 1))],
            maximum=block_counts[-1],
        )
        report.update(
            status="passed" if all(c["passed"] for c in report["cases"]) else "failed",
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
