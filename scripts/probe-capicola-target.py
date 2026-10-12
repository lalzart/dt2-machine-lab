#!/usr/bin/env python3
"""Measure pinned SHARC double semantics before attempting the Capicola core."""

# ruff: noqa: E402, I001
# lab.runtime must install the pinned DigiKit import paths before SHARC imports.
import argparse
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
    from sharc_selache import compare_listing, find_elf_section, swap_parcels
    import sharcldr

    compiler = ROOT / "out/cache/selache-c99/release/selcc"
    tools = SELACHE / "target/release"
    report = {
        "status": "running",
        "boundary": "Standalone numeric ABI probe, not Capicola audio execution",
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
        (out / "probe.c").write_text("""void kernel(float *job) {
    volatile double *v=(volatile double *)0x200e0100;
    job[0]=(float)sizeof(double);
    job[1]=(float)(v[0]-v[1]);
}
""")
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
                out / "probe.c",
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
        stock = STOCK_BLOB.read_bytes()
        blocks = sharcldr.parse_blocks(stock)
        memory = sharcldr.LoadedMemory.from_stream(stock)
        for lo, hi in zip(memory._segments[0], memory._segments[1], strict=True):
            if lo < 0x200F0000 and hi > 0x20080000:
                raise ValueError("Probe arena overlaps stock loader")
        arena = bytearray(0x70000)
        arena[: len(code)] = code
        split = blocks[-1]["offset"]
        if blocks[-1]["byte_count"] or blocks[-1]["flags"] != ["bit0", "FINAL"]:
            raise ValueError("Unexpected loader ending")
        blob = stock[:split] + header(0x20080000, len(arena)) + arena + stock[split:]
        engine = Dsp(blob)
        # Determine storage size with all-zero inputs, then encode a cancellation
        # pair in that ABI. This avoids interpreting float32 bytes as float64.
        engine.core.poke(0x200E0100, bytes(16), 1)
        engine.call(0xBC0000, 10000)
        width = struct.unpack("<f", struct.pack("<I", engine.core.peek(0x200E0000)))[0]
        if width not in (4, 8):
            raise ValueError(f"Unexpected sizeof(double): {width}")
        engine.core.poke(
            0x200E0100,
            struct.pack("<2f" if width == 4 else "<2d", 16777217, 16777216),
            1,
        )
        engine.call(0xBC0000, 10000)
        diff = struct.unpack("<f", struct.pack("<I", engine.core.peek(0x200E0004)))[0]
        report.update(
            status="blocked" if width != 8 or diff != 1 else "passed",
            double_bytes=int(width),
            wide_difference=diff,
            expected_double_bytes=8,
            expected_difference=1,
            reason="Pinned compiler narrows double despite -double-size-64; full core port must not proceed with silent precision loss."
            if width != 8
            else "Double probe passed",
            core_audio_compiled=False,
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
            json.dumps({k: v for k, v in report.items() if k != "commands"}, indent=2)
        )

    return 2 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    sys.exit(main())
