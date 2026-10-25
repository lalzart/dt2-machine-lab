"""Native recorder DEST cell and reserved-slot filter shared by both installers.

The default addresses remain emulator scratch; the device builder relocates
these audited emitters explicitly. No host UI/runtime dependency.
"""

from lab.emit import Code

ARENA = 0x10300000  # Explicit host-mapped emulator scratch, not a target reservation.
STATE = ARENA
TABLE = ARENA + 0x80
NAMES = ARENA + 0x200
DRAW = ARENA + 0x400
SET = ARENA + 0x700
ROTATE = ARENA + 0x800
LABEL = ARENA + 0x100


def setter():
    c = Code()
    c.emit("202f0008 4a80")
    c.branch(7, "done")
    c.branch(11, "down")
    c.imm("2239", STATE)
    c.imm("0c81", 4)
    c.branch(4, "done")
    c.imm("0681", 1)
    c.branch(0, "store")
    c.label("down")
    c.imm("2239", STATE)
    c.emit("4a81")
    c.branch(7, "done")
    c.imm("0681", -1)
    c.label("store")
    c.imm("23c1", STATE)
    c.imm("4ef9", 0x4011AE46)
    c.label("done")
    c.emit("4e75")
    return c.finish(SET)


def rotation():
    """Add zero-based encoder C=2 only to the original ready/armed dispatch."""
    c = Code()
    c.emit("48780002 2f02")
    c.imm("4eb9", 0x40111732)
    c.emit("508f")
    c.imm("0280", 255)  # Stock predicate returns a byte-sized bool.
    c.branch(7, "stock")
    c.imm("4879", 0x44D2E61C)
    c.emit("2f02 41ea00a8 2f08")
    c.imm("4eb9", 0x40111B62)
    c.emit("4a80")
    c.branch(12, "scaled")
    c.imm("0680", 255)
    c.label("scaled")
    c.emit("e080 2f00 2f0a")
    c.imm("4eb9", SET)
    c.emit("4fef0014")
    c.imm("4ef9", 0x40020ECA)
    c.label("stock")
    c.emit("48780005 2f02")  # Displaced original ready dispatch prefix.
    c.imm("4ef9", 0x400209B4)
    return c.finish(ROTATE)


def cell():
    c = Code()
    # Replace the ready-page C-area REC NOW/YES graphic. The original YES
    # button handler and the complete E/MON draw/event paths remain untouched.
    for value in (0, 51, 95, 24, 64):
        c.imm("4879", value)
    c.emit("2f04")
    c.imm("4eb9", 0x40112ECE)
    c.emit("4fef0018")
    # Preserve the original reusable argument at SP; this jumps inside draw.

    def text(y, label=False):
        c.imm("4879", 0x402A6C30 if label else 0x402A96A0)
        c.emit("2f02")
        c.imm("4eb9", 0x401144F8)
        c.emit("508f")
        if label:
            c.imm("4879", LABEL)
        else:
            c.imm("2039", STATE)
            c.emit("d080 d080")
            c.imm("41f9", TABLE)
            c.emit("d1c0 2f10")
        for value in (2, y, 80):
            c.imm("4879", value)
        c.emit("2f02 2f04")
        c.imm("4eb9", 0x40113AE8)
        c.emit("4fef0018 2f02")
        c.imm("4eb9", 0x40114374)
        c.emit("588f")

    text(39)
    text(27, True)
    c.imm("4ef9", 0x400222B4)
    return c.finish(DRAW)


RESERVED = ARENA + 0x900
FILTER = ARENA + 0xA00
SEARCH_SITE = 0x40016728
SEARCH_BYTES = bytes.fromhex("20522f022f0a")


def allocation_filter():
    """First-free loop ABI: D2=index, A2=iterator, D3=project settings.

    Scratch D0/D1/A0 are overwritten by the original virtual call anyway.
    Skip only the native loop iteration, preserving its own capacity checks.
    The sentinel makes a fresh NORMAL session execute the original search.
    """
    c = Code()
    c.imm("41f9", RESERVED)
    c.label("next")
    c.emit("2218")  # MOVE.L (A0)+,D1
    c.imm("0c81", -1)
    c.branch(7, "stock")
    c.emit("2002 b081")  # Compare original D2 index with this reservation.
    c.branch(7, "skip")
    c.branch(0, "next")
    c.label("skip")
    c.imm("4ef9", 0x4001673A)
    c.label("stock")
    c.data.extend(SEARCH_BYTES)
    c.imm("4ef9", SEARCH_SITE + len(SEARCH_BYTES))
    return c.finish(FILTER)
