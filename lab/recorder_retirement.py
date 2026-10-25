"""Isolated instruction-level request/reader observer; never authorizes reuse."""

import hashlib
import re
import struct

from lab.emit import Code
from lab.project import ROOT, read_json, require, sha256, write_json

MACHINE = ROOT / "machines/recorder-observer"
CF_BASE, CF_ENTRY, CF_PACKET = 0x10800000, 0x10800100, 0x10801000
CODE_BASE, STATE_END = 0x20080000, 0x200F8000
FRAME_SITE, EVENT_SITE = 0x1C75C5, 0x1C7E35
FRAME_BEFORE, EVENT_BEFORE = "089c6f09089cf009", "041026004082"
FRAME_SCRATCH, EVENT_SCRATCH = 0x200F4800, 0x200F4C00
FRAME_STACK, EVENT_STACK = 0x200F6F00, 0x200F7F00


def contract():
    c = read_json(MACHINE / "contract.json")
    require(c["status"] == "ready", "Observer contract is not ready")
    require(sha256(ROOT / c["proposal"]) == c["proposal_sha256"], "Proposal drift")
    require(c["dependencies"] == read_json(ROOT / "deps.lock.json"), "Dependency drift")
    for key in (
        "source_equivalence",
        "experiment",
        "controls",
        "state_matrix",
        "validation",
        "results",
        "gaps",
        "decisions",
        "approval",
    ):
        require(bool(c[key]), "Incomplete observer contract: " + key)
    require(len(c["experiment"]["conditions"]) == 16, "Observer experiment drift")
    require(0x19200 <= c["constants"]["TAG"] < 0x80000000, "Unsafe LP0 tag")
    return c


def constants():
    return contract()["constants"]


def packet(epoch, generation, seq, offset, size):
    """Independent host encoding oracle, not a native sender or commit."""
    k = constants()
    return (
        struct.pack(
            ">8I",
            k["TAG"],
            k["VERSION"],
            epoch,
            generation,
            seq,
            offset,
            size,
            seq ^ 0xFFFFFFFF,
        )
        + bytes(28)
        + struct.pack(">I", k["MARKER"])
        + bytes(4032)
    )


def sender():
    """Native diagnostic CF send(epoch,id,seq,logical_start,bytes)."""
    k = constants()
    c = Code()
    c.emit("4feffff0 48d70c0c")
    for offset in (20, 28):
        c.emit(f"202f{offset:04x} 4a80")
        c.branch(7, "bad")
    c.emit("202f0018")
    for limit, cond in ((k["FIRST_ID"], 5), (k["LAST_ID"], 2)):
        c.imm("0c80", limit)
        c.branch(cond, "bad")
    c.emit("202f0020")
    for limit, cond in ((k["POOL_START"], 5), (k["POOL_END"], 4)):
        c.imm("0c80", limit)
        c.branch(cond, "bad")
    c.imm("0680", -k["POOL_START"])
    c.imm("0280", 8191)
    c.branch(6, "bad")
    c.emit("202f0024 4a80")
    c.branch(7, "bad")
    c.imm("0280", 8191)
    c.branch(6, "bad")
    c.imm("203c", k["POOL_END"])
    c.emit("222f0020 9081 222f0024 b081")
    c.branch(5, "bad")
    c.imm("41f9", CF_PACKET)
    c.emit("7000")
    c.imm("223c", 1024)
    c.label("zero")
    c.emit("20c0")
    c.imm("0681", -1)
    c.branch(6, "zero")
    c.imm("45f9", CF_PACKET)
    for index, value in ((0, k["TAG"]), (1, k["VERSION"]), (15, k["MARKER"])):
        c.imm("203c", value)
        c.emit(f"2540{index * 4:04x}")
    for index in range(5):
        c.emit(f"202f{20 + index * 4:04x} 2540{8 + index * 4:04x}")
    c.emit("70ff 222f001c 9081 2540001c 7001 2f00 2f0a")
    c.imm("4879", k["TAG"])
    c.imm("4eb9", 0x400CD638)
    c.emit("4fef000c 7000")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(CF_ENTRY)


