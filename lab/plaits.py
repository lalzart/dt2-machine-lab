"""Experimental Plaits build helpers; kept separate from the SINE baseline."""

import hashlib
import json
import re
import subprocess

from lab.dsp import assemble, header
from lab.runtime import OUT, ROOT, SELACHE, STOCK_BLOB

MACHINE = ROOT / "machines/plaits-va"
COMPILER = ROOT / "out/cache/selache-c99/release/selcc"
TOOLS = SELACHE / "target/release"


def command(args):
    return subprocess.check_output([str(a) for a in args], text=True, timeout=120)


def compile_target(integrated=False, *, variant="reference", output=None):
    """No dependencies edited; inspect actual emitted/linked instruction extents."""
    from sharc_selache import compare_listing, find_elf_section, swap_parcels

    if variant not in ("reference", "main-only", "shared"):
        raise ValueError(f"Unknown Plaits variant: {variant}")
    if variant == "shared" and not integrated:
        raise ValueError("Lane sharing requires the firmware wrapper")
    out = output or OUT
    out.mkdir(parents=True, exist_ok=True)

    if not COMPILER.is_file():
        command(
            [
                "cargo",
                "build",
                "--release",
                "--locked",
                "--manifest-path",
                SELACHE / "Cargo.toml",
                "--target-dir",
                ROOT / "out/cache/selache-c99",
                "-p",
                "selcc",
            ]
        )
    source = MACHINE / ("machine.c" if integrated else "target.c")
    if variant != "reference":
        # A translation unit keeps compiler-specific -D handling out of this
        # experiment. The default source and build path remain the reference.
        defines = "#define PLAITS_MAIN_ONLY 1\n"
        if variant == "shared":
            defines += "#define PLAITS_SHARE_LANES 1\n"
        unit = out / "variant.c"
        unit.write_text(defines + f'#include "{source}"\n')
        source = unit
    command(
        [
            COMPILER,
            "-proc",
            "ADSP-21569",
            "-O1",
            "-S",
            "-o",
            out / "kernel-original.s",
            source,
        ]
    )
    assembly = (out / "kernel-original.s").read_text()
    # Full-width RFRAME is not emitted correctly by the current assembler.
    # Only expand the known problematic stand-alone integer ADD instructions.
    assembly = re.sub(
        r"(?m)^(\s*R\d+ = R\d+ \+ R\d+;)$", r".NOCOMPRESS;\n\1\n.COMPRESS;", assembly
    )
    (out / "kernel.s").write_text(assembly)
    wrapper = ".SECTION/PM seg_pmco;\n.GLOBAL start;\n"
    if integrated:
        wrapper += ".EXTERN machine.;\nstart:\nDM(-5,I6)=R0;\n"
        # Preserve the enclosing stock function's register context. A private
        # stack avoids depending on its local-frame capacity and C compiler ABI.
        regs = [f"{kind}{i}" for kind in ("R", "I", "M", "L") for i in range(16)]
        # DM absolute stores accept universal registers through an R temporary.
        wrapper += "DM(0x200e0800)=R0;\n"
        for i, reg in enumerate(regs[1:], 1):
            wrapper += f"R0={reg}; DM({hex(0x200E0800 + 4 * i)})=R0;\n"
        wrapper += "R4=I4;\nM5=0; M6=1; M7=-1; M14=1; L0=0; L1=0; L2=0; L3=0; L4=0; L5=0; L6=0; L7=0; L8=0; L9=0; L10=0; L11=0; L12=0; L13=0; L14=0; L15=0;\nI7=0x200dff00; I6=I7; R2=I6;\nCJUMP machine. (DB);\nDM(I7,M7)=R2; DM(I7,M7)=returned-1;\nreturned:\nDM(0x200e0900)=R0;\n"
        for i, reg in reversed(list(enumerate(regs[1:], 1))):
            wrapper += f"R0=DM({hex(0x200E0800 + 4 * i)}); {reg}=R0;\n"
        wrapper += "R0=DM(0x200e0900); R1=0; COMP(R0,R1); IF EQ JUMP stock;\nR1=DM(0x200e0804); R0=DM(0x200e0800); JUMP 0x1c524a;\nstock:\nR1=DM(0x200e0804); R0=DM(0x200e0800);\nNOP; NOP; NOP;\nJUMP 0x1c4f18;\n"
    else:
        wrapper += (
            ".EXTERN kernel.;\nstart:\nM5=0; M6=1; M7=-1; M13=0; M14=1; M15=-1;\n"
        )
        wrapper += " ".join(f"L{i}=0;" for i in range(8))
        wrapper += "\nI7=0x200dff00; I6=I7; R4=0x200e0000;\nJUMP kernel. (DB);\nDM(I7,M7)=0; DM(I7,M7)=done-1;\ndone: RTS;\n"
    (out / "wrapper.s").write_text(wrapper)
    (out / "memory.ldf").write_text("""ARCHITECTURE(ADSP-21569)
MEMORY {
 code { TYPE(BW RAM) START(0x20080000) END(0x200bffff) WIDTH(8) }
 data { TYPE(BW RAM) START(0x200c0000) END(0x200cffff) WIDTH(8) }
}
PROCESSOR core0 { OUTPUT($COMMAND_LINE_OUTPUT_FILE) ENTRY(start)
 SECTIONS {
  code SW { INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_pmco seg_swco seg_l1_block0_swco seg_l1_block1_swco seg_l2_swco)) } > code
  data BW { INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_dmda seg_l2 seg_l1_bss seg_l2_bss)) } > data
 }
}
""")
    for stem in ("wrapper", "kernel"):
        command(
            [
                TOOLS / "selas",
                "-proc",
                "ADSP-21569",
                "-o",
                out / f"{stem}.doj",
                out / f"{stem}.s",
            ]
        )
    command(
        [
            TOOLS / "seld",
            "-proc",
            "ADSP-21569",
            "-T",
            out / "memory.ldf",
            "-o",
            out / "plaits.dxe",
            out / "wrapper.doj",
            out / "kernel.doj",
        ]
    )
    listing = command([TOOLS / "seldump", "-ns", "code", out / "plaits.dxe"])
    (out / "listing.txt").write_text(listing)
    if not compare_listing(listing).all_extents_agree:
        raise ValueError("Plaits linked instruction width disagreement")
    code = swap_parcels(find_elf_section(out / "plaits.dxe", "code"))
    data = find_elf_section(out / "plaits.dxe", "data")
    return code, data


