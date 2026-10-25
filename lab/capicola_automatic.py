"""Guarded OS1.16 automatic Capicola preparation hooks."""

import json
import re

from lab.sharc_hooks import HOOKS, context_restores, context_stores
from lab.sharc_hooks import REGS as REGS
from lab.sharc_tools import assemble

# Both event hooks run in the serialized sample-link callback. They must never
# share scratch or stack with a preempted audio/maintenance wrapper.


def wrapper(label, function, scratch, stack, args, displaced, resume):
    scratch = scratch.in_space("dsp-byte")
    stack = stack.in_space("dsp-byte")
    resume = resume.in_space("dsp-sw")
    result = f".EXTERN {function}.;\n.GLOBAL {label};\n{label}:\n" + displaced
    result += context_stores(scratch)
    result += args
    result += "M5=0; M6=1; M7=-1; M14=1;\n"
    result += " ".join(f"L{i}=0;" for i in range(16)) + "\n"
    result += f"I7={hex(stack)}; I6=I7; R2=I6;\n"
    result += f"CJUMP {function}. (DB);\nDM(I7,M7)=R2; DM(I7,M7)={label}_return-1;\n{label}_return:\n"
    result += context_restores(scratch)
    result += f"R0=DM({hex(scratch)});\n"
    # Event hooks replay their displaced instructions AFTER restoring the
    # original registers. Maintenance first clears the stock SIMD mode.
    if label == "cap_page_hook":
        result += "R2=I5; I12=DM(I6,M7);\n"
    elif label == "cap_header_hook":
        result += "NOP; NOP; NOP;\n"
    elif label == "cap_guard_hook":
        result += "NOP; NOP; NOP; NOP; NOP;\n"
    return result + f"JUMP {hex(resume)};\n"


def assembly_wrappers():
    return (
        wrapper(
            "cap_frame_hook",
            "cap_maintenance",
            HOOKS["maintenance"].scratch,
            HOOKS["maintenance"].stack,
            "",
            "BIT CLR MODE1 0x200000;\n",
            HOOKS["maintenance"].continuation,
        )
        + wrapper(
            "cap_page_hook",
            "cap_event",
            HOOKS["sample-page"].scratch,
            HOOKS["sample-page"].stack,
            "R8=R4; R4=1; R12=4096;\n",
            "",
            HOOKS["sample-page"].continuation,
        )
        + wrapper(
            "cap_guard_hook",
            "cap_event",
            HOOKS["sample-guard"].scratch,
            HOOKS["sample-guard"].stack,
            "R12=R8; R8=R4; R4=3;\n",
            "",
            HOOKS["sample-guard"].continuation,
        )
        + wrapper(
            "cap_header_hook",
            "cap_event",
            HOOKS["sample-header"].scratch,
            HOOKS["sample-header"].stack,
            "R12=DM(1,I6); R4=2;\n",
            "",
            HOOKS["sample-header"].continuation,
        )
    )


def patch_hooks(raw, blocks, code, out):
    import sharcldr

    listing = (out / "listing.txt").read_text()
    records = []
    for address, label, source in (
        (
            HOOKS["maintenance"].site.in_space("dsp-sw"),
            "cap_frame_hook",
            "BIT CLR MODE1 0x200000;",
        ),
        (
            HOOKS["sample-page"].site.in_space("dsp-sw"),
            "cap_page_hook",
            "R2=I5; I12=DM(I6,M7);",
        ),
        (
            HOOKS["sample-header"].site.in_space("dsp-sw"),
            "cap_header_hook",
            "MODIFY(I7,-2);",
        ),
        (HOOKS["sample-guard"].site.in_space("dsp-sw"), "cap_guard_hook", ""),
    ):
        expected = (
            bytes.fromhex("7e713f818715fffffeff")
            if label == "cap_guard_hook"
            else bytes.fromhex("8715fffffeff")
            if label == "cap_header_hook"
            else assemble(".section/pm seg_pmco;\n" + source + "\n").boot_bytes
        )
        offset = sharcldr.offset_for_address(blocks, address)
        if raw[offset : offset + len(expected)] != expected:
            raise ValueError(f"Unexpected Capicola hook bytes at {address:#x}")
        target = int(re.search(rf"(?m)^{label}\.:\n\s+([0-9a-f]+)", listing)[1], 16)
        jump = assemble(f".section/pm seg_pmco;\nJUMP {target:#x};\n").boot_bytes
        if len(expected) > len(jump) and (len(expected) - len(jump)) % 2 == 0:
            jump += assemble(".section/pm seg_pmco;\nNOP;\n").boot_bytes * (
                (len(expected) - len(jump)) // 2
            )
        if len(jump) != len(expected):
            raise ValueError("Capicola hook instruction span mismatch")
        raw[offset : offset + len(jump)] = jump
        records.append(
            dict(
                address=address, target=target, before=expected.hex(), after=jump.hex()
            )
        )
    tail = assemble(".section/pm seg_pmco;\nJUMP 0x1c3fe8;\n").boot_bytes
    marker = bytes.fromhex("010001000100") + tail
    if code.count(marker) != 1:
        raise ValueError("Missing header displaced-instruction marker")
    code = code.replace(marker, bytes.fromhex("8715fffffeff") + tail)
    tail = assemble(".section/pm seg_pmco;\nJUMP 0x1c4014;\n").boot_bytes
    marker = bytes.fromhex("0100") * 5 + tail
    if code.count(marker) != 1:
        raise ValueError("Missing loop-guard displaced-instruction marker")
    code = code.replace(marker, bytes.fromhex("7e713f818715fffffeff") + tail)
    (out / "automatic-hooks.json").write_text(json.dumps(records, indent=2) + "\n")
    return code
