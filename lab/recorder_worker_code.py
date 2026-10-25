"""Isolated OS 1.16 queued BUF worker. All orchestration is ColdFire code.

Scratch is emulator-owned; this module does not produce an installable image.
Old generations are pinned, never reclaimed on a guessed reader timeout.
"""

import struct

from lab import flex_native as f
from lab import flex_retirement as owner
from lab import recorder_freeze_code as n
from lab.emit import Code

DEST, NAMES = 0x10300000, 0x10300200  # Checked against the UI ABI at installation.

BASE = 0x10600000
STATE = BASE
ENTRY = BASE + 0x1000
ENTRY_BODY = BASE + 0x1200
WORKER = BASE + 0x1400
FINISH = BASE + 0x2000
SETUP = BASE + 0x2400
COPY = BASE + 0x3000
ACCEPT = BASE + 0x3400
LOOKUP = BASE + 0x3C00
DISCARD = BASE + 0x3D00
ABORT = BASE + 0x3F00
ASSIGN = BASE + 0x4200
RETIRE = BASE + 0x4600
ALLOC = BASE + 0x4900
PAGE_FILTER = BASE + 0x4A00
FLUSH = BASE + 0x4B00
FREEZE_GUARD = BASE + 0x4C00
HEADER = BASE + 0x9000
FREEZE_BODY = BASE + 0xA000
END = BASE + 0xB000
LEGACY = BASE + 0x5000
DISPATCH = BASE + 0x6000
SLOT_GUARDS = BASE + 0x7000
TRAMP = BASE + 0x8000
ERROR_ENTRY = BASE + 0x8100
ERROR_TEXT = BASE + 0x8200
ERROR_TABLE = BASE + 0x8300
ERROR_NAMES = BASE + 0x8400
USE_ENTRY, USE_WORKER, USE_FINISH = 0x40022FBE, 0x4001FC48, 0x4002196C
HOOKS = {
    USE_ENTRY: ("4879402297197e01", ENTRY),
    USE_WORKER: ("4fefffd848d73c3c", WORKER),
    USE_FINISH: ("4e56ffa4206e0008", FINISH),
}
ERRORS = {name: index for index, name in enumerate(f.USE_ERRORS)}
# State: native Flex ABI +56 destination,+60 epoch,+64 setup,+68 project pool,
# +72 private slot,+76 test fault,+80 success count,+84 retired source bytes,
# +96 four stable slots,+112 eight private slots,+144 old full cache key.


def call(c, address, pops=0):
    n.call(c, address, pops)


def entry():
    c = Code()
    c.imm("2039", DEST)
    c.emit("4a80")
    c.branch(7, "stock")
    c.imm("2039", STATE + 12)
    c.emit("4a80")
    c.branch(6, "body")
    c.emit("7000")
    c.imm("23c0", STATE + 160)
    c.emit("7001")
    c.imm("23c0", STATE + 88)
    c.imm("2039", DEST)
    c.imm("23c0", STATE + 56)
    c.imm("2039", n.STATE)
    c.imm("23c0", STATE + 60)
    c.label("body")
    c.imm("4ef9", ENTRY_BODY)
    c.label("stock")
    c.emit("7000")
    c.imm("23c0", STATE + 88)
    c.imm("4ef9", TRAMP)
    return c.finish(ENTRY)


