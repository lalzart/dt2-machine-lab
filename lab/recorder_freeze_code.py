"""Audited ColdFire metadata-only FREEZE command for isolated OS 1.16 tests.

All storage here is explicit emulator scratch, not a target reservation. Caller
must pause the GUI worker and mask interrupts. Old allocations remain pinned.
"""

import struct

from lab.emit import Code
from lab.flex_native import FIRST_ID, LAST_ID, RESOURCE_SITES

BASE = 0x10400000
STATE = BASE
GEN = BASE + 0x1000
SNAP = BASE + 0x1800
NAMES = BASE + 0x2000
GEN_NAME = BASE + 0x2400
LOOKUP = BASE + 0x3000
REGISTER = BASE + 0x3200
FREEZE = BASE + 0x3800
HANDLERS = BASE + 0x5000
TRAMPOLINES = BASE + 0x6000
GUARDS = BASE + 0x7000
SNAP_FIRST = 0x7FFC0001
SNAP_LAST = SNAP_FIRST + 7
RESERVED = 0x10300900  # Gate-A reservation table, checked by the adapter.
SAVE = 0x40043A30
LOAD_PROJECT = 0x400F5050
UNLOAD, CLEAR = 0x401540C6, 0x40153BEA


def call(c, address, pops=0):
    c.imm("4eb9", address)
    if pops:
        c.emit("4fef" + struct.pack(">h", pops).hex())


def lookup():
    c = Code()
    c.emit("202f0004")
    c.imm("0c80", FIRST_ID)
    c.branch(5, "snapshot")
    c.imm("0c80", LAST_ID)
    c.branch(2, "snapshot")
    c.imm("0680", -FIRST_ID)
    c.imm("41f9", GEN)
    c.branch(0, "index")
    c.label("snapshot")
    c.imm("0c80", SNAP_FIRST)
    c.branch(5, "bad")
    c.imm("0c80", SNAP_LAST)
    c.branch(2, "bad")
    c.imm("0680", -SNAP_FIRST)
    c.imm("41f9", SNAP)
    c.label("index")
    c.emit("ed88 d1c0 2010")  # index * 64, descriptor status
    c.imm("0c80", 1)
    c.branch(7, "epoch")
    c.imm("0c80", 2)  # preparing, private to paused native command
    c.branch(6, "bad")
    c.imm("2039", STATE + 24)
    c.imm("0c80", 1)
    c.branch(6, "bad")
    c.label("epoch")
    c.emit("20280008")
    c.imm("2239", STATE)
    c.emit("b081")
    c.branch(6, "bad")
    c.emit("20280004 222f0004 b081")
    c.branch(6, "bad")
    c.emit("2008 4e75")
    c.label("bad")
    c.emit("7000 4e75")
    return c.finish(LOOKUP)


def resource(operation, address, fallback):
    c = Code()
    c.emit("4feffff4 48d70c04")
    if operation in ("resolve", "open", "close"):
        c.emit("246f0010")
        c.imm("b5fc", 0)
        c.branch(7, "stock")
        c.emit("2012")
    elif operation == "read":
        c.emit("246f0018")
        c.imm("b5fc", 0)
        c.branch(7, "stock")
        c.emit("2012")
    else:
        c.emit("202f0010")
    c.emit("2400")
    c.imm("0c80", FIRST_ID)
    c.branch(5, "snapshot")
    c.imm("0c80", LAST_ID)
    c.branch(3, "owned")
    c.label("snapshot")
    c.imm("0c80", SNAP_FIRST)
    c.branch(5, "stock")
    c.imm("0c80", SNAP_LAST)
    c.branch(2, "stock")
    c.label("owned")
    c.emit("2f02")
    call(c, LOOKUP, 4)
    c.emit("4a80")
    c.branch(7, "bad")
    c.emit("2040")
    if operation == "resolve":
        for offset in range(0, 16, 4):
            c.emit("202a" + struct.pack(">H", offset).hex())
            c.emit("2228" + struct.pack(">H", 48 + offset).hex())
            c.emit("b081")
            c.branch(6, "bad")
        c.emit("226f0014 2282 7001")  # exact resolver status 1
    elif operation == "key":
        c.emit("226f0014 41e80010 22d8 22d8 22d8 22d8 7000")
    elif operation == "name":
        c.emit("226f0018 20680020")
        c.emit("22d8 " * 8)
        c.emit("202f0018")
    else:
        c.emit("70ff")  # no PCM source / open / read / size / synthetic close
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70c04 4fef000c 4e75")
    c.label("stock")
    c.emit("4cd70c04 4fef000c")
    c.imm("4ef9", fallback)
    return c.finish(address)


