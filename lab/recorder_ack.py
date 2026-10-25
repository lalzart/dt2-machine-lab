"""Isolated native receipt echo; no sample, identity or allocation retirement."""

import hashlib
import re

from lab import recorder_retirement as observer
from lab.emit import Code
from lab.project import ROOT, read_json, require, sha256, write_json

MACHINE = ROOT / "machines/recorder-ack"
CF_REQUEST, CF_CONSUME, CF_PUMP = 0x10900100, 0x10901000, 0x10901400
CF_EXPECTED = 0x10902100
EPOCH, GENERATION, SEQUENCE, START, SIZE = 4, 8, 12, 16, 20
PHASE, INDEX, AGE, MATCHES, REJECTS, TIMEOUTS = 24, 28, 32, 36, 40, 44


def contract():
    c = read_json(MACHINE / "contract.json")
    require(c["status"] == "ready", "Echo contract not ready")
    require(sha256(ROOT / c["proposal"]) == c["proposal_sha256"], "Echo proposal drift")
    require(c["dependencies"] == read_json(ROOT / "deps.lock.json"), "Dependency drift")
    for key in (
        "approval",
        "controls",
        "state_matrix",
        "source_equivalence",
        "experiment",
        "validation",
        "results",
        "gaps",
        "decisions",
        "working_artifact",
    ):
        require(bool(c[key]), "Incomplete echo contract: " + key)
    require(len(c["experiment"]["conditions"]) == 17, "Echo experiment drift")
    return c


def constants():
    return contract()["constants"]