def setup():
    c = Code()
    c.emit("4fefffe0 48d73c3c")  # D2-D5/A2-A5
    c.imm("45f9", STATE)
    call(c, 0x401988A2)
    c.emit("2f00")
    call(c, 0x40041D18, 4)
    c.emit("2040 2250 22690028 2f08 4e91 588f 4a80")
    c.branch(7, "bad")
    c.imm("0680", 0x1D2)
    c.emit("25400044 202a0040 4a80")
    c.branch(6, "done")
    c.emit("7401 7600 47ea0060")  # ascending visible then private slots
    c.label("scan")
    c.imm("0c82", 1024)
    c.branch(4, "bad")
    c.emit("2002 727f c081")
    c.branch(7, "next")
    c.emit("2002 d080 d080")
    c.imm("41f9", 0x405BA768)
    c.emit("d1c0 2010 4a80")
    c.branch(6, "next")
    c.emit("2002 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0 2010")
    c.imm("0c80", -1)
    c.branch(6, "next")
    c.emit("206a0044 2002 d080 d080 d080 d080 d1c0 2010")
    c.imm("0c80", -1)
    c.branch(6, "next")
    c.emit("26c2 068300000001")
    c.imm("0c83", 12)
    c.branch(7, "reserve")
    c.label("next")
    c.imm("0682", 1)
    c.branch(0, "scan")
    c.label("reserve")
    c.emit("41ea0060")
    c.imm("43f9", n.RESERVED)
    for _ in range(12):
        c.emit("22d8")
    c.emit("70ff 2280 7001 25400040")
    c.imm("23c0", n.STATE + 16)  # Own reservations before any worker can yield.
    # Native display names for four logical slots, including empty buffers.
    for index in range(4):
        c.emit(f"202a{96 + index * 4:04x} d080 d080 d080 d080")
        c.imm("41f9", 0x405B6368)
        c.emit("d1c0")
        for val in (0x42554620, (index + 49) << 24, 0, 0):
            c.imm("223c", val)
            c.emit("20c1")
        c.emit(f"202a{96 + index * 4:04x} d080 d080")
        c.imm("41f9", 0x405BC768)
        c.emit("d1c0")
        c.imm("223c", NAMES + index * 32)
        c.emit("2081 2041")
        for val in (0x42554620, (index + 49) << 24, 0, 0, 0, 0, 0, 0):
            c.imm("223c", val)
            c.emit("20c1")
    c.label("done")
    c.emit("7000")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd73c3c 4fef0020 4e75")
    return c.finish(SETUP)


def source_lookup():
    c = Code()
    c.imm("2079", STATE)
    c.imm("227c", 32)
    c.label("scan")
    c.imm("b1fc", 0)
    c.branch(7, "return")
    c.emit("22280004 b081")
    c.branch(7, "check")
    c.emit("2050")
    c.imm("d3fc", -1)
    c.imm("b3fc", 0)
    c.branch(6, "scan")
    c.branch(0, "bad")
    c.label("check")
    c.emit("22280014 4a81")
    c.branch(6, "return")
    c.label("bad")
    c.imm("207c", 0)
    c.label("return")
    c.emit("4e75")
    return c.finish(LOOKUP)


def worker(*, require_track=True):
    c = Code()
    c.imm("2039", STATE + 12)
    c.emit("4a80")
    c.branch(7, "stock")
    c.emit("4fefffd0 48d77cfc")
    c.imm("45f9", STATE)
    c.emit("202a003c")
    c.imm("2239", n.STATE)
    c.emit("b081")
    c.branch(6, "bad")
    c.emit("202a002c")
    c.imm("2239", 0x80004704)
    c.emit("b081")
    c.branch(6, "bad")
    if require_track:
        c.emit("202a0010")
        c.imm("0c80", 15)
        c.branch(2, "bad")
        c.imm("223c", 0x450)
        c.emit("4c010800 206a002c d1c0 7000 102800d6")
        f.sample_machine_guard(c, invalid="bad")
    c.emit("202a0004")
    c.imm("0c80", 8)
    c.branch(4, "bad")
    c.emit("202a004c")
    c.imm("0c80", 1)  # admission failure seam before setup/heap
    c.branch(7, "bad")
    call(c, SETUP)
    c.emit("4a80")
    c.branch(6, "bad")
    c.emit("202a0038")
    c.imm("0680", -1)
    c.emit("d080 d080 41ea0060 d1c0 2410 25420024")
    c.emit("202a0004 d080 d080 41ea0070 d1c0 2610 25430048")
    c.emit("2002 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0 43ea0090 22d8 22d8 22d8 22d8")
    # Source admission, hash, stock allocation/transport all execute natively.
    c.emit("2f03 2f2a0020 2f2a001c 2f2a0018 2f0a")
    call(c, ACCEPT, 20)
    c.imm("0c80", -1)
    c.branch(7, "bad")
    c.emit("2840 25400014")
    # Stock loader success is insufficient if final length is zero.
    c.emit("2003 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0 20280008")
    c.imm("0c80", 80)
    c.branch(3, "abort")
    c.emit("202a004c")
    c.imm("0c80", 2)  # unpublished candidate failure seam
    c.branch(7, "abort")
    c.emit("202a004c")
    c.imm("0c80", 6)
    c.branch(6, "complete")
    c.emit("202a003c 5280 2540003c")
    c.label("complete")
    c.emit("7000")
    c.branch(0, "return")
    c.label("abort")
    c.emit("2f0c")
    call(c, ABORT, 4)
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd77cfc 4fef0030 4e75")
    c.label("stock")
    c.imm("4ef9", TRAMP + 32)
    return c.finish(WORKER)


