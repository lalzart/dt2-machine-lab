"""Native pinned-source ownership and exact-match durable handover."""

from lab.emit import Code
from lab.flex_native import RESOURCE_SITES


def mask(c):
    """Save SR in D1 and raise IPL without changing S/M/other mode bits."""
    c.emit("40c1 2001")
    c.imm("0080", 0x700)
    c.emit("46c0")


def pin_source(address):
    """Return pinned RAM pointer, zero for backing, or -1 on count overflow."""
    c = Code()
    c.emit("206f0004")
    mask(c)
    c.emit("20280038")
    c.emit("4a80")
    c.branch(6, "overflow")
    c.emit("22680014")
    c.imm("b3fc", 0)
    c.branch(7, "done")
    c.emit("20280030")
    c.imm("0c80", -1)
    c.branch(7, "overflow")
    c.emit("5280 21400030")
    c.label("done")
    c.emit("46c1 2009 4e75")
    c.label("overflow")
    c.emit("46c1 70ff 4e75")
    return c.finish(address)


def unpin_source(address, *, abort=0):
    """Release one active copy, preserving the source until a retirement call."""
    c = Code()
    c.emit("206f0004")
    mask(c)
    c.emit("20280030")
    c.emit("4a80")
    c.branch(7, "underflow")
    c.imm("0680", -1)
    c.emit("21400030 46c1")
    if abort:
        c.emit("20280038")
        c.imm("0c80", 1)
        c.branch(6, "done")
        c.imm("4ef9", abort)
        c.label("done")
    c.emit("7000 4e75")
    c.label("underflow")
    c.emit("46c1 70ff 4e75")
    return c.finish(address)


def abort_source(address):
    """Invalidate an uncommitted candidate and free once active copies finish.

    Caller must own a failed USE transaction that never published a project
    reference. The descriptor/identity remains a tombstone until reboot.
    """
    c = Code()
    c.emit("4feffff8 48d70404 246f000c")
    mask(c)
    c.emit("7001 25400038 202a0030")
    c.emit("4a80")
    c.branch(6, "pinned")
    c.emit("242a0014 7000 25400014 46c1")
    c.emit("4a82")
    c.branch(7, "done")
    c.emit("2f02")
    c.imm("4eb9", 0x4011E8FC)
    c.emit("588f")
    c.label("done")
    c.emit("7000")
    c.branch(0, "return")
    c.label("pinned")
    c.emit("46c1 7001")
    c.label("return")
    c.emit("4cd70404 508f 4e75")
    return c.finish(address)


def discard_candidate(address, abort):
    """Abort the candidate, then clear only its matching stock loader slot."""
    c = Code()
    c.emit("4feffff8 48d70404 246f000c 2f0a")
    c.imm("4eb9", abort)
    c.emit("588f 242a0018 2002 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0")
    for i in range(4):
        c.emit(f"2028{i * 4:04x} 222a{4 + i * 4:04x} b081")
        c.branch(6, "done")
    c.emit("2f02")
    c.imm("4eb9", 0x401540C6)
    c.imm("4eb9", 0x40153BEA)
    c.emit("588f")
    c.label("done")
    c.emit("7000 4cd70404 508f 4e75")
    return c.finish(address)


def retire_source(address):
    """Try validated backing handover; 0 freed, 1 retained/already absent.

    Descriptor identity is never recycled. Active copies pin RAM. A transient
    validation owner excludes double retirement; the cached full reference and
    reader count are rechecked before the source pointer is detached. File I/O
    and heap free execute with the incoming interrupt mask restored.
    """
    c = Code()
    c.emit("4fefffe0 48d70404 246f0024")
    mask(c)
    for offset, expected in ((52, 0), (48, 0), (28, 1)):
        c.emit(f"202a{offset:04x}")
        c.imm("0c80", expected)
        c.branch(6, "retained_unclaimed")
    c.emit("202a0014")
    c.emit("4a80")
    c.branch(7, "retained_unclaimed")
    c.emit("7001 25400034 41ea0020 43ef0008 22d8 22d8 22d8 22d8 46c1")
    c.emit("41ef0018 2f08 41ef000c 2f08")
    c.imm("4eb9", RESOURCE_SITES["resolve"][0])
    c.emit("508f 2400")
    mask(c)
    c.emit("5382")
    c.branch(6, "retained")
    for i in range(4):
        c.emit(f"202a{32 + i * 4:04x} 242f{8 + i * 4:04x} b082")
        c.branch(6, "retained")
    c.emit("202a0030")
    c.emit("4a80")
    c.branch(6, "retained")
    c.emit("242a0014 7000 25400014 25400034 46c1 2f02")
    c.imm("4eb9", 0x4011E8FC)
    c.emit("588f 7000")
    c.branch(0, "return")
    c.label("retained")
    c.emit("7000 25400034")
    c.label("retained_unclaimed")
    c.emit("46c1 7001")
    c.label("return")
    c.emit("4cd70404 4fef0020 4e75")
    return c.finish(address)


