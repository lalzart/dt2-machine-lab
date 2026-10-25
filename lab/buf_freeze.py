"""Explicit global-BUF FREEZE admission over the existing native worker.

Emulator scratch only. Claim the existing mutation lease while latching a
committed generation. No reader, allocator, snapshot or retirement policy changes.
"""

from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab.emit import Code
from lab.project import require

BASE, END = 0x11200000, 0x11204000
STATE = BASE
ACTIVE, BUFFER, EPOCH, KIT, PROJECT, SLOT, GENERATION, POOL = range(0, 32, 4)
KEY, PIN = 32, 48
SUBMIT, ADMIT, SOURCE = BASE + 0x1000, BASE + 0x1600, BASE + 0x2000
GATE, GATE_STOCK = BASE + 0x2600, BASE + 0x2A00
DONE, DONE_STOCK, CLEAR = BASE + 0x2C00, BASE + 0x2D00, BASE + 0x2E00


def source():
    """Pure register/memory check: source(buf) -> descriptor, D1 logical slot.

    Requires caller's mutation exclusion. Validate both complete associations;
    never accept preparing/quarantined metadata or a zero-length/not-ready take.
    """
    c = Code()
    c.emit("4feffff0 48d70c0c 242f0014")
    c.imm("0c82", 1)
    c.branch(5, "bad")
    c.imm("0c82", 4)
    c.branch(2, "bad")
    c.emit("2002")
    c.imm("0680", -1)
    c.emit("d080 d080")
    c.imm("41f9", n.STATE + 32)
    c.emit("d1c0 2410 4a82")
    c.branch(7, "bad")
    c.imm("0c82", 1023)
    c.branch(2, "bad")
    c.emit("2002 d080 d080 d080 d080")
    c.imm("47f9", 0x405B1368)
    c.emit("d7c0 2f13")
    n.call(c, n.LOOKUP, 4)
    c.emit("4a80")
    c.branch(7, "bad")
    c.emit("2440 2012")
    c.imm("0c80", 1)
    c.branch(6, "bad")
    c.emit("202a0018 4a80")
    c.branch(7, "bad")
    c.emit("202a001c 4a80")
    c.branch(7, "bad")
    for off in range(0, 16, 4):
        c.emit(f"202b{off:04x} 222a{off + 16:04x} b081")
        c.branch(6, "bad")
    c.emit("202a0024")
    c.imm("0c80", 1023)
    c.branch(2, "bad")
    c.emit("d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0")
    for off in range(0, 16, 4):
        c.emit(f"2028{off:04x} 222a{off + 16:04x} b081")
        c.branch(6, "bad")
    c.emit("200a 2202")
    c.branch(0, "return")
    c.label("bad")
    c.emit("7000")
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(SOURCE)