def finish():
    # Keep native Flex's stock completion UI, using our assignment primitive.
    # Its busy flag is cleared before assignment; worker-only slot guards have
    # already finished before this UI-thread phase.
    body = f.recorder_use_finish(FINISH + 32, STATE, ASSIGN, TRAMP + 64, ERRORS)
    c = Code()
    c.imm("2039", STATE + 12)
    c.emit("4a80")
    c.branch(7, "stock")
    c.imm("4ef9", FINISH + 32)
    c.label("stock")
    c.imm("4ef9", TRAMP + 64)
    prefix = c.finish(FINISH)
    return prefix.ljust(32, b"\x00") + body


def assign(*, assign_track=True):
    """Publish the logical association; historical adapters may also assign."""
    c = Code()
    c.emit("4fefffd0 48d77cfc")
    c.imm("45f9", STATE)
    c.emit("286a0014 242a0024 262a0048")
    c.emit("202a002c")
    c.imm("2239", 0x80004704)
    c.emit("b081")
    c.branch(6, "abort")
    c.emit("202a003c")
    c.imm("2239", n.STATE)
    c.emit("b081")
    c.branch(6, "abort")
    if assign_track:
        c.emit("202a0010")
        c.imm("223c", 0x450)
        c.emit("4c010800 206a002c d1c0 7000 102800d6")
        f.sample_machine_guard(c, invalid="abort")
    c.emit("7001 2540000c")
    c.emit("2f02")
    call(c, n.UNLOAD, 4)
    c.emit("2f02")
    call(c, n.CLEAR, 4)
    c.emit("2f02 41ec0004 2f08")
    call(c, 0x40154540, 8)
    c.emit("4a80")
    c.branch(6, "restore")
    c.emit("202a00a0")
    c.imm("0c80", 1)
    c.branch(6, "restore")
    c.emit("202a004c")
    c.imm("0c80", 3)
    c.branch(7, "restore")
    c.emit("2f2a003c 2f03 2f02 2f2a0038")
    call(c, n.REGISTER, 16)
    c.emit("4a80")
    c.branch(6, "restore")
    if assign_track:
        c.emit("2f2a002c 2f2a0010 2f02")
        call(c, ASSIGN + 0x500, 12)
        c.emit("4a80")
        c.branch(6, "restore")
    # Restore the logical name after the stock cache-hit name association.
    c.emit("202a0038")
    c.imm("0680", -1)
    c.emit("e588 e588 d080")  # buffer index * 32
    c.imm("41f9", NAMES)
    c.emit("d1c0 2248 2002 d080 d080 d080 d080")
    c.imm("41f9", 0x405B6368)
    c.emit("d1c0 20d9 20d9 20d9 20d9")
    # Project metadata has stable buffer identity, not a transient source ID.
    c.emit("2002 d080 d080 d080 d080 206a0044 d1c0")
    c.emit("202a0038")
    c.imm("0680", 0x7FFD0000)
    c.emit("20c0 202a003c 20c0 7000 20c0 2080 202a0050 5280 25400050")
    c.emit("2f0c")
    call(c, RETIRE, 4)
    call(c, FLUSH)
    c.emit("7000 2540000c")
    c.branch(0, "return")
    c.label("restore")
    c.emit("2f02")
    call(c, n.UNLOAD, 4)
    c.emit("2f02")
    call(c, n.CLEAR, 4)
    c.emit("202a0090")
    c.imm("0c80", -1)
    c.branch(7, "abort")
    c.emit("2f02 41ea0090 2f08")
    call(c, 0x40154540, 8)
    c.emit("2540005c")  # Failed restoration is observable; pins stay retained.
    c.label("abort")
    c.emit("2f0c")
    call(c, ABORT, 4)
    c.emit("7000 2540000c 254000a0 70ff")
    c.label("return")
    c.emit("4cd77cfc 4fef0030 4e75")
    return c.finish(ASSIGN)