def read_backing(address):
    """int read_backing(node, dest, count, position).

    Open a fresh stock handle from the full cached durable reference, read at
    the requested byte position, and close it before returning. Synthetic
    handles can consequently remain descriptor/position values, rather than
    borrowing the source allocation across calls. The node remains owned.

    OS 1.16 reference-open returns 1 for an exact four-word reference match.
    Positive statuses 2-4 are recovery matches: close them without reading.
    The stock read entry consumes/advances handle+4 and checks handle+12.
    """
    c = Code()
    c.emit("4fefffe8 48d70404 246f001c 202a001c")
    c.imm("0c80", 1)
    c.branch(6, "failed")
    c.emit("41ef0008 2f08 41ea0020 2f08")
    c.imm("4eb9", RESOURCE_SITES["open"][0])
    c.emit("508f")
    c.emit("4a80")
    c.branch(15, "failed")
    # Positive recovery matches have opened a handle too; close without reading.
    c.emit("74ff")
    c.emit("5380")
    c.branch(6, "close")
    c.emit("202f0028 2f40000c 41ef0008 2f08 2f2f0028 2f2f0028")
    c.imm("4eb9", RESOURCE_SITES["read"][0])
    c.emit("4fef000c 2400")
    c.label("close")
    c.emit("41ef0008 2f08")
    c.imm("4eb9", RESOURCE_SITES["close"][0])
    c.emit("588f 2002")
    c.branch(0, "return")
    c.label("failed")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70404 4fef0018 4e75")
    return c.finish(address)


def save_owned(address, pin, unpin, backing, raw_save):
    """Save pinned RAM or stream backing through one 32 KiB scratch block.

    Validate a prefix before creating a destination. The writer rechecks backing
    identity on each chunk and verifies final hash/length. Failure releases only
    scratch/pins and leaves descriptor and references intact.
    """
    c = Code()
    c.emit("4feffff0 48d70c0c 246f0014 7600 2f0a")
    c.imm("4eb9", pin)
    c.emit("588f 2640")
    c.imm("0c80", -1)
    c.branch(7, "failed")
    c.emit("4a80")
    c.branch(7, "backing")
    c.emit("7000")
    c.branch(0, "save")
    c.label("backing")
    c.imm("203c", 0x8000)
    c.emit("2f00")
    c.imm("4eb9", 0x4011E8F0)
    c.emit("588f 2640 4a80")
    c.branch(7, "failed")
    c.emit("7601 7000 2f00 7010 2f00 2f0b 2f0a")
    c.imm("4eb9", backing)
    c.emit("4fef0010")
    c.imm("0c80", 16)
    c.branch(6, "read_failed")
    c.emit("200b")
    c.label("save")
    c.emit("2f00 2f2f0020 2f2f0020 2f0a")
    c.imm("4eb9", raw_save)
    c.emit("4fef0010 2400")
    c.branch(0, "cleanup")
    c.label("read_failed")
    c.emit("74ff")
    c.label("cleanup")
    c.emit("4a83")
    c.branch(7, "unpin")
    c.emit("2f0b")
    c.imm("4eb9", 0x4011E8FC)
    c.emit("588f")
    c.branch(0, "result")
    c.label("unpin")
    c.emit("2f0a")
    c.imm("4eb9", unpin)
    c.emit("588f")
    c.label("result")
    c.emit("2002")
    c.branch(0, "return")
    c.label("failed")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(address)