def wrappers():
    from lab.sharc_hooks import context_restores, context_stores

    def save(scratch):
        return (
            context_stores(scratch)
            + f"R0=ASTATX; DM({scratch + 0x104:#x})=R0; R0=ASTATY; DM({scratch + 0x108:#x})=R0;\n"
        )

    def restore(scratch, flags=True):
        text = context_restores(scratch)
        if flags:
            text += f"R0=DM({scratch + 0x108:#x}); ASTATY=R0; R0=DM({scratch + 0x104:#x}); ASTATX=R0;\n"
        return text + f"R0=DM({scratch:#x});\n"

    def invoke(label, fn, stack):
        return (
            "M5=0; M6=1; M7=-1; M14=1;\n"
            + " ".join(f"L{i}=0;" for i in range(16))
            + f"\nI7={stack:#x}; I6=I7; R2=I6;\nCJUMP {fn}. (DB);\nDM(I7,M7)=R2; DM(I7,M7)={label}_returned-1;\n{label}_returned:\n"
        )

    k = constants()
    text = ".SECTION/PM seg_pmco;\n.EXTERN observer_frame.;\n.EXTERN observer_latch.;\n.GLOBAL observer_frame_hook;\nobserver_frame_hook:\n"
    text += save(FRAME_SCRATCH) + invoke("frame", "observer_frame", FRAME_STACK)
    text += restore(FRAME_SCRATCH)
    text += "I2=DM(-17,I6); I3=DM(-16,I6); JUMP 0x1c75c9;\n"
    text += ".GLOBAL observer_event_hook;\nobserver_event_hook:\nR4=DM(0x268240);\n"
    text += save(EVENT_SCRATCH)
    text += f"R0=R4; R1={k['TAG']:#x}; COMP(R0,R1); IF NE JUMP event_stock;\nR0=1; DM({EVENT_SCRATCH + 0x100:#x})=R0;\n"
    text += invoke("event", "observer_latch", EVENT_STACK)
    text += "JUMP event_restore;\nevent_stock:\nR0=0;\n"
    text += f"DM({EVENT_SCRATCH + 0x100:#x})=R0;\nevent_restore:\n"
    text += context_restores(EVENT_SCRATCH)
    text += f"R0=DM({EVENT_SCRATCH + 0x100:#x}); R1=0; COMP(R0,R1); R1=DM({EVENT_SCRATCH + 4:#x}); R0=DM({EVENT_SCRATCH:#x});\nIF EQ JUMP 0x1c7e38; JUMP 0x1c7e43;\n"
    text += (
        ".GLOBAL observer_direct;\nobserver_direct:\n"
        + invoke("direct", "observer_frame", FRAME_STACK)
        + "RTS;\n"
    )
    return text


