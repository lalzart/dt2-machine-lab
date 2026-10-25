"""Opt-in native pending-reference diagnostics, never allocator authority."""

import hashlib
import re

from lab import recorder_retirement as inherited
from lab.project import ROOT, read_json, require, sha256, write_json

MACHINE = ROOT / "machines/recorder-retirement-gate"
BASE_BUILD = inherited.build


def contract():
    c = read_json(MACHINE / "contract.json")
    require(c["status"] == "ready", "Retirement gate not ready")
    require(sha256(ROOT / c["proposal"]) == c["proposal_sha256"], "Gate plan drift")
    require(c["dependencies"] == read_json(ROOT / "deps.lock.json"), "Gate pin drift")
    for name in ("working_artifact", "evidence_level", "controls", "state_matrix",
                 "source_equivalence", "experiment", "validation", "results", "gaps",
                 "decisions", "approval"):
        require(bool(c[name]), "Incomplete gate contract: " + name)
    require(len(c["experiment"]["conditions"]) == 16, "Gate cases drift")
    require(c["constants"]["UNKNOWN_OWNERSHIP"] == 127, "Unknown roots removed")
    return c


def state(engine):
    base = contract()["constants"]["STATE"]
    return [engine.core.peek(base + i * 4) for i in range(97)]


def build(output, *, state_base=None):
    """Compose with inherited observer; ack overlay may be composed on top."""
    # isort: off
    from lab import runtime  # install pinned import paths first
    import sharcldr
    from sharc_selache import compare_listing, find_elf_section, swap_parcels
    from lab.dsp_build import COMPILER, TOOLS, command
    from lab.sharc_hooks import context_restores, context_stores
    from lab.sharc_tools import assemble, header
    # isort: on

    from copy import deepcopy

    cfg = deepcopy(contract())
    if state_base is not None:
        require(
            type(state_base) is int
            and 0x20000000 <= state_base <= 0x200FA000
            and state_base % 0x1000 == 0,
            "Invalid gate state placement",
        )
        cfg["constants"].update(STATE=state_base, END=state_base + 0x4000)
    require(cfg["firmware"] == sha256(runtime.STOCK_BLOB), "Gate firmware drift")
    k = cfg["constants"]
    output.mkdir(exist_ok=False)
    blob, base = BASE_BUILD(output / "observer")
    old_listing = (output / "observer/listing.txt").read_text()
    observer_fn = int(re.search(r"(?m)^observer_frame\.:\n\s+([0-9a-f]+)", old_listing)[1], 16)
    (output / "protocol.h").write_text("\n".join(
        f"#define {n} {v:#x}u" for n, v in k.items()) + "\n")
    (output / "gate.c").write_bytes((MACHINE / "gate.c").read_bytes())
    command([COMPILER, "-proc", "ADSP-21569", "-O1", "-S", "-o",
             output / "kernel-original.s", output / "gate.c"])
    assembly = (output / "kernel-original.s").read_text()
    assembly = re.sub(r"(?m)^(\s*R\d+ = R\d+ \+ R\d+;)$",
                      r".NOCOMPRESS;\n\1\n.COMPRESS;", assembly)
    (output / "kernel.s").write_text(assembly)
    text = ".SECTION/PM seg_pmco;\n.EXTERN gate_control.;\n.EXTERN gate_lookup.;\n.EXTERN gate_frame.;\n"

    def invoke(label, fn, stack):
        return ("M5=0; M6=1; M7=-1; M14=1;\n" +
                " ".join(f"L{i}=0;" for i in range(16)) +
                f"\nI7={stack:#x}; I6=I7; R2=I6;\nCJUMP {fn} (DB);\n"
                f"DM(I7,M7)=R2; DM(I7,M7)={label}_returned-1;\n{label}_returned:\n")

    def wrapper(label, fn, index, tail):
        scratch = k["STATE"] + 0x1000 + index * 0x400
        stack = k["STATE"] + 0x2F00 + index * 0x400
        return (f".GLOBAL {label};\n{label}:\n" + context_stores(scratch) +
                f"R0=ASTATX; DM({scratch+0x104:#x})=R0; R0=ASTATY; DM({scratch+0x108:#x})=R0;\n" +
                fn(label, stack) + context_restores(scratch) +
                f"R0=DM({scratch+0x108:#x}); ASTATY=R0; R0=DM({scratch+0x104:#x}); ASTATX=R0; R0=DM({scratch:#x});\n" + tail)

    for i, patch in enumerate(cfg["patches"]):
        fn = "gate_control." if i == 0 else "gate_lookup."
        text += wrapper(patch["hook"], lambda label, stack, fn=fn: invoke(label, fn, stack),
                        i, patch["displaced"] + f" JUMP {patch['resume']:#x};\n")
    text += wrapper("gate_frame_hook", lambda label, stack:
                    invoke(label+"_observer", f"{observer_fn:#x}", stack) +
                    invoke(label, "gate_frame.", stack), 2,
                    "I2=DM(-17,I6); I3=DM(-16,I6); JUMP 0x1c75c9;\n")
    text += ".GLOBAL gate_direct;\ngate_direct:\n" + invoke("direct_observer", f"{observer_fn:#x}", k["STATE"]+0x3B00)
    text += invoke("direct", "gate_frame.", k["STATE"]+0x3B00) + "RTS;\n"
    text += ".SECTION/DM seg_dmda;\n.VAR gate_anchor=0;\n"
    (output / "wrapper.s").write_text(text)
    (output / "memory.ldf").write_text("""ARCHITECTURE(ADSP-21569)
MEMORY {
 code { TYPE(BW RAM) START(0x200d0000) END(0x200d7fff) WIDTH(8) }
 data { TYPE(BW RAM) START(@DATA_START@) END(@DATA_END@) WIDTH(8) }
}
PROCESSOR core0 { OUTPUT($COMMAND_LINE_OUTPUT_FILE) ENTRY(gate_direct)
 SECTIONS {
 code SW { INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_pmco seg_swco seg_l1_block0_swco seg_l1_block1_swco seg_l2_swco)) } > code
 data BW { INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_dmda seg_l2 seg_l1_bss seg_l2_bss)) } > data
 }
}
""".replace("@DATA_START@", hex(k["STATE"] + 0x800))
        .replace("@DATA_END@", hex(k["STATE"] + 0xFFF)))
    for stem in ("wrapper", "kernel"):
        command([TOOLS / "selas", "-proc", "ADSP-21569", "-o",
                 output / f"{stem}.doj", output / f"{stem}.s"])
    command([TOOLS / "seld", "-proc", "ADSP-21569", "-T", output / "memory.ldf",
             "-o", output / "gate.dxe", output / "wrapper.doj", output / "kernel.doj"])
    listing = command([TOOLS / "seldump", "-ns", "code", output / "gate.dxe"])
    (output / "listing.txt").write_text(listing)
    require(compare_listing(listing).all_extents_agree, "Gate instruction widths disagree")
    code = swap_parcels(find_elf_section(output / "gate.dxe", "code"))
    data = find_elf_section(output / "gate.dxe", "data")
    require(len(code) <= 0x8000 and len(data) <= 0x800 and not any(data), "Gate arena")
    raw = bytearray(blob)
    blocks = sharcldr.parse_blocks(raw)
    memory = sharcldr.LoadedMemory.from_stream(raw, blocks)
    for lo, hi in ((k["CODE_BASE"], k["CODE_BASE"]+0x8000), (k["STATE"], k["END"])):
        require(not any(a < hi and b > lo for a, b in
                zip(memory._segments[0], memory._segments[1], strict=True)), "Gate overlap")
    symbols = {n: int(re.search(rf"(?m)^{n}\.:\n\s+([0-9a-f]+)", listing)[1], 16)
               for n in ("gate_control_hook", "gate_lookup_hook", "gate_frame_hook", "gate_direct")}
    patches = []
    frame = dict(site=inherited.FRAME_SITE, before=base["patches"][0]["after"], hook="gate_frame_hook")
    for p in [*cfg["patches"], frame]:
        off = sharcldr.offset_for_address(blocks, p["site"])
        expected = bytes.fromhex(p["before"])
        require(raw[off:off+len(expected)] == expected, "Gate patch drift")
        if "displaced" in p:
            require(assemble(".SECTION/PM seg_pmco;\n"+p["displaced"]).boot_bytes == expected,
                    "Gate displaced instruction mismatch")
        jump = assemble(f".SECTION/PM seg_pmco;\nJUMP {symbols[p['hook']]:#x};\n").boot_bytes
        jump += assemble(".SECTION/PM seg_pmco;\nNOP;\n").boot_bytes * ((len(expected)-len(jump))//2)
        require(len(jump) == len(expected), "Gate patch width")
        raw[off:off+len(expected)] = jump
        patches.append(dict(site=p["site"], before=expected.hex(), after=jump.hex(), target=symbols[p["hook"]]))
    blob = bytes(raw) + header(k["CODE_BASE"], len(code)) + code + header(k["STATE"], k["END"]-k["STATE"], fill=0)
    (output / "GATE_BLOB.bin").write_bytes(blob)
    metadata = dict(base, gate=dict(symbols=symbols, patches=patches, code_bytes=len(code),
                    mapped_state_bytes=k["END"]-k["STATE"], contract_sha256=sha256(MACHINE/"contract.json")),
                    blob_sha256=hashlib.sha256(blob).hexdigest())
    metadata["symbols"] = dict(base["symbols"], observer_frame_hook=symbols["gate_frame_hook"])
    metadata["patches"] = [dict(base["patches"][0], after=patches[-1]["after"], target=symbols["gate_frame_hook"]), *base["patches"][1:]]
    write_json(output / "build.json", metadata)
    return blob, metadata
