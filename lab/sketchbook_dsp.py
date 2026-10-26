"""Opt-in bounded DSP readback tail, preserving the stock reply prefix.

CPU and SHARC use separate address spaces. Only original peripheral exchange
bytes cross that boundary; host memory peeks are an independent test oracle.
"""

import hashlib
import re

from lab.project import ROOT, read_json, require, sha256, write_json

MACHINE = ROOT / "machines/sketchbook-save"
BASE_SHA = "2ede0c37df1374f19c0d88c3130c2db2d1fc42ba7a98bd9e52a96d0dd13eb53a"


def contract():
    c = read_json(MACHINE / "contract.json")
    require(c["status"] == "ready", "Sketchbook contract not ready")
    require(
        sha256(ROOT / c["proposal"]) == c["proposal_sha256"],
        "Sketchbook proposal drift",
    )
    require(
        c["dependencies"] == read_json(ROOT / "deps.lock.json"),
        "Sketchbook dependency drift",
    )
    for name, digest in c["source_equivalence"]["files"].items():
        require(sha256(ROOT / name) == digest, "Sketchbook reference drift: " + name)
    for name in (
        "approval",
        "working_artifact",
        "evidence_level",
        "controls",
        "state_matrix",
        "experiment",
        "validation",
        "results",
        "gaps",
        "decisions",
    ):
        require(c[name], "Incomplete Sketchbook contract: " + name)
    k = c["constants"]
    require(
        k["FRAME"] == 0xBC0 and k["STOCK_FRAME"] == 0xABC, "Stock transport bound drift"
    )
    require(
        k["HEADER"] + k["PAYLOAD"] == k["FRAME"] - k["TAIL"], "Tail capacity mismatch"
    )
    return c


