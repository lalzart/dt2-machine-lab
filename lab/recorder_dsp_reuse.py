"""Restricted paused-emulator reclamation, never installed by normal builders.

The harness must stop both processors and supplies a closed-world certificate
plus an unmodified native DSP diagnostic. No hardware fence is implied.
The actual checks, tombstone and stock allocator release are ColdFire code.
"""

import struct

from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab.emit import Code
from lab.project import require

BASE, END = 0x10B00000, 0x10B04000
ENTRY, PROOF = BASE + 0x1000, BASE + 0x3000
CERTIFICATE = 0x51554945  # QUIE: explicit test-only exclusive pause assertion.


def command(*, first_id=n.FIRST_ID, last_id=n.FIRST_ID + 7, lookup=None,
            after_release=None):
    """release(id, epoch, kit, sequence) -> 0 or negative, no host mutation."""
    c = Code()
    c.emit("4fefffd0 48d77cfc 242f0034 262f0038 282f003c 2a2f0040")
    c.emit("40c0")
    c.imm("0280", 0x700)
    c.imm("0c80", 0x700)
    c.branch(6, "unknown")
    for at in (w.STATE + 12, n.STATE + 24, q.STATE + 56, q.STOCK_BUSY):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "unknown")
    for at, reg in ((n.STATE, 3), (0x80004704, 4)):
        c.imm("2039", at)
        c.emit(f"b08{reg}")
        c.branch(6, "stale")
    c.imm("0c82", first_id)
    c.branch(5, "stale")
    c.imm("0c82", last_id)
    c.branch(2, "stale")
    if lookup is None:
        c.emit("2002")
        c.imm("0680", -n.FIRST_ID)
        c.emit("ed88")
        c.imm("49f9", n.GEN)
        c.emit("d9c0")
    else:
        c.emit("2f02")
        n.call(c, lookup, 4)
        c.emit("4a80")
        c.branch(7, "stale")
        c.emit("2840")
    c.emit("2014")
    c.imm("0c80", 1)
    c.branch(6, "stale")
    c.emit("202c0004 b082")
    c.branch(6, "stale")
    c.emit("202c0008 b083")
    c.branch(6, "stale")
    c.emit("2c2c0024")  # D6 private slot.
    # Snapshots keep the original generation's canonical key.
    c.imm("41f9", n.SNAP)
    c.emit("7e08")
    c.label("snap")
    c.emit("2010 4a80")
    c.branch(7, "next_snap")
    c.emit("20280010 b082")
    c.branch(7, "frozen")
    c.label("next_snap")
    c.emit("41e80040")
    c.imm("0687", -1)
    c.branch(6, "snap")
    c.imm("4bf9", PROOF)
    for off, reg in ((4, 2), (8, 3), (12, 5)):
        c.emit(f"202d{off:04x} b08{reg}")
        c.branch(6, "stale")
    c.emit("2015")
    c.imm("0c80", CERTIFICATE)
    c.branch(6, "unknown")
    # Only the final private descriptor may remain. No observed readers,
    # logical/snapshot/preview/other descriptors, cached or incoming selections.
    for off in (24, 28, 32, 40, 44, 48, 52, 56, 60, 64):
        c.emit(f"202d{off:04x} 4a80")
        c.branch(6, "dsp_busy")
    c.emit("202d0024")
    c.imm("0c80", 1)
    c.branch(6, "unknown")
    c.emit("202d0044 222d0048 b081")
    c.branch(6, "stale")
    c.emit("4a80")
    c.branch(7, "stale")
    c.emit("202d004c 222d0050 b081")
    c.branch(3, "stale")  # completed control serial must advance past request.
    # Find the private slot's allocation record through the original table.
    c.emit("2006 d080 d080")
    c.imm("41f9", 0x405B5368)
    c.emit("d1c0 2010")
    c.imm("0c80", 0x10000)
    c.branch(4, "unknown")
    c.imm("223c", 0x34)
    c.emit("4c010800")
    c.imm("2679", 0x405A0F64)
    c.emit("d7c0")
    c.imm("2239", 0x405A0F68)
    c.emit("200b b081")
    c.branch(4, "unknown")
    for off, proof_off in ((16, 16), (20, 20)):
        c.emit(f"202b{off:04x} 222d{proof_off:04x} b081")
        c.branch(6, "stale")
    c.emit("202b0030")
    c.imm("0c80", 1)
    c.branch(6, "alias")
    # On-demand CPU key/project scan; only this private owner may name A.
    c.emit("7e00")
    c.imm("41f9", 0x405B1368)
    c.imm("2279", w.STATE + 68)
    c.label("slots")
    for opcode in ("2010", "2011"):
        c.emit(opcode + " b082")
        c.branch(6, "skip_" + opcode)
        c.emit("2007 b086")
        c.branch(6, "alias")
        c.label("skip_" + opcode)
    c.emit("41e80010 43e90010")
    c.imm("0687", 1)
    c.imm("0c87", 1024)
    c.branch(6, "slots")
    # Exact full cache key must still belong to the private slot.
    c.emit("2006 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0")
    for off in range(0, 16, 4):
        c.emit(f"2028{off:04x} 222c{16 + off:04x} b081")
        c.branch(6, "stale")
    # All possible refusal points precede mutation. Preserve immutable ID/key
    # and tombstone before removing the last owner; IDs are never reissued.
    c.emit("7003 2880 7000 2a80")  # status=3; consume certificate.
    c.emit("2006 d080 d080 d080 d080")
    c.imm("2079", w.STATE + 68)
    c.emit("d1c0 70ff 20c0 7000 20c0 20c0 2080")
    c.emit("7001")
    c.imm("23c0", n.STATE + 24)  # Private native operation, paused lease only.
    c.emit("2f06")
    n.call(c, n.UNLOAD, 4)
    c.emit("7000")
    c.imm("23c0", n.STATE + 24)
    if after_release is not None:
        c.emit("2f0c")
        n.call(c, after_release, 4)
    c.branch(0, "return")
    for label, value in (
        ("unknown", -1),
        ("stale", -2),
        ("frozen", -3),
        ("dsp_busy", -4),
        ("alias", -5),
    ):
        c.label(label)
        c.emit(f"{0x7000 | (value & 255):04x}")
        c.branch(0, "return")
    c.label("return")
    c.emit("4cd77cfc 4fef0030 4e75")
    return c.finish(ENTRY)


def install(fw):
    for at in range(BASE, END, 4096):
        fw.m.ensure(at)
        fw.write(at, bytes(4096))
    block = command()
    require(ENTRY + len(block) <= PROOF, "Reclaim payload overlap")
    fw.write(ENTRY, block)
    fw.uc.ctl_remove_cache(BASE, END)
    return block


def deliver(fw, view, allocation, *, exclusive=False):
    """Modeled transport of real native observations, never fabricated success.

    exclusive=True is a harness assertion of the restricted closed world;
    general ownership is intentionally unknown without that assertion.
    """
    words = [
        CERTIFICATE if exclusive else 0,
        view[12],
        view[11],
        view[13],
        allocation["start"],
        allocation["size"],
        *view[15:25],
        view[25],
        view[5],
        view[10],
        view[4],
        view[34],
    ]
    fw.write(PROOF, struct.pack(">21I", *words))