def retire():
    c = Code()
    c.emit("4feffff8 48d70404 246f000c 242a0014 7000 25400014")
    c.emit("202a000c")
    c.imm("2239", STATE + 84)
    c.emit("2040 2001 d1c0 2208")
    c.imm("23c1", STATE + 84)
    c.emit("2f02")
    call(c, 0x4011E8FC, 4)
    c.emit("7000 4cd70404 508f 4e75")
    return c.finish(RETIRE)


def resource_dispatch(op, address, native, legacy):
    c = Code()
    if op in ("resolve", "open", "close"):
        c.emit("206f0004")
        c.imm("b1fc", 0)
        c.branch(7, "native")
        c.emit("2010")
    elif op == "read":
        c.emit("206f000c")
        c.imm("b1fc", 0)
        c.branch(7, "native")
        c.emit("2010")
    else:
        c.emit("202f0004")
    c.imm("0c80", f.FIRST_ID)
    c.branch(5, "native")
    c.imm("0c80", f.LAST_ID)
    c.branch(2, "native")
    c.imm("0680", -f.FIRST_ID)
    c.emit("ed88")
    c.imm("41f9", n.GEN)
    c.emit("d1c0 2010 4a80")
    c.branch(6, "native")
    c.imm("2039", STATE + 12)
    c.imm("0c80", 1)
    c.branch(6, "native")
    c.imm("4ef9", legacy)
    c.label("native")
    c.imm("4ef9", native)
    return c.finish(address)


def slot_guard(address, fallback, *, load=False):
    c = Code()
    for at in (STATE + 12, n.STATE + 24):
        c.imm("2039", at)
        c.imm("0c80", 1)
        c.branch(7, "stock")
    c.emit("202f" + ("0008" if load else "0004"))
    c.imm("41f9", n.RESERVED)
    c.label("next")
    c.emit("2218")
    c.imm("0c81", -1)
    c.branch(7, "stock")
    c.emit("b081")
    c.branch(7, "deny")
    c.branch(0, "next")
    c.label("stock")
    c.imm("4ef9", fallback)
    c.label("deny")
    c.emit("70ff 4e75" if load else "7000 4e75")
    return c.finish(address)


def page_filter():
    """Hold logical headers until commit; private PCM pages go straight through."""
    c = Code()
    c.emit("4feffff4 48d70c04")
    for at, condition in ((STATE + 12, 6), (STATE + 164, 7)):
        c.imm("2039", at)
        c.imm("0c80", 1)
        c.branch(condition, "stock")
    c.emit("242f0010")
    c.imm("0c82", -1)
    c.branch(6, "stock")
    c.emit("246f0014 2012")
    c.imm("2239", STATE + 36)
    c.emit("b081")
    c.branch(6, "stock")
    c.emit("202a0010 4a80")
    c.branch(7, "drop")
    c.imm("2039", STATE + 76)
    c.imm("0c80", 5)  # Native missing-final-header fault seam.
    c.branch(7, "drop")
    c.emit("204a")
    c.imm("43f9", HEADER)
    c.imm("203c", 4096)
    c.label("byte")
    c.emit("12d8")
    c.imm("0680", -1)
    c.branch(6, "byte")
    c.emit("202f0018")
    c.imm("23c0", STATE + 168)
    c.emit("7001")
    c.imm("23c0", STATE + 160)
    c.label("drop")
    c.emit("7000 4cd70c04 4fef000c 4e75")
    c.label("stock")
    c.emit("4cd70c04 4fef000c")
    c.imm("4ef9", TRAMP + 96)
    return c.finish(PAGE_FILTER)