def build(output):
    """Compile and append an isolated, guarded stock-image overlay."""
    import sharcldr
    from sharc_selache import compare_listing, find_elf_section, swap_parcels

    from lab.dsp_build import COMPILER, TOOLS, command
    from lab.runtime import STOCK_BLOB
    from lab.sharc_tools import assemble, header

    cfg = contract()
    require(sha256(STOCK_BLOB) == cfg["firmware"], "Wrong observer firmware")
    out = output
    out.mkdir(exist_ok=False)
    (out / "protocol.h").write_text(
        "\n".join(f"#define {k} {v:#x}u" for k, v in cfg["constants"].items()) + "\n"
    )
    (out / "observer.c").write_bytes((MACHINE / "observer.c").read_bytes())
    command(
        [
            COMPILER,
            "-proc",
            "ADSP-21569",
            "-O1",
            "-S",
            "-o",
            out / "kernel-original.s",
            out / "observer.c",
        ]
    )
    assembly = (out / "kernel-original.s").read_text()
    assembly = re.sub(
        r"(?m)^(\s*R\d+ = R\d+ \+ R\d+;)$", r".NOCOMPRESS;\n\1\n.COMPRESS;", assembly
    )
    (out / "kernel.s").write_text(assembly)
    (out / "wrapper.s").write_text(
        wrappers() + ".SECTION/DM seg_dmda;\n.VAR observer_anchor=0;\n"
    )
    (out / "memory.ldf").write_text("""ARCHITECTURE(ADSP-21569)
MEMORY {
 code { TYPE(BW RAM) START(0x20080000) END(0x200bffff) WIDTH(8) }
 data { TYPE(BW RAM) START(0x200f4000) END(0x200f47ff) WIDTH(8) }
}
PROCESSOR core0 { OUTPUT($COMMAND_LINE_OUTPUT_FILE) ENTRY(observer_direct)
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
            out / "observer.dxe",
            out / "wrapper.doj",
            out / "kernel.doj",
        ]
    )
    listing = command([TOOLS / "seldump", "-ns", "code", out / "observer.dxe"])
    (out / "listing.txt").write_text(listing)
    require(
        compare_listing(listing).all_extents_agree,
        "Observer instruction width disagreement",
    )
    code = swap_parcels(find_elf_section(out / "observer.dxe", "code"))
    data = find_elf_section(out / "observer.dxe", "data")
    require(len(code) <= 0x40000 and len(data) <= 0x800, "Observer arena exhausted")
    require(not any(data), "Unexpected observer static initializer")
    raw = bytearray(STOCK_BLOB.read_bytes())
    blocks = sharcldr.parse_blocks(raw)
    memory = sharcldr.LoadedMemory.from_stream(raw, blocks)
    for lo, hi in (
        (CODE_BASE, CODE_BASE + 0x40000),
        (cfg["constants"]["STATE"], STATE_END),
    ):
        require(
            not any(
                a < hi and b > lo
                for a, b in zip(memory._segments[0], memory._segments[1], strict=True)
            ),
            "Observer overlaps loaded memory",
        )
    symbols = {
        name: int(re.search(rf"(?m)^{name}\.:\n\s+([0-9a-f]+)", listing)[1], 16)
        for name in ("observer_frame_hook", "observer_event_hook", "observer_direct")
    }
    patches = []
    for site, before, name in (
        (FRAME_SITE, FRAME_BEFORE, "observer_frame_hook"),
        (EVENT_SITE, EVENT_BEFORE, "observer_event_hook"),
    ):
        off = sharcldr.offset_for_address(blocks, site)
        expected = bytes.fromhex(before)
        require(raw[off : off + len(expected)] == expected, "Observer patch site drift")
        jump = assemble(f".SECTION/PM seg_pmco;\nJUMP {symbols[name]:#x};\n").boot_bytes
        jump += assemble(".SECTION/PM seg_pmco;\nNOP;\n").boot_bytes * (
            (len(expected) - len(jump)) // 2
        )
        require(len(jump) == len(expected), "Observer patch extent")
        raw[off : off + len(jump)] = jump
        patches.append(
            dict(site=site, before=before, after=jump.hex(), target=symbols[name])
        )
    blob = (
        bytes(raw)
        + header(CODE_BASE, len(code))
        + code
        + header(
            cfg["constants"]["STATE"], STATE_END - cfg["constants"]["STATE"], fill=0
        )
    )
    (out / "OBSERVER_BLOB.bin").write_bytes(blob)
    metadata = dict(
        symbols=symbols,
        patches=patches,
        code_bytes=len(code),
        state_bytes=0x4000,
        blob_sha256=hashlib.sha256(blob).hexdigest(),
        contract_sha256=sha256(MACHINE / "contract.json"),
    )
    write_json(out / "build.json", metadata)
    return blob, metadata