def register():
    """register(buf=1..4, visible_slot, private_pin, epoch), no PCM arguments."""
    c = Code()
    c.emit("4fefffd0 48d71c3c 242f0034 262f0038 282f003c 2a2f0040")
    c.imm("45f9", STATE)
    c.emit("2012 b085")
    c.branch(6, "bad")
    c.imm("0c82", 1)
    c.branch(5, "bad")
    c.imm("0c82", 4)
    c.branch(2, "bad")
    c.emit("2003 d080 d080 d080 d080")  # visible * 16
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0 2648 2010")
    c.imm("0c80", FIRST_ID)
    c.branch(5, "bad")
    c.imm("0c80", LAST_ID)
    c.branch(2, "bad")
    c.imm("0680", -FIRST_ID)
    c.emit("ed88")
    c.imm("41f9", GEN)
    c.emit("d1c0 2010")
    c.imm("0c80", 0)
    c.branch(6, "bad")
    c.emit("21450008 21440024 21530004 43e80010 204b 22d8 22d8 22d8 22d8")
    # A0 advanced after copying? Source is A0 and destination A1: use the
    # actual descriptor base again from the generation's source identity.
    c.emit("2013")
    c.imm("0680", -FIRST_ID)
    c.emit("ed88")
    c.imm("41f9", GEN)
    c.emit("d1c0")
    # Copy original key to logical ref, and install the generic generation name.
    c.emit("43e80030 41e80010 22d8 22d8 22d8 22d8")
    c.emit("2013")
    c.imm("0680", -FIRST_ID)
    c.emit("ed88")
    c.imm("41f9", GEN)
    c.emit("d1c0")
    c.imm("223c", GEN_NAME)
    c.emit("21410020")
    c.emit("7201 2081 25410010 2002")
    c.imm("0680", -1)
    c.emit("d080 d080")
    c.imm("41f9", STATE + 32)
    c.emit("d1c0 2083 7000")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd71c3c 4fef0030 4e75")
    return c.finish(REGISTER)


def project_guard(address, fallback):
    c = Code()
    c.imm("2039", STATE + 16)
    c.emit("4a80")
    c.branch(7, "stock")
    c.emit("7000 4e75")
    c.label("stock")
    c.imm("4ef9", fallback)
    return c.finish(address)