def fragments(epoch, generation, sequence):
    """Independent encoding oracle, never a reply producer in the peer."""
    words = (epoch, generation, sequence)
    return bytes((i << 2) | ((words[i // 16] >> (2 * (i & 15))) & 3) for i in range(48))


def cpu():
    """Emit request, receive matcher and original-driver pump as CF instructions."""
    k = constants()
    state = k["CF_STATE"]

    def prologue(c):
        c.emit("4feffff0 48d70c0c")  # preserve D2/D3/A2/A3
        c.imm("47f9", state)

    def epilogue(c):
        c.emit("4cd70c0c 4fef0010 4e75")

    c = Code()
    prologue(c)
    c.emit("244f")  # A2 = stable argument frame
    for offset in (20, 28):
        c.emit(f"202a{offset:04x} 4a80")
        c.branch(7, "bad")
    # Epoch then sequence ordering; equal tuple/extent is idempotent.
    c.emit("202a0014 222b0004 b081")
    c.branch(5, "bad")
    c.branch(2, "send")
    c.emit("202a001c 222b000c b081")
    c.branch(5, "bad")
    c.branch(2, "send")
    for arg, field in ((24, GENERATION), (32, START), (36, SIZE)):
        c.emit(f"202a{arg:04x} 222b{field:04x} b081")
        c.branch(6, "bad")
    c.emit("7000")
    c.branch(0, "return")
    c.label("send")
    for offset in (36, 32, 28, 24, 20):
        c.emit(f"2f2a{offset:04x}")
    c.imm("4eb9", observer.CF_ENTRY)
    c.emit("4fef0014 4a80")
    c.branch(6, "return")
    for offset, field in (
        (20, EPOCH),
        (24, GENERATION),
        (28, SEQUENCE),
        (32, START),
        (36, SIZE),
    ):
        c.emit(f"202a{offset:04x} 2740{field:04x}")
    c.emit(f"7000 2740{PHASE:04x} 2740{INDEX:04x} 2740{AGE:04x}")
    # Fixed-size native encoding uses already-reviewed CF immediate shifts.
    # Construct privately, then mark pending last; no table is supplied by host.
    for i in range(k["FRAGMENTS"]):
        c.emit(f"202b{4 + 4 * (i // 16):04x}")
        c.emit("e488 " * (i & 15))
        c.imm("0280", 3)
        c.imm("0080", i << 2)
        c.imm("13c0", CF_EXPECTED + i)
    c.emit(f"7001 2740{PHASE:04x} 7000")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    epilogue(c)
    request = c.finish(CF_REQUEST)
    require(CF_REQUEST + len(request) <= CF_CONSUME, "Request code overlap")

    c = Code()
    prologue(c)
    c.emit(f"202b{PHASE:04x}")
    c.imm("0c80", 2)
    c.branch(7, "confirmed")
    c.imm("0c80", 3)
    c.branch(7, "expired")
    c.imm("0c80", 1)
    c.branch(6, "pending")
    c.emit(f"202b{AGE:04x}")
    c.imm("0680", 1)
    c.emit(f"2740{AGE:04x}")
    c.imm("0c80", k["TIMEOUT"])
    c.branch(4, "timeout")
    c.emit("7000")
    c.imm("1039", 0x8000488C + k["CF_REPLY_BYTE"])
    c.emit("2200 e489")  # fragment index D1 = byte >> 2
    c.imm("0c81", k["FRAGMENTS"])
    c.branch(4, "reject")
    c.emit(f"242b{INDEX:04x} b282")
    c.branch(7, "bits")
    c.emit("4a81")
    c.branch(6, "reject")
    c.label("bits")
    c.emit("2400 2001")
    c.imm("41f9", CF_EXPECTED)
    c.emit("d1c0 7000 1010")  # expected encoded byte at current index
    c.emit("b082")
    c.branch(6, "reject")
    c.imm("0681", 1)
    c.emit(f"2741{INDEX:04x}")
    c.imm("0c81", k["FRAGMENTS"])
    c.branch(6, "pending")
    c.emit(f"7002 2740{PHASE:04x} 202b{MATCHES:04x}")
    c.imm("0680", 1)
    c.emit(f"2740{MATCHES:04x}")
    c.label("confirmed")
    c.emit("7001")
    c.branch(0, "return")
    c.label("reject")
    c.emit(f"7000 2740{INDEX:04x} 202b{REJECTS:04x}")
    c.imm("0680", 1)
    c.emit(f"2740{REJECTS:04x}")
    c.label("pending")
    c.emit("7000")
    c.branch(0, "return")
    c.label("timeout")
    c.emit(f"7003 2740{PHASE:04x} 202b{TIMEOUTS:04x}")
    c.imm("0680", 1)
    c.emit(f"2740{TIMEOUTS:04x}")
    c.label("expired")
    c.emit("70ff")
    c.label("return")
    epilogue(c)
    consume = c.finish(CF_CONSUME)
    require(CF_CONSUME + len(consume) <= CF_PUMP, "Matcher code overlap")

    c = Code()
    for value in (0x8000488C, 0xABC, 0x80005348, 0x802):
        c.imm("4879", value)
    c.imm("4eb9", 0x400CD2BC)
    c.emit("4fef0010")
    c.imm("4ef9", CF_CONSUME)
    return {CF_REQUEST: request, CF_CONSUME: consume, CF_PUMP: c.finish(CF_PUMP)}


def build(output):
    """Append an isolated echo overlay to the unchanged observer experiment."""
    # isort: off
    from lab import runtime  # noqa: F401 -- install pinned tool import paths first

    import sharcldr
    from sharc_selache import compare_listing, find_elf_section, swap_parcels

    from lab.dsp_build import COMPILER, TOOLS, command
    from lab.sharc_hooks import context_restores, context_stores
    from lab.sharc_tools import assemble, header
    # isort: on

    c = contract()
    k = c["constants"]
    output.mkdir(exist_ok=False)
    raw, base = observer.build(output / "observer")
    text = (MACHINE / "echo.c").read_bytes()
    (output / "echo.c").write_bytes(text)
    (output / "protocol.h").write_text(
        "\n".join(f"#define {name} {value:#x}u" for name, value in k.items())
        + f"\n#define REQUEST_STATE {observer.constants()['STATE']:#x}u\n"
    )
    command(
        [
            COMPILER,
            "-proc",
            "ADSP-21569",
            "-O1",
            "-S",
            "-o",
            output / "kernel-original.s",
            output / "echo.c",
        ]
    )
    s = (output / "kernel-original.s").read_text()
    s = re.sub(r"(?m)^(\s*R\d+ = R\d+ \+ R\d+;)$", r".NOCOMPRESS;\n\1\n.COMPRESS;", s)
    (output / "kernel.s").write_text(s)
    scratch, stack = k["DSP_SCRATCH"], k["DSP_STACK"]
    wrapper = (
        ".SECTION/PM seg_pmco;\n.EXTERN echo_emit.;\n.GLOBAL echo_hook;\necho_hook:\n"
    )
    wrapper += context_stores(scratch)
    wrapper += f"R0=ASTATX; DM({scratch + 0x104:#x})=R0; R0=ASTATY; DM({scratch + 0x108:#x})=R0;\nR4=I4;\n"
    wrapper += "M5=0; M6=1; M7=-1; M14=1;\n"
    wrapper += " ".join(f"L{i}=0;" for i in range(16))
    wrapper += f"\nI7={stack:#x}; I6=I7; R2=I6;\nCJUMP echo_emit. (DB);\nDM(I7,M7)=R2; DM(I7,M7)=echo_returned-1;\necho_returned:\n"
    wrapper += context_restores(scratch)
    wrapper += f"R0=DM({scratch + 0x108:#x}); ASTATY=R0; R0=DM({scratch + 0x104:#x}); ASTATX=R0; R0=DM({scratch:#x});\n"
    wrapper += f"JUMP {base['symbols']['observer_frame_hook']:#x};\n"
    wrapper += ".SECTION/DM seg_dmda;\n.VAR echo_anchor=0;\n"
    (output / "wrapper.s").write_text(wrapper)
    (output / "memory.ldf").write_text("""ARCHITECTURE(ADSP-21569)
MEMORY {
 code { TYPE(BW RAM) START(0x200c0000) END(0x200c3fff) WIDTH(8) }
 data { TYPE(BW RAM) START(0x200f8000) END(0x200f87ff) WIDTH(8) }
}
PROCESSOR core0 { OUTPUT($COMMAND_LINE_OUTPUT_FILE) ENTRY(echo_hook)
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
                output / f"{stem}.doj",
                output / f"{stem}.s",
            ]
        )
    command(
        [
            TOOLS / "seld",
            "-proc",
            "ADSP-21569",
            "-T",
            output / "memory.ldf",
            "-o",
            output / "echo.dxe",
            output / "wrapper.doj",
            output / "kernel.doj",
        ]
    )
    listing = command([TOOLS / "seldump", "-ns", "code", output / "echo.dxe"])
    (output / "listing.txt").write_text(listing)
    require(
        compare_listing(listing).all_extents_agree, "Echo instruction widths disagree"
    )
    code = swap_parcels(find_elf_section(output / "echo.dxe", "code"))
    data = find_elf_section(output / "echo.dxe", "data")
    require(
        len(code) <= 0x4000 and len(data) <= 0x800 and not any(data), "Echo arena/state"
    )
    blocks = sharcldr.parse_blocks(raw)
    memory = sharcldr.LoadedMemory.from_stream(raw, blocks)
    for lo, hi in (
        (k["CODE_BASE"], k["CODE_BASE"] + 0x4000),
        (k["DSP_STATE"], k["DSP_STATE"] + 0x4000),
    ):
        require(
            not any(
                a < hi and b > lo
                for a, b in zip(memory._segments[0], memory._segments[1], strict=True)
            ),
            "Echo overlaps existing memory",
        )
    hook = int(re.search(r"(?m)^echo_hook\.:\n\s+([0-9a-f]+)", listing)[1], 16)
    emit = int(re.search(r"(?m)^echo_emit\.:\n\s+([0-9a-f]+)", listing)[1], 16)
    patched = bytearray(raw)
    offset = sharcldr.offset_for_address(blocks, observer.FRAME_SITE)
    before = bytes.fromhex(base["patches"][0]["after"])
    require(patched[offset : offset + len(before)] == before, "Echo hook site drift")
    jump = assemble(f".SECTION/PM seg_pmco;\nJUMP {hook:#x};\nNOP;\n").boot_bytes
    require(len(jump) == len(before), "Echo patch width")
    patched[offset : offset + len(jump)] = jump
    blob = (
        bytes(patched)
        + header(k["CODE_BASE"], len(code))
        + code
        + header(k["DSP_STATE"], 0x4000, fill=0)
    )
    (output / "ECHO_BLOB.bin").write_bytes(blob)
    metadata = dict(
        blob_sha256=hashlib.sha256(blob).hexdigest(),
        code_bytes=len(code),
        state_bytes=0x4000,
        hook=hook,
        emit=emit,
        observer=base,
        contract_sha256=sha256(MACHINE / "contract.json"),
    )
    write_json(output / "build.json", metadata)
    return blob, metadata
