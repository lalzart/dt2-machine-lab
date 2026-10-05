"""Experimental Plaits build helpers; kept separate from the SINE baseline."""

import hashlib
import json
import re
import struct
import subprocess

from lab.dsp import assemble, header
from lab.runtime import OUT, ROOT, SELACHE, STOCK_BLOB

MACHINE = ROOT / "machines/plaits-va"
COMPILER = ROOT / "out/cache/selache-c99/release/selcc"
TOOLS = SELACHE / "target/release"


def command(args):
    return subprocess.check_output([str(a) for a in args], text=True, timeout=120)


def checked_trio_tables(assembly, source):
    """Repair the pinned compiler's integer negation of float array literals.

    Accept only the exact IEEE bits or the observed negated-positive-bit bug;
    never guess a correction for other output. Host source stays upstream exact.
    """
    for name, body in re.findall(
        r"static const float (\w+)\[\] = \{(.*?)\};", source.read_text(), re.S
    ):
        values = [float(v.strip()) for v in body.split(",") if v.strip()]
        pattern = r"\.VAR " + name + r"\. = [^;]+;(?:\n\.VAR = [^;]+;)*"
        match = re.search(pattern, assembly)
        if not match:
            raise ValueError(f"Missing emitted table: {name}")
        emitted = re.findall(r"= (0x[0-9A-Fa-f]+);", match[0])
        if len(emitted) != len(values):
            raise ValueError(f"Unexpected table extent: {name}")
        corrected = []
        for value, word in zip(values, emitted, strict=True):
            expected = struct.unpack("<I", struct.pack("<f", value))[0]
            buggy = (-(expected & 0x7FFFFFFF)) & 0xFFFFFFFF
            if int(word, 16) != expected and not (value < 0 and int(word, 16) == buggy):
                raise ValueError(f"Unexpected emitted value in {name}: {word}")
            corrected.append(f"0x{expected:08X}")
        replacement = f".VAR {name}. = {corrected[0]};" + "".join(
            f"\n.VAR = {word};" for word in corrected[1:]
        )
        assembly = assembly[: match.start()] + replacement + assembly[match.end() :]
    return assembly


def compile_target(integrated=False, *, variant="reference", output=None, family="va"):
    """No dependencies edited; inspect actual emitted/linked instruction extents."""
    from sharc_selache import compare_listing, find_elf_section, swap_parcels

    if variant not in ("reference", "main-only", "shared"):
        raise ValueError(f"Unknown Plaits variant: {variant}")
    if variant == "shared" and not integrated:
        raise ValueError("Lane sharing requires the firmware wrapper")
    if family not in ("va", "trio") or (family != "va" and variant != "reference"):
        raise ValueError("Unknown family or unsupported multi-model optimization")
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
    machine = ROOT / ("machines/plaits-" + family)
    source = machine / ("machine.c" if integrated else "target.c")
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
    if family in ("trio",):
        assembly = checked_trio_tables(assembly, ROOT / "machines/plaits-trio/tables.h")
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


def build_blob(integrated=False, *, variant="reference", output=None, family="va"):
    import sharcldr

    from lab.runtime import PROFILE

    out = output or OUT
    code, data = compile_target(integrated, variant=variant, output=out, family=family)
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
                "family": family,
                "lane_state_bytes": {
                    "va": (768 if integrated else 252),
                    "trio": (696 if integrated else 256),
                }[family],
                "render_cache_bytes": 1036 if variant == "shared" else 0,
                "placement": "emulator-only; stock loader disjointness is not runtime memory ownership",
            },
            indent=2,
        )
        + "\n"
    )
    return result


def build_cpu(*, family="va"):
    """A named type-7 CPU candidate. The current replay capture predates this label."""
    import machinebuild
    import machinepatch
    import machineprofile

    from lab.runtime import PROFILE, STOCK_MAIN

    digest, profile = machineprofile.profile_for(STOCK_MAIN)
    if digest != PROFILE["stock_main_sha256"] or profile is not machineprofile.DT2_116:
        raise ValueError("Unexpected CPU firmware")
    if family not in ("va", "trio"):
        raise ValueError("Unknown CPU machine family")
    name, short = ("P-VA", "PVA") if family == "va" else ("PLAITS", "PLT")
    fields = PROFILE["cpu"]["descriptor_fields"]
    if family in ("trio",):
        fields = (0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0, 0xFE, 0x0A)
    spec = machinepatch.MachineSpec(
        name=name,
        short=short,
        desc_name=name,
        desc_short=short,
        clone_of=6,
        fields=fields,
    )
    writes, data = machinebuild.plan_and_verify(
        STOCK_MAIN, profile, spec, machinepatch.PARTS
    )
    if family in ("trio",):
        # Dormant Manual Slice C row: no exposed stock descriptor uses 0xFA.
        # Keep shared PLAY/SAMP/SLICE metadata unchanged; only MODEL is dedicated.
        data = bytearray(data)
        base, row, label = 0x40000400, 0x40212C24, 0x40311CC4
        # MODEL is discrete. The stock one-pole mirror filter would turn a
        # model lock into an intermediate number at note-on. Bypass only
        # track 1 / type 7 / mirror 27 after the stock filter has completed.
        # D0 is caller-clobbered and restored to the displaced return value;
        # no other register or stock track/parameter is changed by this shim.
        shim = bytes.fromhex(
            "7000 103980003cd0 0c8000000007 660c "
            "303980003398 33c080005ba8 "
            "203c80005b50 4ef9400d934c"
        )
        controls = json.loads(
            (ROOT / f"machines/plaits-{family}/controls.json").read_text()
        )
        max_raw = controls["model"]["max_raw"]
        if max_raw != (len(controls["model_names"]) - 1) * 256:
            raise ValueError("MODEL range disagrees with control map")
        extra = [
            (row + 12, struct.pack(">I", 0x7F00), struct.pack(">I", max_raw)),
            (row + 40, struct.pack(">I", 0x40242AAC), struct.pack(">I", label)),
            (row + 48, struct.pack(">I", 0x40242AB6), struct.pack(">I", label + 6)),
            (label, bytes(12), b"Model\0MODEL\0"),
            (0x400D9346, bytes.fromhex("203c80005b50"), bytes.fromhex("4ef940311d04")),
            (0x40311D04, bytes(len(shim)), shim),
        ]
        for address, before, after in extra:
            off = address - base
            if data[off : off + len(before)] != before:
                raise ValueError(f"MODEL metadata guard failed at {address:#x}")
            data[off : off + len(after)] = after
    (OUT / "PLAITS_MAIN_OS.bin").write_bytes(data)
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "writes": len(writes) + (6 if family in ("trio",) else 0),
        "machine_id": 7,
        "name": name,
        "scope": "Image construction; UI and control transport require a separate capture",
    }
