"""Sketch-owned COPY/PASTE frontend over the unchanged BUF snapshot worker.

Volatile clipboard metadata lives in spare Sketch state. No stock clipboard,
audio allocator, project format or snapshot identity policy is replaced.
"""

from lab import arp_firmware as abi
from lab import buf_freeze as bf
from lab import buf_next_bar as nb
from lab import recorder_freeze_code as frozen
from lab import recorder_freeze_worker_code as jobs
from lab import recorder_worker_code as worker
from lab.emit import Code

BASE = 0x11100000
STATE = BASE + 0x180
VALID, PENDING, COMPLETION, EPOCH, KIT, PROJECT, POOL, DESCRIPTOR, SLOT = range(
    0, 36, 4
)
TARGET, OWN = 36, 40
COPY, FEEDBACK, CHECK, PASTE, KEY = (
    BASE + x for x in (0x200, 0x400, 0x700, 0xA00, 0xD00)
)
LABELS = {
    "copy_queued": "COPY: PRESERVING TAKE",
    "copy_ready": "COPIED / F+STOP:PASTE",
    "copy_busy": "COPY: BUSY",
    "copy_empty": "COPY: BUF EMPTY",
    "copy_full": "COPY: TAKE LIST FULL",
    "copy_failed": "COPY: FAILED",
    "copy_stale": "COPY: CONTEXT CHANGED",
    "paste_ready": "PASTED TO TRACK %u",
    "paste_empty": "PASTE: COPY A BUF FIRST",
    "paste_busy": "PASTE: BUSY",
    "paste_machine": "PASTE: USE ONESHOT",
    "paste_failed": "PASTE: FAILED",
    "paste_stale": "PASTE: TAKE UNAVAILABLE",
}
(
    QUEUED,
    COPIED,
    BUSY,
    EMPTY,
    FULL,
    FAILED,
    STALE,
    PASTED,
    NO_COPY,
    PASTE_BUSY,
    MACHINE,
    PASTE_FAILED,
    PASTE_STALE,
) = range(30, 43)


def load(c, field, reg=0):
    c.imm(f"{0x2039 | reg << 9:04x}", STATE + field)


def store(c, field, reg=0):
    c.imm(f"{0x23C0 | reg:04x}", STATE + field)


def setv(c, field, value):
    c.imm("203c", value)
    store(c, field)


def action(c, value):
    from lab import sketch as s

    s.setv(c, s.ACTION, value)


def copy():
    from lab import sketch as s

    c = Code()
    c.emit(abi.PRESAVE)
    frozen.call(c, FEEDBACK)
    load(c, PENDING)
    c.emit("4a80")
    c.branch(6, "busy")
    c.imm("2439", jobs.STATE + 32)
    s.load(c, s.BUF)
    c.emit("2f00")
    frozen.call(c, bf.SUBMIT, 4)
    c.emit("4a80")
    c.branch(7, "accepted")
    for result, label in ((-7, "busy"), (-2, "empty"), (-5, "full")):
        c.imm("0c80", result)
        c.branch(7, label)
    action(c, FAILED)
    c.branch(0, "done")
    c.label("accepted")
    c.emit("2002 5280")
    store(c, COMPLETION)
    setv(c, VALID, 0)
    setv(c, PENDING, 1)
    for source, field in (
        (bf.EPOCH, EPOCH),
        (bf.KIT, KIT),
        (bf.PROJECT, PROJECT),
        (bf.POOL, POOL),
    ):
        c.imm("2039", bf.STATE + source)
        store(c, field)
    action(c, QUEUED)
    c.branch(0, "done")
    for label, value in (("busy", BUSY), ("empty", EMPTY), ("full", FULL)):
        c.label(label)
        action(c, value)
        c.branch(0, "done")
    c.label("done")
    c.emit(abi.RESTORE + "4e75")
    return c.finish(COPY)


def context(c, bad):
    for at, field in (
        (frozen.STATE, EPOCH),
        (0x80004704, KIT),
        (0x44F370A0, PROJECT),
        (worker.STATE + 68, POOL),
    ):
        c.imm("2039", at)
        load(c, field, 1)
        c.emit("b081")
        c.branch(6, bad)


