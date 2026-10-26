"""Predictable bank-H snapshot rows over the existing immutable FREEZE service.

No extra PCM, identities or reservation. Occupied rows refuse before the
snapshot is issued; the worker repeats the check under its existing lease.
"""

from lab import buf_freeze as bf
from lab import recorder_freeze_code as n
from lab import recorder_worker_code as w
from lab.emit import Code

SLOTS = tuple(range(1019, 1011, -1))  # H123..H116; H124..H127 remain BUF 1..4.
PICK = bf.BASE + 0x3000
TARGET = bf.STATE + 0x100
CONFLICT = -8
ACTION = 43  # After the existing COPY/PASTE feedback values 30..42.


def picker():
    """No-argument, memory-only check; caller owns mutation exclusion.

    Return the next fixed slot or a negative result. Never clear, unload,
    overwrite, reserve a slot or consume a snapshot identity here.
    """
    c = Code()
    c.emit("4feffff0 48d70c0c")
    c.imm("2239", n.STATE + 4)
    c.imm("0c81", len(SLOTS))
    c.branch(4, "full")
    c.imm("203c", SLOTS[0])
    c.emit("9081 2400")
    c.imm("23c2", TARGET)
    c.imm("2079", w.STATE + 68)
    c.emit("2008 4a80")
    c.branch(7, "bad")
    c.emit("2002 d080 d080 d080 d080 d1c0 2010")
    c.imm("0c80", -1)
    c.branch(6, "conflict")
    c.emit("2002 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0 2010")
    c.imm("0c80", -1)
    c.branch(6, "conflict")
    c.emit("2002 d080 d080")
    c.imm("41f9", 0x405BA768)
    c.emit("d1c0 2010 4a80")
    c.branch(6, "conflict")
    # Includes occupied private seats, existing snapshots and quarantined rows.
    c.imm("41f9", n.RESERVED)
    c.emit("7615")
    c.label("reserved")
    c.emit("2010")
    c.imm("0c80", -1)
    c.branch(7, "ready")
    c.emit("b082")
    c.branch(7, "conflict")
    c.emit("5888")
    c.imm("0683", -1)
    c.branch(6, "reserved")
    c.branch(0, "bad")
    c.label("ready")
    c.emit("2002")
    c.branch(0, "return")
    for name, value in (("conflict", CONFLICT), ("full", -5), ("bad", -1)):
        c.label(name)
        c.imm("203c", value)
        c.branch(0, "return")
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(PICK)
