"""OS1.16 startup visibility and guarded, metadata-only BUF reservation.

Uses spare managed-profile CPU space. No PCM allocation or loader reordering.
"""

from lab import buf_next_bar as b
from lab import buf_startup as startup
from lab import recorder_freeze_code as n
from lab import recorder_worker_code as w
from lab import sketch_managed as managed
from lab.emit import Code

AVAILABILITY = managed.BASE + 0x400
EARLY = managed.BASE + 0x600
NAMES = managed.BASE + 0x900
TEXTS = managed.BASE + 0xA00
ATTEMPTS, RESULT = managed.STATE + 0x40, managed.STATE + 0x44


def availability():
    """0=owned mapping, 1=loading, 2=setup unavailable; read-only."""
    from lab import buf_fixed_slots as fixed

    c = Code()
    c.imm("2039", w.STATE + 64)
    c.imm("0c80", 1)
    c.branch(6, "pending")
    for i, slot in enumerate(fixed.PUBLIC):
        c.imm("2039", n.STATE + 32 + i * 4)
        c.imm("0c80", slot)
        c.branch(6, "bad")
    c.emit("7000 4e75")
    c.label("pending")
    b.load(c, startup.POISON)
    c.emit("4a80")
    c.branch(6, "bad")
    b.load(c, startup.BATCH_DONE)
    c.imm("0c80", 1)
    c.branch(6, "loading")
    c.imm("2039", fixed.STATE + fixed.STATUS)
    c.emit("4a80")
    c.branch(6, "bad")
    c.label("loading")
    c.emit("7001 4e75")
    c.label("bad")
    c.emit("7002 4e75")
    return c.finish(AVAILABILITY)


def early():
    """Called by the batch's own task after stock clears, before its load list.

    Require the batch wrapper A2 to be the active project wrapper. The normal
    initializer still owns every busy, reservation, conflict and capacity check.
    On refusal, retain the existing post-batch retry path.
    """
    c = Code()
    c.emit("4feffff0 48d70303")
    b.load(c, startup.POISON)
    c.emit("4a80")
    c.branch(6, "done")
    b.load(c, b.PHASE)
    c.emit("4a80")
    c.branch(6, "done")
    c.imm("2039", w.STATE + 64)
    c.emit("4a80")
    c.branch(6, "done")
    n.call(c, 0x401988A2)
    c.emit("4a80")
    c.branch(7, "done")
    c.emit("2f00")
    n.call(c, 0x40041D18, 4)
    c.emit("220a b081")
    c.branch(6, "done")
    c.imm("2039", ATTEMPTS)
    c.emit("5280")
    c.imm("23c0", ATTEMPTS)
    n.call(c, startup.INIT_STOCK)
    c.imm("2039", w.STATE + 64)
    c.imm("23c0", RESULT)
    c.label("done")
    c.emit("4cd70303 4fef0010 4e75")
    return c.finish(EARLY)


def payload(*, early_setup=False):
    code = {AVAILABILITY: availability()}
    if early_setup:
        code[EARLY] = early()
    names = b"".join(
        f"BUF {i} {status}".encode().ljust(16, b"\0")
        for status in ("LOADING", "UNAVAIL")
        for i in range(1, 5)
    )
    return code, {NAMES: names, TEXTS: b"LOADING\0".ljust(16, b"\0") + b"UNAVAIL\0"}