def freeze(*, address=FREEZE, worker_gate=None):
    """freeze(buf, epoch, expected_kit) -> slot or negative; diagnostic only.

    Native cache association; source/pin identity and serial checked before
    publishing. All post-association failures quarantine the consumed slot.
    """
    c = Code()
    c.emit("4fefff80 48d77cfc 242f0084 262f0088 2c2f008c")
    if worker_gate is None:
        c.emit("40c0")
        c.imm("0280", 0x700)
        c.imm("0c80", 0x700)
        c.branch(6, "bad")  # Preserve the original diagnostic contract.
    else:
        # A separate opt-in worker supplies an ownership gate, not a relaxed
        # public entry. The original diagnostic payload remains byte-exact.
        call(c, worker_gate)
        c.emit("4a80")
        c.branch(6, "bad")
    c.imm("45f9", STATE)
    c.emit("2012 b083")
    c.branch(6, "stale")
    c.imm("2039", 0x80004704)
    c.emit("b086")
    c.branch(6, "stale")
    c.emit("202a0018 4a80")
    c.branch(6, "bad")
    c.imm("0c82", 1)
    c.branch(5, "bad")
    c.imm("0c82", 4)
    c.branch(2, "bad")
    c.emit("2002")
    c.imm("0680", -1)
    c.emit("d080 d080")
    c.imm("41f9", STATE + 32)
    c.emit("d1c0 2810 4a84")
    c.branch(7, "empty")
    c.emit("2004 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0 2f10")
    call(c, LOOKUP, 4)
    c.emit("4a80")
    c.branch(7, "stale")
    c.emit("2840")  # A4 committed generation metadata
    # Check complete visible and private cache keys, not only an address.
    c.emit("2004 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0")
    for off in range(0, 16, 4):
        c.emit("2028" + struct.pack(">H", off).hex())
        c.emit("222c" + struct.pack(">H", 16 + off).hex())
        c.emit("b081")
        c.branch(6, "stale")
    c.emit("202c0024 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0")
    for off in range(0, 16, 4):
        c.emit("2028" + struct.pack(">H", off).hex())
        c.emit("222c" + struct.pack(">H", 16 + off).hex())
        c.emit("b081")
        c.branch(6, "stale")
    c.emit("2a2a0004")  # issued snapshot identities; never recycled
    c.imm("0c85", 8)
    c.branch(4, "full")
    # Original free-slot iterator ctor/search/dtor, including the Gate-A filter.
    c.emit("41ef0040 2f08")
    call(c, 0x40016576, 4)
    c.emit("41ef0040 2f08")
    call(c, 0x40016702, 4)
    c.emit("2e00 41ef0040 2f08")
    call(c, 0x4019977C, 4)
    c.imm("0c87", -1)
    c.branch(7, "full")
    c.emit("202a000c")
    c.imm("0c80", 1)
    c.branch(7, "full")
    # Derive the project pool using the original current-project ABI.
    call(c, 0x401988A2)
    c.emit("2f00")
    call(c, 0x40041D18, 4)
    c.emit("2040 2250 22690028 2f08 4e91 588f 4a80")
    c.branch(7, "stale")
    c.imm("0680", 0x1D2)
    c.emit("2c00 2005 ed88")
    c.imm("47f9", SNAP)
    c.emit("d7c0 2013 4a80")
    c.branch(6, "full")
    c.emit("2005")
    c.imm("0680", SNAP_FIRST)
    c.emit("27400004 27430008 27470024")
    c.emit("41ec0010 43eb0010 22d8 22d8 22d8 22d8")
    # Full new logical reference is distinct from its original cache key.
    c.emit("202b0004 27400030 27430034 202c001c 27400038 7000 2740003c")
    # Name table: eight fixed snapshot names for each of four buffers.
    c.emit("2002")
    c.imm("0680", -1)
    c.emit("ed88 e588")  # buffer index * 256
    c.imm("49f9", NAMES)
    c.emit("d9c0 2005 e588 e588 d080 d9c0 274c0020")
    c.emit("7002 2680 7001 25400018 2005")
    c.imm("0680", 1)
    c.emit("25400004")
    # A snapshot slot is never recycled, even if a partial operation fails.
    c.imm("41f9", RESERVED)
    c.label("reserve")
    c.emit("2210")
    c.imm("0c81", -1)
    c.branch(7, "reserve_here")
    c.emit("5888")
    c.branch(0, "reserve")
    c.label("reserve_here")
    c.emit("2087 72ff 21410004 202a000c")
    c.imm("0c80", 4)
    c.branch(6, "cache_fault")
    c.emit("2f07")
    call(c, CLEAR, 4)
    c.branch(0, "rollback")
    c.label("cache_fault")
    c.imm("0c80", 3)
    c.branch(6, "load")
    # Force a cache miss; native metadata-only OPEN must reject the reread.
    c.emit("202b0014")
    c.imm("0680", 2)
    c.emit("27400014")
    c.label("load")
    c.emit("2f07 41eb0030 2f08")
    call(c, 0x40154540, 8)
    c.emit("4a80")
    c.branch(6, "rollback")
    c.emit("202a000c")
    c.imm("0c80", 2)
    c.branch(7, "rollback")
    if worker_gate is not None:
        call(c, worker_gate)
        c.emit("4a80")
        c.branch(6, "rollback")
    # Stock cache hits name the original generation, not the logical alias.
    # Publish the snapshot basename using the same inline/pointer slot tables.
    c.emit("2007 d080 d080 d080 d080")
    c.imm("43f9", 0x405B6368)
    c.emit("d3c0 2809 206b0020 41e80006")
    c.imm("203c", 16)
    c.label("name_byte")
    c.emit("12d8")
    c.imm("0680", -1)
    c.branch(6, "name_byte")
    c.emit("2007 d080 d080")
    c.imm("41f9", 0x405BC768)
    c.emit("d1c0 2084")
    # Completed cache association exists; publish project identity last.
    c.emit("2007 d080 d080 d080 d080 2246 d3c0 41eb0030 22d8 22d8 22d8 22d8")
    c.emit("7001 2680 7000 25400018 2007")
    c.branch(0, "return")
    c.label("rollback")
    c.emit("2f07")
    call(c, UNLOAD, 4)
    c.emit("2f07")
    call(c, CLEAR, 4)
    # Slot remains quarantined; no header/read completion proof exists.
    c.emit("7003 2680 7000 25400018")
    c.emit("70fc")
    c.branch(0, "return")
    for label, value in (("empty", -2), ("stale", -3), ("full", -5), ("bad", -1)):
        c.label(label)
        c.emit(f"{0x7000 | (value & 255):04x}")
        c.branch(0, "return")
    c.label("return")
    c.emit("4cd77cfc 4fef0080 4e75")
    return c.finish(address)


def slot_guard(address, fallback, *, load=False):
    c = Code()
    c.imm("2039", STATE + 24)
    c.imm("0c80", 1)
    c.branch(7, "stock")
    c.emit("202f" + ("0008" if load else "0004"))
    for index in range(8):
        c.imm("41f9", SNAP + index * 64)
        c.emit("2210")
        c.imm("0c81", 0)
        c.branch(7, f"next{index}")
        c.emit("22280024 b081")
        c.branch(7, "deny")
        c.label(f"next{index}")
    c.label("stock")
    c.imm("4ef9", fallback)
    c.label("deny")
    c.emit("70ff 4e75" if load else "7000 4e75")
    return c.finish(address)


def payload():
    result = {LOOKUP: lookup(), REGISTER: register(), FREEZE: freeze()}
    originals = {}
    for index, (op, (pc, expected)) in enumerate(RESOURCE_SITES.items()):
        tramp = TRAMPOLINES + index * 32
        originals[pc] = bytes.fromhex(expected)
        result[tramp] = (
            bytes.fromhex(expected)
            + b"\x4e\xf9"
            + struct.pack(">I", pc + len(bytes.fromhex(expected)))
        )
        result[HANDLERS + index * 512] = resource(op, HANDLERS + index * 512, tramp)
    return result, originals
