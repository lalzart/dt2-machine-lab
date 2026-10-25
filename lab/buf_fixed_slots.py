"""Fixed OS1.16 public BUF seats; stock private-seat/player ownership is retained.

Only the opt-in Sketch device profile installs this CPU setup emitter. No
runtime mapping preference, PCM allocation, project rewrite or migration.
"""

from lab import recorder_freeze_code as n
from lab import recorder_worker_code as w
from lab.emit import Code

PUBLIC = (1020, 1021, 1022, 1023)  # BUF 1..4 = H124..H127.
STATE = w.STATE + 0x200  # Unused worker-state padding, within its existing arena.
STATUS, SLOT, RESTORED = 0, 4, 8
CONFLICT, CAPACITY, PROJECT = 1, 2, 3


def setup():
    """Same no-argument ABI as w.SETUP; full-plan validation precedes ownership.

    A retained 0x7ffd0001..4 project marker is accepted only at the matching
    fixed slot with nonzero epoch and zero trailing words. Loaded audio/cache
    must still be empty. Such a marker restores identity, never recorded PCM.
    Caller retains the existing loader/mutation exclusion requirements.
    """
    c = Code()
    c.emit("4fefff80 48d77cfc")
    c.imm("45f9", w.STATE)
    c.emit("7000")
    c.imm("23c0", STATE + STATUS)
    c.imm("23c0", STATE + SLOT)
    n.call(c, 0x401988A2)
    c.emit("2f00")
    n.call(c, 0x40041D18, 4)
    c.emit("2040 2250 22690028 2f08 4e91 588f 4a80")
    c.branch(7, "project")
    c.imm("0680", 0x1D2)
    c.emit("2640 202a0040 4a80")
    c.branch(7, "plan")
    c.emit("200b 222a0044 b081")
    c.branch(6, "project")
    for index, slot in enumerate(PUBLIC):
        c.emit(f"202a{96 + index * 4:04x}")
        c.imm("0c80", slot)
        c.branch(6, "project")
    c.branch(0, "done")
    c.label("plan")
    c.emit("49ef0040 7c00")  # A4 = complete local plan; D6 = restored markers.

    def empty_cache(bad):
        c.emit("2002 d080 d080")
        c.imm("41f9", 0x405BA768)
        c.emit("d1c0 2010 4a80")
        c.branch(6, bad)
        c.emit("2002 d080 d080 d080 d080")
        c.imm("41f9", 0x405B1368)
        c.emit("d1c0 2010")
        c.imm("0c80", -1)
        c.branch(6, bad)
        c.emit("2002 d080 d080 d080 d080 204b d1c0 2010")

    for index, slot in enumerate(PUBLIC):
        c.imm("243c", slot)
        empty_cache("conflict")
        c.imm("0c80", -1)
        c.branch(7, f"public{index}")
        c.imm("0c80", 0x7FFD0001 + index)
        c.branch(6, "conflict")
        c.emit("20280004 4a80")
        c.branch(7, "conflict")
        for offset in (8, 12):
            c.emit(f"2028{offset:04x} 4a80")
            c.branch(6, "conflict")
        c.imm("0686", 1)
        c.label(f"public{index}")
        c.emit(f"2942{index * 4:04x}")
    # Keep the existing private-seat count and ascending free-slot policy.
    c.emit("7401 7804")
    c.label("private")
    c.imm("0c82", PUBLIC[0])
    c.branch(4, "capacity")
    c.emit("2002 727f c081")
    c.branch(7, "next")
    empty_cache("next")
    c.imm("0c80", -1)
    c.branch(6, "next")
    c.emit("2004 d080 d080 224c d3c0 2282")
    c.imm("0684", 1)
    c.imm("0c84", 12)
    c.branch(7, "commit")
    c.label("next")
    c.imm("0682", 1)
    c.branch(0, "private")
    c.label("commit")
    c.emit("254b0044 204c 43ea0060")
    for _ in range(12):
        c.emit("22d8")
    c.emit("204c")
    c.imm("43f9", n.RESERVED)
    for _ in range(12):
        c.emit("22d8")
    c.emit("70ff 2280")
    for index, slot in enumerate(PUBLIC):
        c.imm("203c", slot * 16)
        c.imm("41f9", 0x405B6368)
        c.emit("d1c0")
        for value in (0x42554620, (index + 49) << 24, 0, 0):
            c.imm("223c", value)
            c.emit("20c1")
        c.imm("203c", slot * 4)
        c.imm("41f9", 0x405BC768)
        c.emit("d1c0")
        c.imm("223c", w.NAMES + index * 32)
        c.emit("2081 2041")
        for value in (0x42554620, (index + 49) << 24, 0, 0, 0, 0, 0, 0):
            c.imm("223c", value)
            c.emit("20c1")
    c.imm("23c6", STATE + RESTORED)
    c.emit("7001")
    c.imm("23c0", n.STATE + 16)
    c.emit("25400040")  # Ready is the final publication, after all names/slots.
    c.label("done")
    c.emit("7000")
    c.branch(0, "return")
    for name, status in (
        ("conflict", CONFLICT),
        ("capacity", CAPACITY),
        ("project", PROJECT),
    ):
        c.label(name)
        if name == "conflict":
            c.imm("23c2", STATE + SLOT)
        c.imm("203c", status)
        c.imm("23c0", STATE + STATUS)
        c.emit("70ff")
        c.branch(0, "return")
    c.label("return")
    c.emit("4cd77cfc 4fef0080 4e75")
    return c.finish(w.SETUP)
