"""Guarded native STRETCH renderer seam; no new CPU selector or controls."""

import json
import re

from lab.sharc_hooks import HOOKS, context_restores, context_stores
from lab.sharc_tools import assemble


def assembly_wrapper():
    contract = HOOKS["stretch"]
    scratch = contract.scratch.in_space("dsp-byte")
    stack = contract.stack.in_space("dsp-byte")
    resume = contract.continuation.in_space("dsp-sw")
    result = ".EXTERN cap_stretch_machine.;\n.GLOBAL cap_stretch_hook;\ncap_stretch_hook:\nR4=R13; R12=R15;\n"
    result += context_stores(scratch)
    result += "M5=0; M6=1; M7=-1; M14=1;\n"
    result += " ".join(f"L{i}=0;" for i in range(16)) + "\n"
    result += f"I7={stack:#x}; I6=I7; R2=I6;\nCJUMP cap_stretch_machine. (DB);\nDM(I7,M7)=R2; DM(I7,M7)=cap_stretch_return-1;\ncap_stretch_return:\nDM(0x200e0900)=R0;\n"
    result += context_restores(scratch)
    result += "R0=DM(0x200e0900); R1=0; COMP(R0,R1); IF EQ JUMP cap_stretch_stock;\n"
    result += f"R1=DM({scratch + 4:#x}); R0=DM({scratch:#x}); JUMP 0x1c6af8;\ncap_stretch_stock:\nR1=DM({scratch + 4:#x}); R0=DM({scratch:#x}); JUMP {resume:#x};\n"
    return result


def patch_hook(raw, blocks, out):
    import sharcldr

    # Stock uses one six-byte parallel PASS/MOVE. The assembler emits two
    # compressed moves for our replay, so guard the inspected stock bytes.
    expected = bytes.fromhex("ff700286d014")
    offset = sharcldr.offset_for_address(
        blocks, HOOKS["stretch"].site.in_space("dsp-sw")
    )
    if raw[offset : offset + len(expected)] != expected or len(expected) != 6:
        raise ValueError("Unexpected native STRETCH call setup")
    listing = (out / "listing.txt").read_text()
    target = int(re.search(r"(?m)^cap_stretch_hook\.:\n\s+([0-9a-f]+)", listing)[1], 16)
    jump = assemble(f".section/pm seg_pmco;\nJUMP {target:#x};\n").boot_bytes
    if len(jump) != len(expected):
        raise ValueError("STRETCH hook extent mismatch")
    raw[offset : offset + len(jump)] = jump
    (out / "stretch-hook.json").write_text(
        json.dumps(
            dict(
                address=HOOKS["stretch"].site.in_space("dsp-sw"),
                target=target,
                before=expected.hex(),
                after=jump.hex(),
                stock_resume=HOOKS["stretch"].continuation.in_space("dsp-sw"),
                custom_resume=0x1C6AF8,
            ),
            indent=2,
        )
        + "\n"
    )
