"""Read-only native accounting for the existing OS 1.16 Flex source owner.

This is an optional diagnostic, not a reclaimer. Call on the UI thread while
the recorder worker is idle. All successfully published nodes remain pinned.
Counts describe Flex's requested CPU allocations, not allocator overhead,
recorder storage, sample playback memory, or free device memory.
"""

import hashlib

from lab.flex_native import MAX_FRAMES, Code
from lab.project import require

ENTRY = 0x402FDE6C
END = 0x402FDF66
BASE = 0x40000400
BASELINES = {
    "e39ac4e57266d407efbe20a9db760975ff3197a9bccc111602ad831bd909e1d0",
    "24b6f9fcdde519299a67738d7d4cb166d90f0e53e15e5dd55e88a7e90fee0363",
    "32081f9ce0db5002e271cdda883feecb54f72c0a1111cb1fa6782f690fe4743a",
    "edb451e857102fd814637e15b3860ac68c6c012af22929d57cc57759dee7b3d7",
}


def snapshot(address, *, separate_source=False):
    """int snapshot(state, out[4]): takes, cached saves, PCM bytes, heap requests.

    Busy/corrupt lists fail without changing output. Registers obey the native
    ABI. A saved flag only means a cached reference exists; it does not prove
    the file still exists and must never authorize retirement.
    """
    c = Code()
    c.emit("4fefffe8 48d70c3c 246f001c 266f0020")
    c.emit("202a000c")
    c.imm("0c80", 0)
    c.branch(6, "invalid")
    c.emit("2052 7400 7600 7800 7a00")
    c.label("node")
    c.imm("b1fc", 0)
    c.branch(7, "done")
    c.imm("0c82", 32)
    c.branch(4, "invalid")
    c.emit("2028000c")
    c.imm("0c80", 362)  # minimum 141-frame mono take plus header/trailer
    c.branch(5, "invalid")
    c.imm("0c80", MAX_FRAMES * 4 + 80)
    c.branch(2, "invalid")
    if separate_source:
        c.emit("22280014")
        c.imm("0c81", 0)
        c.branch(7, "descriptor_only")
    c.imm("0680", -80)
    c.emit("2244 d3c0 2809")
    c.emit("2028000c")
    c.imm("0680", 64)
    c.emit("2245 d3c0 2a09")
    if separate_source:
        c.branch(0, "counted")
        c.label("descriptor_only")
        c.imm("0685", 64)
        c.label("counted")
    c.imm("0682", 1)
    c.emit("2028001c")
    c.imm("0c80", 1)
    c.branch(6, "next")
    c.imm("0683", 1)
    c.label("next")
    c.emit("2050")
    c.branch(0, "node")
    c.label("done")
    c.emit("2682 27430004 27440008 2745000c 7000")
    c.branch(0, "return")
    c.label("invalid")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70c3c 4fef0018 4e75")
    return c.finish(address)


def patch_cpu(image):
    """Optional diagnostic entry in unused, guarded existing Flex padding.

    No new hooks or allocation limits. The default Flex/Plaits/Capicola build
    remains byte-identical. A native call or emulator probe supplies state/out.
    """
    baseline = hashlib.sha256(image).hexdigest()
    require(baseline in BASELINES, "Unknown Flex accounting baseline")
    payload = snapshot(ENTRY)
    require(ENTRY + len(payload) <= END, "Accounting padding exhausted")
    require(not any(image[ENTRY - BASE : END - BASE]), "Occupied accounting padding")
    result = bytearray(image)
    result[ENTRY - BASE : ENTRY - BASE + len(payload)] = payload
    return bytes(result), dict(
        baseline_sha256=baseline,
        sha256=hashlib.sha256(result).hexdigest(),
        entry=ENTRY,
        bytes=len(payload),
        remaining_contiguous_padding=END - ENTRY - len(payload),
        fields=[
            "retained_takes",
            "cached_save_refs",
            "pcm_bytes",
            "requested_heap_bytes",
        ],
        source_retirement=False,
        ui_gesture=None,
        hardware_ready=False,
        scope="Read-only native diagnostic; call on the UI thread while USE is idle",
    )


def saved_message(address, state, snapshot_at, format_at, buffer, show, fallback):
    """Show source-owner counters after named save, using persistent text storage."""
    c = Code()
    c.emit("4feffff0 204f 2f08")
    c.imm("4879", state)
    c.imm("4eb9", snapshot_at)
    c.emit("508f")
    c.imm("0c80", 0)
    c.branch(6, "fallback")
    c.emit("2f17 2f2f0010")  # takes, then requested bytes; sprintf right-to-left
    c.imm("4879", format_at)
    c.imm("4879", buffer)
    c.imm("4eb9", 0x40000E82)
    c.emit("4fef0010")
    c.imm("4879", buffer)
    c.branch(0, "show")
    c.label("fallback")
    c.imm("4879", fallback)
    c.label("show")
    c.imm("4eb9", show)
    c.emit("588f 4fef0010 4e75")
    return c.finish(address)