def feedback():
    from lab import sketch as s

    c = Code()
    c.emit(abi.PRESAVE)
    load(c, PENDING)
    c.emit("4a80")
    c.branch(7, "done")
    context(c, "stale")
    c.imm("2039", jobs.STATE + 32)
    load(c, COMPLETION, 1)
    c.emit("b081")
    c.branch(7, "completed")
    c.emit("5280 b081")
    c.branch(7, "done")  # Still the predecessor, including counter wrap.
    c.branch(0, "stale")  # Another job completed before this result was observed.
    c.label("completed")
    setv(c, PENDING, 0)
    c.imm("2439", jobs.STATE + 12)
    c.imm("0c82", 1)
    c.branch(13, "failed")
    c.imm("0c82", 1023)
    c.branch(2, "failed")
    c.imm("45f9", frozen.SNAP)
    c.emit("7608")
    c.label("scan")
    c.emit("202a0024 b082")
    c.branch(7, "found")
    c.emit("41ea0040 2448")
    c.imm("0683", -1)
    c.branch(6, "scan")
    c.branch(0, "failed")
    c.label("found")
    c.emit("200a")
    store(c, DESCRIPTOR)
    store(c, SLOT, 2)
    setv(c, VALID, 1)
    frozen.call(c, CHECK)
    c.emit("4a80")
    c.branch(7, "stale")
    s.load(c, s.ACTION)
    for value in (QUEUED, BUSY, PASTE_BUSY):
        c.imm("0c80", value)
        c.branch(7, "ready")
    c.branch(0, "done")
    c.label("ready")
    action(c, COPIED)
    c.branch(0, "done")
    for label, value in (("failed", FAILED), ("stale", STALE)):
        c.label(label)
        setv(c, VALID, 0)
        setv(c, PENDING, 0)
        s.load(c, s.ACTION)
        for owner in (QUEUED, BUSY, PASTE_BUSY):
            c.imm("0c80", owner)
            c.branch(7, label + "_message")
        c.branch(0, "done")
        c.label(label + "_message")
        action(c, value)
        c.branch(0, "done")
    c.label("done")
    c.emit(abi.RESTORE + "4e75")
    return c.finish(FEEDBACK)


def check():
    """Read-only validation of the immutable snapshot, its loader and pool keys."""
    c = Code()
    c.emit(abi.PRESAVE)
    load(c, VALID)
    c.imm("0c80", 1)
    c.branch(6, "bad")
    context(c, "bad")
    load(c, DESCRIPTOR)
    c.imm("0c80", frozen.SNAP)
    c.branch(5, "bad")
    c.imm("0c80", frozen.SNAP + 7 * 64)
    c.branch(2, "bad")
    c.emit("2200")
    c.imm("0281", 63)
    c.branch(6, "bad")
    c.emit("2440 2012")
    c.imm("0c80", 1)
    c.branch(6, "bad")
    c.emit("202a0008")
    load(c, EPOCH, 1)
    c.emit("b081")
    c.branch(6, "bad")
    load(c, SLOT, 2)
    c.imm("0c82", 1)
    c.branch(13, "bad")
    c.imm("0c82", 1023)
    c.branch(2, "bad")
    c.emit("202a0024 b082")
    c.branch(6, "bad")
    c.emit("2002 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0")
    for off in range(0, 16, 4):
        c.emit(f"2028{off:04x} 222a{16 + off:04x} b081")
        c.branch(6, "bad")
    c.emit("20280008 4a80")
    c.branch(7, "bad")
    c.emit("2028000c 4a80")
    c.branch(7, "bad")
    load(c, POOL)
    # worker.STATE+68 already addresses the pool entries (setup added 0x1d2).
    c.emit("2040 2002 d080 d080 d080 d080 d1c0")
    for off in range(0, 16, 4):
        c.emit(f"2028{off:04x} 222a{48 + off:04x} b081")
        c.branch(6, "bad")
    c.emit("7001")
    c.branch(0, "done")
    c.label("bad")
    c.emit("7000")
    c.label("done")
    c.emit(abi.RESTORE + "4e75")
    return c.finish(CHECK)


