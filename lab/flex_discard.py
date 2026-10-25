"""Explicit, irreversible take deletion; IDs remain permanent tombstones.

Unlike reachability-based GC, the user authorizes removing this audio from the
whole current project. Old handles fail closed instead of reading recycled PCM.
"""

from lab.emit import Code
from lab.flex_retirement import mask


def discard(address, pool, lookup, abort, state):
    """int discard(node, captured_pool): 0 removed, -1 busy/stale/saved.

    UI-thread operation. Claim the tombstone only with no source reader/save,
    retirement owner or queued USE. Native slot unload cancels loader work and
    clears DSP slot state. Only then release the CPU source. Descriptor/ID stay.
    """
    c = Code()
    c.emit("4fefffd8 48d73c1c 246f002c 2a6f0030")
    for opcode in ("b5fc", "bbfc"):
        c.imm(opcode, 0)
        c.branch(7, "failed")
    c.imm("4eb9", pool)
    c.emit("220d b081")
    c.branch(6, "failed")
    c.emit("202a0004")
    c.imm("4eb9", lookup)
    c.emit("2008 220a b081")
    c.branch(6, "failed")
    mask(c)
    c.imm("2039", state + 12)
    c.emit("4a80")
    c.branch(6, "busy")
    for offset in (28, 48, 52, 56):
        c.emit(f"202a{offset:04x} 4a80")
        c.branch(6, "busy")
    c.emit("7001 25400038 46c1 264d 7400")
    c.label("pool_slot")
    for offset in range(0, 16, 4):
        c.emit(f"202b{offset:04x} 222a{offset + 4:04x} b081")
        c.branch(6, "pool_next")
    c.emit("70ff 2680 7000 27400004 27400008 2740000c")
    c.label("pool_next")
    c.emit("47eb0010")
    c.imm("0682", 1)
    c.imm("0c82", 1024)
    c.branch(5, "pool_slot")
    c.imm("47f9", 0x405B1368)
    c.emit("7400")
    c.label("loaded_slot")
    for offset in range(0, 16, 4):
        c.emit(f"202b{offset:04x} 222a{offset + 4:04x} b081")
        c.branch(6, "loaded_next")
    c.imm("2879", 0x80004704)
    c.emit("7600")
    c.label("track")
    c.emit("7000 302c0080 b082")
    c.branch(6, "track_next")
    c.emit("7000 39400080 2f03 41ec0034 2f08")
    c.imm("4eb9", 0x4002D438)
    c.emit("508f")
    c.label("track_next")
    c.imm("d9fc", 0x450)
    c.imm("0683", 1)
    c.imm("0c83", 16)
    c.branch(5, "track")
    c.emit("2f02")
    c.imm("4eb9", 0x401540C6)
    c.imm("4eb9", 0x40153BEA)
    c.emit("588f")
    c.label("loaded_next")
    c.emit("47eb0010")
    c.imm("0682", 1)
    c.imm("0c82", 1024)
    c.branch(5, "loaded_slot")
    c.emit("2f0a")
    c.imm("4eb9", abort)
    c.emit("588f 7000")
    c.branch(0, "done")
    c.label("busy")
    c.emit("46c1")
    c.label("failed")
    c.emit("70ff")
    c.label("done")
    c.emit("4cd73c1c 4fef0028 4e75")
    return c.finish(address)