def admit():
    c = Code()
    c.emit("4fefffd0 48d77cfc 242f0034")
    # Stock getters may execute normally; no stock calls occur with IRQs masked.
    n.call(c, 0x4019988A)
    c.emit("4a80")
    c.branch(7, "refused_unmasked")
    c.emit("2f00")
    n.call(c, 0x40015F6C, 4)
    c.emit("4a80")
    c.branch(6, "busy_unmasked")
    c.emit("40c7 2007")
    c.imm("0080", 0x700)
    c.emit("46c0")
    for at in (
        w.STATE + 12,
        n.STATE + 24,
        q.STOCK_BUSY,
        q.STATE + 56,
        nb.STATE + nb.PHASE,
    ):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "busy")
    c.imm("2039", q.STATE)
    c.imm("2239", q.STATE + 4)
    c.emit("b081")
    c.branch(6, "busy")
    c.imm("0c82", 1)
    c.branch(5, "refused")
    c.imm("0c82", 4)
    c.branch(2, "refused")
    for at in (0x80004704, 0x44F370A0, w.STATE + 68):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(7, "empty")
    c.imm("2039", n.STATE + 4)
    c.imm("0c80", 8)
    c.branch(4, "full")
    c.emit("2f02")
    n.call(c, SOURCE, 4)
    c.emit("4a80")
    c.branch(7, "empty")
    c.imm("23c0", STATE + GENERATION)
    c.imm("23c1", STATE + SLOT)
    c.emit("2040")
    for off in range(0, 16, 4):
        c.emit(f"2028{off + 16:04x}")
        c.imm("23c0", STATE + KEY + off)
    c.emit("20280024")
    c.imm("23c0", STATE + PIN)
    c.imm("23c2", STATE + BUFFER)
    c.imm("23c2", q.STATE + 16)
    for actual, field, queue in (
        (n.STATE, EPOCH, q.STATE + 20),
        (0x80004704, KIT, q.STATE + 24),
        (0x44F370A0, PROJECT, None),
        (w.STATE + 68, POOL, None),
    ):
        c.imm("2039", actual)
        c.imm("23c0", STATE + field)
        if queue is not None:
            c.imm("23c0", queue)
    c.emit("7002")
    c.imm("23c0", w.STATE + 12)  # Existing worker mutation lease pins the take.
    c.emit("7001")
    c.imm("23c0", STATE + ACTIVE)
    c.imm("23c0", q.STATE + 8)
    c.emit("7000")
    c.imm("23c0", q.STATE + 28)
    c.imm("23c0", q.STATE + 48)
    c.branch(0, "restore")
    for label, value in (("busy", -7), ("refused", -1), ("empty", -2), ("full", -5)):
        c.label(label)
        c.emit(f"{0x7000 | (value & 255):04x}")
        c.branch(0, "restore")
    c.label("restore")
    c.emit("46c7")
    c.branch(0, "return")
    c.label("refused_unmasked")
    c.emit("70ff")
    c.branch(0, "return")
    c.label("busy_unmasked")
    c.emit("70f9")
    c.label("return")
    c.emit("4cd77cfc 4fef0030 4e75")
    return c.finish(ADMIT)


def gate():
    c = Code()
    n.call(c, GATE_STOCK)
    c.emit("4a80")
    c.branch(6, "return")
    c.imm("2039", STATE + ACTIVE)
    c.emit("4a80")
    c.branch(7, "return")  # The legacy queue keeps its original gate.
    c.emit("4feffff4 48d70404")
    for actual, field in ((0x44F370A0, PROJECT), (w.STATE + 68, POOL)):
        c.imm("2039", actual)
        c.imm("2239", STATE + field)
        c.emit("b081")
        c.branch(6, "stale")
    c.imm("2f39", STATE + BUFFER)
    n.call(c, SOURCE, 4)
    c.emit("4a80")
    c.branch(7, "stale")
    c.emit("2401")
    c.imm("2239", STATE + GENERATION)
    c.emit("b081")
    c.branch(6, "stale")
    c.emit("2440 2002")
    c.imm("2239", STATE + SLOT)
    c.emit("b081")
    c.branch(6, "stale")
    for off in range(0, 16, 4):
        c.emit(f"202a{off + 16:04x}")
        c.imm("2239", STATE + KEY + off)
        c.emit("b081")
        c.branch(6, "stale")
    c.emit("202a0024")
    c.imm("2239", STATE + PIN)
    c.emit("b081")
    c.branch(6, "stale")
    c.emit("7000")
    c.branch(0, "restore")
    c.label("stale")
    c.emit("70fd")
    c.label("restore")
    c.emit("4cd70404 4fef000c")
    c.label("return")
    c.emit("4e75")
    return c.finish(GATE)


def payload():
    c = Code()
    c.emit("7000")
    c.imm("23c0", STATE + ACTIVE)
    c.emit("4e75")
    done = Code()
    n.call(done, CLEAR)
    # CLEAR clobbers D0 only; original DONE reloads its integer stack argument.
    done.imm("4ef9", DONE_STOCK)
    parts = {
        SUBMIT: q.submit(address=SUBMIT, admission=ADMIT, queue_failure=CLEAR),
        ADMIT: admit(),
        SOURCE: source(),
        GATE: gate(),
        GATE_STOCK: q.gate(),
        DONE: done.finish(DONE),
        DONE_STOCK: q.done(),
        CLEAR: c.finish(CLEAR),
    }
    ordered = sorted(parts.items())
    for (at, raw), (after, _) in zip(ordered, ordered[1:], strict=False):
        require(at + len(raw) <= after, f"BUF FREEZE overlap {at:#x}")
    require(ordered[-1][0] + len(ordered[-1][1]) < END, "BUF FREEZE overflow")
    return parts