def flush():
    c = Code()
    c.emit("7001")
    c.imm("23c0", STATE + 164)
    c.imm("2039", STATE + 168)
    c.emit("2f00")
    c.imm("4879", HEADER)
    c.emit("70ff 2f00")
    call(c, 0x400CD638, 12)
    c.emit("7000")
    c.imm("23c0", STATE + 164)
    c.imm("23c0", STATE + 160)
    c.emit("4e75")
    return c.finish(FLUSH)


def freeze_guard():
    c = Code()
    c.imm("2039", STATE + 12)
    c.emit("4a80")
    c.branch(6, "busy")
    c.imm("4ef9", FREEZE_BODY)
    c.label("busy")
    c.emit("70ff 4e75")
    return c.finish(FREEZE_GUARD)


def error_entry():
    c = Code()
    c.imm("2039", STATE + 88)
    c.emit("4a80")
    c.branch(7, "stock")
    c.imm("4ef9", ERROR_TEXT)
    c.label("stock")
    c.imm("4879", 0x40229675)
    c.imm("4ef9", 0x4002198C)
    return c.finish(ERROR_ENTRY)


def allocator():
    """Failure seam asks the real stock heap for an impossible allocation."""
    c = Code()
    c.emit("202f0004")
    c.imm("0c80", 64)
    c.branch(7, "stock")
    c.imm("2039", STATE + 76)
    c.imm("0c80", 4)
    c.branch(6, "stock")
    c.imm("4879", 0x4000001)
    call(c, 0x4011E8F0, 4)
    c.emit("4e75")
    c.label("stock")
    c.imm("4ef9", 0x4011E8F0)
    return c.finish(ALLOC)


def payload():
    parts = {
        ENTRY: entry(),
        ENTRY_BODY: f.recorder_use_entry(ENTRY_BODY, STATE, follow_selected=True),
        WORKER: worker(),
        FINISH: finish(),
        SETUP: setup(),
        COPY: f.recording_copy(COPY),
        ACCEPT: f.accept_recording(
            ACCEPT, COPY, ERRORS, separate_source=True, discard=DISCARD
        ),
        LOOKUP: source_lookup(),
        DISCARD: owner.discard_candidate(DISCARD, ABORT),
        ABORT: owner.abort_source(ABORT),
        ASSIGN: assign(),
        ASSIGN + 0x500: f.assign_recording(ASSIGN + 0x500),
        RETIRE: retire(),
        ALLOC: allocator(),
        PAGE_FILTER: page_filter(),
        FLUSH: flush(),
        FREEZE_GUARD: freeze_guard(),
        FREEZE_BODY: n.freeze(),
        ERROR_ENTRY: error_entry(),
        ERROR_TEXT: f.recorder_error_text(ERROR_TEXT, STATE, ERROR_TABLE),
    }
    parts[ACCEPT] = parts[ACCEPT].replace(
        bytes.fromhex("4eb94011e8f0"), b"\x4e\xb9" + struct.pack(">I", ALLOC)
    )
    for i, (pc, (before, _)) in enumerate(HOOKS.items()):
        parts[TRAMP + i * 32] = (
            bytes.fromhex(before) + b"\x4e\xf9" + struct.pack(">I", pc + 8)
        )
    for i, (op, (_pc, _)) in enumerate(f.RESOURCE_SITES.items()):
        old = n.TRAMPOLINES + i * 32
        parts[LEGACY + i * 512] = f.resource_handler(LEGACY + i * 512, LOOKUP, op, old)
        parts[DISPATCH + i * 256] = resource_dispatch(
            op, DISPATCH + i * 256, n.HANDLERS + i * 512, LEGACY + i * 512
        )
    for i, _pc in enumerate((0x40154540, n.UNLOAD, n.CLEAR)):
        parts[SLOT_GUARDS + i * 256] = slot_guard(
            SLOT_GUARDS + i * 256, n.TRAMPOLINES + 0x800 + i * 32, load=i == 0
        )
    parts[TRAMP + 96] = (
        bytes.fromhex("4feffff448d70c04") + b"\x4e\xf9" + struct.pack(">I", 0x400CD640)
    )
    ordered = sorted(parts.items())
    for (a, b), (next_a, _) in zip(ordered, ordered[1:], strict=False):
        if a + len(b) > next_a:
            raise ValueError(f"Worker payload overlap {a:#x}")
    return parts