def paste():
    c = Code()
    c.emit(abi.PRESAVE)
    frozen.call(c, FEEDBACK)
    load(c, PENDING)
    c.emit("4a80")
    c.branch(6, "busy")
    load(c, VALID)
    c.emit("4a80")
    c.branch(7, "empty")
    for at in (
        jobs.STOCK_BUSY,
        jobs.STATE + 56,
        worker.STATE + 12,
        nb.STATE + nb.PHASE,
    ):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "busy")
    frozen.call(c, CHECK)
    c.emit("4a80")
    c.branch(7, "stale")
    frozen.call(c, 0x401988A2)
    c.emit("2600 2f00")
    frozen.call(c, 0x40041D18, 4)
    c.emit("2f00")
    frozen.call(c, 0x4004ABE8, 4)
    c.imm("0c80", 15)
    c.branch(2, "failed")
    c.emit("2400 5280")
    store(c, TARGET)
    load(c, KIT)
    c.emit("2440 2002")
    c.imm("223c", 0x450)
    c.emit("4c010800 d5c0 7000 102a00d6 4a80")
    c.branch(6, "machine")
    # Stock parameter accessor and the sample chooser's exact setter argument
    # shape. The setter owns range checks, notifications and track refresh.
    c.emit("2f02")
    c.imm("4879", 0xCD)
    c.emit("2f03")
    frozen.call(c, 0x40045582, 12)
    c.emit("4a80")
    c.branch(7, "failed")
    c.emit("2440")
    for arg in (1, 1, 1, -1):
        c.imm("4879", arg)
    load(c, SLOT)
    c.emit("2f00")
    c.imm("4879", 0xCD)
    c.emit("2f0a")
    frozen.call(c, 0x4003B570, 28)
    load(c, SLOT, 1)
    c.emit("b081")
    c.branch(6, "failed")
    action(c, PASTED)
    c.branch(0, "done")
    for label, value in (
        ("empty", NO_COPY),
        ("busy", PASTE_BUSY),
        ("stale", PASTE_STALE),
        ("machine", MACHINE),
        ("failed", PASTE_FAILED),
    ):
        c.label(label)
        action(c, value)
        c.branch(0, "done")
    c.label("done")
    c.emit(abi.RESTORE + "4e75")
    return c.finish(PASTE)


def key():
    from lab import sketch as s

    c = Code()
    c.emit(abi.PRESAVE + "246f0028 266f002c 242b000c 262b0010")
    frozen.call(c, FEEDBACK)
    for key_id, bit in ((19, 1), (21, 2)):
        c.imm("0c82", key_id)
        c.branch(7, f"key{bit}")
    c.branch(0, "no")
    for bit, service in ((1, COPY), (2, PASTE)):
        c.label(f"key{bit}")
        load(c, OWN)
        c.imm("0280", bit)
        c.branch(7, f"new{bit}")
        c.emit("2003")
        c.imm("0280", 1)
        c.branch(6, "yes")  # Repeat/hold cannot submit another operation.
        load(c, OWN)
        c.imm("0280", ~bit)
        store(c, OWN)
        c.branch(0, "yes")
        c.label(f"new{bit}")
        s.load(c, s.VIEW)
        c.emit("4a80")
        c.branch(7, "no")
        c.emit("220a b081")
        c.branch(6, "no")
        s.load(c, s.OWN)
        c.emit("4a80")
        c.branch(6, "no")
        c.emit("2003")
        c.imm("0280", 9)
        c.imm("0c80", 1)
        c.branch(6, "no")
        c.imm("4879", 17)
        frozen.call(c, 0x4011DE70, 4)
        c.imm("0280", 255)
        c.branch(7, "no")
        load(c, OWN)
        c.imm("0080", bit)
        store(c, OWN)
        frozen.call(c, service)
        c.branch(0, "yes")
    c.label("yes")
    c.emit("7001")
    c.branch(0, "done")
    c.label("no")
    c.emit("7000")
    c.label("done")
    c.emit(abi.RESTORE + "4e75")
    return c.finish(KEY)


def payload():
    return {
        COPY: copy(),
        FEEDBACK: feedback(),
        CHECK: check(),
        PASTE: paste(),
        KEY: key(),
    }
