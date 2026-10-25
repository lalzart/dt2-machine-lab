"""Single native Project::save owner and explicit prepare/commit/cleanup phases.

Callback ABI: prepares/cleanup receive the original three stack arguments;
prepares return exactly zero on success. Commit callbacks receive the unmodified
stock result followed by those three arguments. They report their own status.
The stock writer returns a byte bool; its full D0 result is returned unchanged.
"""

from dataclasses import dataclass

from lab.emit import Code
from lab.project import require

SITE = 0x40043A30
STOCK_PREFIX = bytes.fromhex("4fefffcc48d77c1c")


@dataclass(frozen=True)
class SavePhases:
    stock: int
    prepare: tuple[int, ...] = ()
    commit: tuple[int, ...] = ()
    cleanup: tuple[int, ...] = ()

    def __post_init__(self):
        callbacks = (self.stock, *self.prepare, *self.commit, *self.cleanup)
        require(
            all(type(x) is int and 0 < x < 2**32 and x % 2 == 0 for x in callbacks),
            "Invalid save callback",
        )
        require(
            len(callbacks) == len(set(callbacks)),
            "Save callback owns more than one phase",
        )


def dispatcher(address, phases):
    """Preserve D1-D7/A0-A6 and stack on every success/failure path."""
    c = Code()
    c.emit("4fefffc0 48d77ffe")

    def invoke(target, committed=False):
        c.emit("2f2f004c 2f2f004c 2f2f004c")
        if committed:
            c.emit("2f2f0048")  # saved stock result, adjusted for pushed args
        c.imm("4eb9", target)
        c.emit("4fef0010" if committed else "4fef000c")

    for target in phases.prepare:
        invoke(target)
        c.emit("4a80")
        c.branch(6, "aborted")
    invoke(phases.stock)
    c.emit("2f40003c")
    c.imm("0280", 255)
    c.imm("0c80", 1)
    c.branch(6, "cleanup")
    for target in phases.commit:
        invoke(target, committed=True)
    c.branch(0, "cleanup")
    c.label("aborted")
    c.emit("7000 2f40003c")
    c.label("cleanup")
    for target in phases.cleanup:
        invoke(target)
    c.emit("202f003c 4cd77ffe 4fef0040 4e75")
    return c.finish(address)


def stock_trampoline():
    return (
        STOCK_PREFIX
        + bytes.fromhex("4ef9")
        + (SITE + len(STOCK_PREFIX)).to_bytes(4, "big")
    )


def prepare_guard(address, prepare, stock):
    """Single-prepare specialization: standard call ABI, tail-call stock once.

    This form is only valid with no commit or cleanup subscribers. It retains
    the original arguments and stack; D0/D1/A0/A1 remain caller-clobbered.
    """
    c = Code()
    c.emit("2f2f000c 2f2f000c 2f2f000c")
    c.imm("4eb9", prepare)
    c.emit("4fef000c 4a80")
    c.branch(6, "failed")
    c.imm("4ef9", stock)
    c.label("failed")
    c.emit("7000 4e75")
    return c.finish(address)


def flex_prepare(address, persist):
    """Flex's exact before-serialization operation; zero means continue."""
    c = Code()
    c.emit("2f2f0004")
    c.imm("4eb9", 0x40041D18)
    c.emit("588f 2040 2250 22690028 2f08 4e91 588f 4a80")
    c.branch(7, "failed")
    c.imm("0680", 0x1D2)
    c.emit("2f00")
    c.imm("4eb9", persist)
    c.emit("588f 4e75")
    c.label("failed")
    c.emit("70ff 4e75")
    return c.finish(address)


def arp_callbacks(locations, arp):
    """Generate adapter callbacks using the existing native journal primitives."""
    from lab import arp_firmware as fw
    from lab import arp_firmware_storage as storage

    c = Code()
    c.emit(fw.PRESAVE)
    fw.ptr(c, arp)
    c.branch(7, "done")
    fw.setv(c, fw.PLAY, 0)
    fw.panic(c, arp)
    fw.setv(c, fw.BUSY, 1)
    c.emit("202f002c")
    fw.store(c, storage.SLOT)
    storage.addr(c, fw.MODES)
    storage.addr(c, fw.SAVE_MODES, 1)
    c.imm("243c", 128)
    c.label("snapshot")
    c.emit("22d8 5382")
    c.branch(6, "snapshot")
    c.label("done")
    c.emit("7000 " + fw.RESTORE + " 4e75")
    prepare = c.finish(locations["arp_prepare"])

    c = Code()
    c.emit(fw.PRESAVE)
    fw.ptr(c, arp)
    c.branch(7, "done")
    fw.load(c, storage.SLOT)
    c.imm("0c80", 128)
    c.branch(2, "failure")
    c.emit("2f00 7000 2f00")
    c.imm("4eb9", 0x400F4A74)
    c.emit("508f 4a80")
    c.branch(7, "failure")
    c.emit("2040 2010")
    fw.load(c, storage.SLOT, 1)
    c.emit("b081")
    c.branch(6, "failure")
    c.emit("2008")
    c.imm("0680", 12)
    fw.store(c, storage.BUFFER)
    fw.call(c, arp, "project_hash")
    c.emit("4a80")
    c.branch(7, "failure")
    c.emit("7001 2f00")
    fw.call(c, arp, "journal")
    c.emit("588f 4a80")
    c.branch(7, "failure")
    fw.setv(c, fw.STATUS, 1)
    c.branch(0, "done")
    c.label("failure")
    fw.setv(c, fw.STATUS, -1)
    c.label("done")
    c.emit(fw.RESTORE + " 4e75")
    commit = c.finish(locations["arp_commit"])

    c = Code()
    c.emit(fw.PRESAVE)
    fw.ptr(c, arp)
    c.branch(7, "done")
    fw.setv(c, fw.BUSY, 0)
    c.label("done")
    c.emit(fw.RESTORE + " 4e75")
    cleanup = c.finish(locations["arp_cleanup"])
    return dict(arp_prepare=prepare, arp_commit=commit, arp_cleanup=cleanup)