def build_blob(integrated=False, *, variant="reference", output=None):
    import sharcldr

    from lab.runtime import PROFILE

    out = output or OUT
    code, data = compile_target(integrated, variant=variant, output=out)
    raw = bytearray(STOCK_BLOB.read_bytes())
    if hashlib.sha256(raw).hexdigest() != PROFILE["stock_blob_sha256"]:
        raise ValueError("Unexpected stock DSP image")
    blocks = sharcldr.parse_blocks(raw)
    memory = sharcldr.LoadedMemory.from_stream(raw, blocks)
    for lo, hi in zip(memory._segments[0], memory._segments[1], strict=True):
        if lo < 0x200F2000 and hi > 0x20080000:
            raise ValueError("Experimental arena overlaps a stock loader segment")
    if integrated:
        hook = sharcldr.offset_for_address(blocks, 0x1C4F15)
        displaced = bytes(raw[hook : hook + 6])
        if displaced.hex() != "5499a801408c":
            raise ValueError("Unexpected voice hook bytes")
        tail = assemble(".section/pm seg_pmco;\nJUMP 0x1c4f18;\n").boot_bytes
        marker = bytes.fromhex("010001000100") + tail
        if code.count(marker) != 1:
            raise ValueError("Expected exactly one stock fallback placeholder")
        code = code.replace(marker, displaced + tail)
        raw[hook : hook + 6] = assemble(
            ".section/pm seg_pmco;\nJUMP 0xbc0000;\n"
        ).boot_bytes
        offset = sharcldr.offset_for_address(blocks, 0x1C2731)
        expected = assemble(".section/pm seg_pmco;\nI3=0x2567c0;\n").boot_bytes
        if raw[offset : offset + 6] != expected:
            raise ValueError("Unexpected remap pointer bytes")
        raw[offset : offset + 6] = assemble(
            ".section/pm seg_pmco;\nI3=0x200f0000;\n"
        ).boot_bytes
    import struct

    arena = bytearray(0x72000)
    if len(code) > 0x40000 or len(data) > 0x10000:
        raise ValueError("Plaits placement overflow")
    arena[: len(code)] = code
    arena[0x40000 : 0x40000 + len(data)] = data
    arena[0x70000:0x70020] = struct.pack("<8I", 0, 1, 2, 3, 4, 0, 5, 5)
    split = blocks[-1]["offset"]
    if blocks[-1]["flags"] != ["bit0", "FINAL"] or blocks[-1]["byte_count"]:
        raise ValueError("Unexpected final loader block")
    result = (
        bytes(raw[:split]) + header(0x20080000, len(arena)) + arena + bytes(raw[split:])
    )
    parsed = sharcldr.parse_blocks(result)
    if parsed[-1]["payload_offset"] != len(result):
        raise ValueError("Bad candidate loader stream")
    (out / "PLAITS_BLOB.bin").write_bytes(result)
    (out / "build.json").write_text(
        json.dumps(
            {
                "code_bytes": len(code),
                "data_bytes": len(data),
                "arena_bytes": len(arena),
                "compiler_sha256": hashlib.sha256(COMPILER.read_bytes()).hexdigest(),
                "integrated": integrated,
                "variant": variant,
                "lane_state_bytes": 768 if integrated else 252,
                "render_cache_bytes": 1036 if variant == "shared" else 0,
                "placement": "emulator-only; stock loader disjointness is not runtime memory ownership",
            },
            indent=2,
        )
        + "\n"
    )
    return result


def build_cpu():
    """A named type-7 CPU candidate. The current replay capture predates this label."""
    import machinebuild
    import machinepatch
    import machineprofile

    from lab.runtime import PROFILE, STOCK_MAIN

    digest, profile = machineprofile.profile_for(STOCK_MAIN)
    if digest != PROFILE["stock_main_sha256"] or profile is not machineprofile.DT2_116:
        raise ValueError("Unexpected CPU firmware")
    spec = machinepatch.MachineSpec(
        name="P-VA",
        short="PVA",
        desc_name="P-VA",
        desc_short="PVA",
        clone_of=6,
        fields=PROFILE["cpu"]["descriptor_fields"],
    )
    writes, data = machinebuild.plan_and_verify(
        STOCK_MAIN, profile, spec, machinepatch.PARTS
    )
    (OUT / "PLAITS_MAIN_OS.bin").write_bytes(data)
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "writes": len(writes),
        "machine_id": 7,
        "name": "P-VA",
        "scope": "Image construction only; current real CPU capture still uses inherited SINE label/type 7",
    }
