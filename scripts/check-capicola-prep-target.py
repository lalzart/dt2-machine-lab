#!/usr/bin/env python3
"""Execute the bounded native PCM bank worker on SHARC."""

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
                ROOT / "machines/capicola/prepare-target.c",
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
        host_spec = importlib.util.spec_from_file_location(
            "prep_check", ROOT / "scripts/check-capicola-prep.py"
        )
        host = importlib.util.module_from_spec(host_spec)
        host_spec.loader.exec_module(host)
        report["source_hashes"] = host.fingerprints()
        lib, ref = host.build(out)

        def peek(address, size):
            return b"".join(
                struct.pack("<I", engine.core.peek(address + i))
                for i in range(0, size, 4)
            )

        max_instructions = 0

        def call(op, n=0, stride=1, token=1):
            nonlocal max_instructions
            engine.core.poke(
                0x200E0000, struct.pack("<8i", op, n, stride, token, 0, 0, 0, 0), 1
            )
            before = engine.core.stats()["instructions"]
            engine.call(0xBC0000, 10000000)
            max_instructions = max(
                max_instructions, engine.core.stats()["instructions"] - before
            )
            return struct.unpack("<4i", peek(0x200E0010, 16))

        report["cases"] = []
        for name in ("silence", "impulse", "sine", "two-tone", "noise"):
            values = host.fixture(name, 1024)
            sample = ref.Sample(lib, [v / 32768 for v in values])
            for stride in (1, 2):
                raw = [x for v in values for x in ([v] if stride == 1 else [v, -v])]
                engine.core.poke(
                    0x200E8000, struct.pack("<" + str(len(raw)) + "h", *raw), 1
                )
                call(0)
                assert call(1, len(values), stride)[0] == 1
                while True:
                    phase, index, needed, count = call(2, 256)
                    if phase != 1:
                        break
                assert phase == 2 and count == 0
                assert needed == sample.bank.count, (name, needed, sample.bank.count)
                engine.core.poke(0x82FFFFFC, struct.pack("<I", 0x12345678), 1)
                engine.core.poke(
                    0x83000000 + needed * 12, struct.pack("<I", 0x12345678), 1
                )
                assert call(3, needed)[0] == 3
                while True:
                    phase, index, _, count = call(2, 256)
                    if phase != 3:
                        break
                assert phase == 4 and count == needed
                assert engine.core.peek(0x82FFFFFC) == 0x12345678
                assert engine.core.peek(0x83000000 + needed * 12) == 0x12345678
                payload = peek(0x83000000, count * 12)
                expected = sample.payload()
                actual_values = struct.unpack(
                    "<" + str(count) + "f", payload[: count * 4]
                )
                expected_values = struct.unpack(
                    "<" + str(count) + "f", expected[: count * 4]
                )
                value_error = max(
                    abs(a - b)
                    for a, b in zip(actual_values, expected_values, strict=True)
                )
                # Record timestamp drift rather than silently treating it as exact.
                aw = struct.unpack(
                    "<" + str(count) + "i", payload[count * 4 : count * 8]
                )
                af = struct.unpack("<" + str(count) + "I", payload[count * 8 :])
                ew = struct.unpack(
                    "<" + str(count) + "i", expected[count * 4 : count * 8]
                )
                ef = struct.unpack("<" + str(count) + "I", expected[count * 8 :])
                time_error = max(
                    abs((a - b) + (c - d) / 16777216)
                    for a, b, c, d in zip(aw, ew, af, ef, strict=True)
                )
                call(5)
                reader = ref.Reader(sample)
                reader.start(ct.c_float(1.1).value, ct.c_float(0.7).value)
                output = []
                for _ in range(24):
                    call(6, 64)
                    output.extend(struct.unpack("<64f", peek(0x200E0400, 256)))
                reference = struct.unpack("<1536f", reader.render(1536))
                errors = [a - b for a, b in zip(output, reference, strict=True)]
                mx = max(map(abs, errors))
                rms = math.sqrt(sum(e * e for e in errors) / len(errors))
                report["cases"].append(
                    dict(
                        name=name,
                        stride=stride,
                        keys=count,
                        value_error=value_error,
                        time_error=time_error,
                        max_error=mx,
                        rms_error=rms,
                    )
                )
                if mx > 1e-4 or rms > 1e-5 or time_error > 1 / 16777216:
                    raise ValueError(
                        "Native analyzer equivalence failed: "
                        + str(report["cases"][-1])
                    )
                call(5)
                repeat = []
                for _ in range(24):
                    call(6, 64)
                    repeat.extend(struct.unpack("<64f", peek(0x200E0400, 256)))
                assert repeat == output, "Target replay differs"
                call(1, len(values), stride)
                call(6, 64)
                assert peek(0x200E0400, 256) == bytes(256), (
                    "Stale reader was not silenced"
                )
                assert call(2, 1, token=2)[0] == 5
                call(1, len(values), stride)
                assert call(4)[0] == 0
        assert host.fingerprints() == report["source_hashes"], "Source drift"
        report.update(status="passed", max_call_instructions=max_instructions)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