def build(base_blob, base_metadata, output):
    # isort: off
    from lab import runtime as runtime  # Initialize pinned assembler imports.
    import sharcldr
    from sharc_selache import compare_listing, find_elf_section, swap_parcels
    from lab.dsp_build import COMPILER, TOOLS, command
    from lab.sharc_hooks import context_restores, context_stores
    from lab.sharc_tools import assemble
    from lab.sketch_dsp_device import blocks, header, check_stream

    # isort: on
    c = contract()
    k = c["constants"]
    require(
        hashlib.sha256(base_blob).hexdigest() == BASE_SHA,
        "Readback requires exact R10 DSP",
    )
    require(base_metadata["blob_sha256"] == BASE_SHA, "Readback base metadata mismatch")
    output.mkdir(exist_ok=False)
    (output / "protocol.h").write_text(
        "\n".join(f"#define {n} {v:#x}u" for n, v in k.items()) + "\n"
    )
    (output / "readback.c").write_bytes((MACHINE / "readback.c").read_bytes())
    command(
        [
            COMPILER,
            "-proc",
            "ADSP-21569",
            "-O1",
            "-S",
            "-o",
            output / "kernel-original.s",
            output / "readback.c",
        ]
    )
    assembly = (output / "kernel-original.s").read_text()
    assembly = re.sub(
        r"(?m)^(\s*R\d+ = R\d+ \+ R\d+;)$", r".NOCOMPRESS;\n\1\n.COMPRESS;", assembly
    )
    (output / "kernel.s").write_text(assembly)
    old_frame = base_metadata["hook"]
    old_event = base_metadata["base"]["patches"][1]["target"]

    def enter(scratch):
        return (
            context_stores(scratch)
            + f"R0=ASTATX; DM({scratch + 0x104:#x})=R0; R0=ASTATY; DM({scratch + 0x108:#x})=R0;\n"
        )

    def invoke(name, stack, argument=""):
        return (
            argument
            + "M5=0; M6=1; M7=-1; M14=1;\n"
            + " ".join(f"L{i}=0;" for i in range(16))
            + f"\nI7={stack:#x}; I6=I7; R2=I6;\nCJUMP readback_{name}. (DB);\nDM(I7,M7)=R2; DM(I7,M7)=rb_{name}_returned-1;\nrb_{name}_returned:\n"
        )

    def leave(scratch):
        return (
            context_restores(scratch)
            + f"R0=DM({scratch + 0x108:#x}); ASTATY=R0; R0=DM({scratch + 0x104:#x}); ASTATX=R0; R0=DM({scratch:#x});\n"
        )

    fs, es = k["FRAME_SCRATCH"], k["EVENT_SCRATCH"]
    text = ".SECTION/PM seg_pmco;\n.EXTERN readback_emit.;\n.EXTERN readback_latch.;\n.GLOBAL readback_frame_hook;\nreadback_frame_hook:\n"
    text += (
        enter(fs)
        + invoke("emit", k["FRAME_STACK"], "R4=I4;\n")
        + leave(fs)
        + f"JUMP {old_frame:#x};\n"
    )
    text += (
        ".GLOBAL readback_event_hook;\nreadback_event_hook:\nR4=DM(0x268240);\n"
        + enter(es)
    )
    text += f"R0=R4; R1={k['TAG']:#x}; COMP(R0,R1); IF NE JUMP rb_event_stock;\n"
    text += invoke("latch", k["EVENT_STACK"])
    text += (
        leave(es)
        + "JUMP 0x1c7e43;\nrb_event_stock:\n"
        + leave(es)
        + f"JUMP {old_event:#x};\n"
    )
    text += ".SECTION/DM seg_dmda;\n.VAR readback_anchor=0;\n"
    (output / "wrapper.s").write_text(text)
    (output / "memory.ldf").write_text(f"""ARCHITECTURE(ADSP-21569)
MEMORY {{ code {{ TYPE(BW RAM) START({k["DSP_CODE"]:#x}) END({k["DSP_CODE"] + 0x3FFF:#x}) WIDTH(8) }}
 data {{ TYPE(BW RAM) START({k["DSP_STATE"]:#x}) END({k["DSP_STATE"] + 0x1FF:#x}) WIDTH(8) }} }}
PROCESSOR core0 {{ OUTPUT($COMMAND_LINE_OUTPUT_FILE) ENTRY(readback_frame_hook)
 SECTIONS {{ code SW {{ INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_pmco seg_swco seg_l1_block0_swco seg_l1_block1_swco seg_l2_swco)) }} > code
 data BW {{ INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_dmda seg_l2 seg_l1_bss seg_l2_bss)) }} > data }} }}
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
            output / "readback.dxe",
            output / "wrapper.doj",
            output / "kernel.doj",
        ]
    )
    listing = command([TOOLS / "seldump", "-ns", "code", output / "readback.dxe"])
    (output / "listing.txt").write_text(listing)
    require(
        compare_listing(listing).all_extents_agree,
        "Readback instruction widths disagree",
    )
    symbols = {
        n: int(re.search(rf"(?m)^{n}\.:\n\s+([0-9a-f]+)", listing)[1], 16)
        for n in (
            "readback_frame_hook",
            "readback_event_hook",
            "readback_emit",
            "readback_latch",
        )
    }
    code = swap_parcels(find_elf_section(output / "readback.dxe", "code"))
    require(
        len(code) <= 0x4000
        and not any(find_elf_section(output / "readback.dxe", "data")),
        "Readback arena overflow",
    )
    memory = sharcldr.LoadedMemory.from_stream(base_blob)
    require(
        not any(
            a < k["DSP_CODE"] + 0x4000 and b > k["DSP_CODE"]
            for a, b in zip(memory._segments[0], memory._segments[1], strict=True)
        ),
        "Readback code overlaps existing memory",
    )
    require(
        memory.read(k["DSP_STATE"], 0x200) == bytes(0x200),
        "Readback state not in initialized reserve",
    )
    raw = bytearray(base_blob)
    old_blocks = sharcldr.parse_blocks(raw)
    patches = []
    for site, target, old_target, width in (
        (0x1C75C5, symbols["readback_frame_hook"], old_frame, 8),
        (0x1C7E35, symbols["readback_event_hook"], old_event, 6),
    ):
        old = assemble(
            f".SECTION/PM seg_pmco;\nJUMP {old_target:#x};\n"
            + ("NOP;\n" if width == 8 else "")
        ).boot_bytes
        new = assemble(
            f".SECTION/PM seg_pmco;\nJUMP {target:#x};\n"
            + ("NOP;\n" if width == 8 else "")
        ).boot_bytes
        off = sharcldr.offset_for_address(old_blocks, site)
        require(
            bytes(raw[off : off + width]) == old and len(new) == width,
            "Readback hook drift",
        )
        raw[off : off + width] = new
        patches.append(dict(site=site, before=old.hex(), after=new.hex()))
    off = sharcldr.offset_for_address(old_blocks, 0x1C80A0)
    before = assemble(".SECTION/PM seg_pmco;\nR4=0xabc;\n").boot_bytes
    after = assemble(".SECTION/PM seg_pmco;\nR4=0xbc0;\n").boot_bytes
    require(
        len(before) == len(after) == 4 and bytes(raw[off : off + 4]) == before,
        "SPI init size drift",
    )
    raw[off : off + 4] = after
    patches.append(dict(site=0x1C80A0, before=before.hex(), after=after.hex()))
    items = blocks(raw)
    require(items[-1][0] == 0x8001, "Missing final DSP block")
    pad = (-len(code)) % 4
    code += bytes(pad)
    items.insert(-1, (1, k["DSP_CODE"], len(code), 0, code))
    offsets = []
    at = 0
    for b in items:
        offsets.append(at)
        at += 16 + len(b[4])
    firsts = [i for i, b in enumerate(items) if b[0] == 0x5001]
    for n, i in enumerate(firsts):
        b = items[i]
        end = offsets[firsts[n + 1]] if n + 1 < len(firsts) else at
        items[i] = (*b[:3], end - offsets[i] - 16, b[4])
    result = b"".join(header(*b[:4]) + b[4] for b in items)
    stream = check_stream(result)
    (output / "SKETCHBOOK_BLOB.bin").write_bytes(result)
    meta = dict(
        blob_sha256=hashlib.sha256(result).hexdigest(),
        base_blob_sha256=BASE_SHA,
        code_bytes=len(code),
        symbols=symbols,
        patches=patches,
        boot_stream=stream,
        contract_sha256=sha256(MACHINE / "contract.json"),
    )
    write_json(output / "build.json", meta)
    return result, meta
