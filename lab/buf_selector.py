"""Opt-in OS1.16 quick-list aliases. Menu ranks never enter sample storage.

Uses vacant space inside the existing next-bar arena; no new PCM allocation,
sample numbering, generation identity or DSP state. Stock full browser remains.
"""

import struct

from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_worker_code as w
from lab.dt2_116 import BASE as MAIN_BASE
from lab.dt2_116 import STOCK_SHA
from lab.emit import Code
from lab.project import require

BASE, END = nb.BASE + 0x6000, nb.END
INVERSE, FORWARD = BASE + 0x100, BASE + 0x400
BUILD, COUNT, CURSOR, INITIAL = BASE + 0x700, BASE + 0x900, BASE + 0xA00, BASE + 0xC00
RESOLVE, FORMAT, NORMAL = BASE + 0xD00, BASE + 0xF00, BASE + 0x1200
BUILD_STOCK, FORMAT_STOCK, NAMES = BASE + 0x1400, BASE + 0x1440, BASE + 0x1500
KEY_STOCK, SCALER = BASE + 0x1460, BASE + 0x1300
SCALER_INIT = BASE + 0x1484
VIEW_ENABLED = BASE + 0x1480  # Latched on rebuild, outside the 256-byte scaler.
KEY, NAVIGATE, ROTATE = BASE + 0x1600, BASE + 0x1800, BASE + 0x1C00
BANK = BASE + 0x1D00
MOVE_RANK = BASE + 0x1F00
POINTERS = {0x401EE50C: (0x40111C50, ROTATE)}
# Immediate predecessor of A00 is BUF 1: top-to-bottom BUF 4,3,2,1,A00,A01...
HOOKS = {
    0x4001E31A: ("4fefff7848d77cfc", BUILD),
    0x4001E47C: ("b9fc000000806694", COUNT),
    0x4001E0AC: ("2f0a2f02246f000c", CURSOR),
    0x4001E5BC: ("716a00a202808000007f6c085380728080815280", INITIAL),
    0x4001E1BE: ("727fb2806522", RESOLVE),
    0x4001DFBE: ("4fefffe048d7047c", FORMAT),
    0x4001DFEA: ("2052736800a2", NORMAL),
    0x4001EBC8: ("4e56ffc448d70c3c", KEY),
}


def qualified(c, bad):
    c.imm("2239", VIEW_ENABLED)
    c.imm("0c81", 1)
    c.branch(6, bad)
    ready_mapping(c, bad)


def ready_mapping(c, bad):
    c.imm("2239", w.STATE + 64)
    c.imm("0c81", 1)
    c.branch(6, bad)
    # Initializer owns the mapping. Never use half-initialized or invalid slots.
    for i in range(4):
        c.imm("2239", n.STATE + 32 + i * 4)
        c.imm("0c81", 1)
        c.branch(5, bad)
        c.imm("0c81", 1023)
        c.branch(2, bad)


def inverse():
    """(view*, actual slot) -> menu rank; writes only view's current bank cell.

    Original slot at view+0xa0 is kept for stock NO restoration. D0/D1/A0/A1
    are scratch, all other registers preserved. No loader or parameter call.
    """
    c = Code()
    c.emit("4feffff0 48d7040c 246f0014 242f0018")
    c.imm("0c82", 1023)
    c.branch(2, "invalid")
    qualified(c, "ordinary")
    for i in range(4):
        c.imm("2239", n.STATE + 32 + i * 4)
        c.emit("b481")
        c.branch(7, "buf" + str(i))
    c.imm("0c82", 128)
    c.branch(4, "ordinary")
    c.emit("354200a2 2002")
    c.imm("0680", 4)
    c.branch(0, "done")
    for i in range(4):
        c.label("buf" + str(i))
        c.emit("7000 354000a2")
        c.imm("203c", 3 - i)
        c.branch(0, "done")
    c.label("invalid")
    c.emit("7400")
    c.label("ordinary")
    c.emit("354200a2 2002")
    c.imm("0280", 127)
    c.label("done")
    c.emit("4cd7040c 4fef0010 4e75")
    return c.finish(INVERSE)


def forward():
    """(bank representative, menu rank) -> actual sample slot, or OFF on bad rank."""
    c = Code()
    c.emit("4feffff0 48d7040c 242f0014 262f0018")
    c.imm("0c82", 1023)
    c.branch(2, "bad")
    c.imm("0c82", 128)
    c.branch(4, "ordinary")
    qualified(c, "ordinary")
    c.imm("0c83", 132)
    c.branch(4, "bad")
    c.imm("0c83", 4)
    c.branch(4, "normal_a")
    for rank in range(4):
        c.imm("0c83", rank)
        c.branch(7, "buf" + str(rank))
    for rank in range(4):
        c.label("buf" + str(rank))
        c.imm("2039", n.STATE + 32 + (3 - rank) * 4)
        c.branch(0, "done")
    c.label("normal_a")
    c.emit("2003")
    c.imm("0680", -4)
    c.branch(0, "done")
    c.label("ordinary")
    c.imm("0c83", 128)
    c.branch(4, "bad")
    c.emit("2002")
    c.imm("0280", 0x380)
    c.emit("d083")
    c.branch(0, "done")
    c.label("bad")
    c.emit("7000")
    c.label("done")
    c.emit("4cd7040c 4fef0010 4e75")
    return c.finish(FORWARD)


def build_rows(*, navigation_fixes=False):
    c = Code()
    c.emit("4feffff0 48d7040c 246f0014 7400 342a00a2")
    n.call(c, nb.INIT_BODY)
    # EncoderFilter owns an allocated Timer; construct the module-lifetime
    # object once. Rebuilding a menu must not replace its registered timer.
    c.imm("2039", SCALER_INIT)
    c.imm("0c80", 1)
    c.branch(7, "scaler_ready")
    c.imm("4879", SCALER)
    n.call(c, 0x40111888, 4)
    c.emit("7001")
    c.imm("23c0", SCALER_INIT)
    c.label("scaler_ready")
    c.emit("7000")
    c.imm("23c0", VIEW_ENABLED)
    ready_mapping(c, "built_mode")
    c.emit("7001")
    c.imm("23c0", VIEW_ENABLED)
    c.label("built_mode")
    if not navigation_fixes:
        c.emit("2f02 2f0a")
        n.call(c, INVERSE, 8)
    c.emit("2f0a")
    n.call(c, BUILD_STOCK, 4)
    c.emit("2f02 2f0a")
    n.call(c, CURSOR, 8)
    c.emit("4cd7040c 4fef0010 4e75")
    return c.finish(BUILD)


def count():
    c = Code()
    c.emit("7000 302b00a2")
    c.imm("0c80", 128)
    c.branch(4, "stock")
    qualified(c, "stock")
    c.imm("b9fc", 132)
    c.branch(6, "loop")
    c.branch(0, "done")
    c.label("stock")
    c.imm("b9fc", 128)
    c.branch(6, "loop")
    c.label("done")
    c.imm("4ef9", 0x4001E484)
    c.label("loop")
    c.imm("4ef9", 0x4001E418)
    return c.finish(COUNT)


def cursor(*, navigation_fixes=False):
    c = Code()
    c.emit("4feffff0 48d7041c 246f0014 7400 342f001a 7600 7000 302a00a2")
    c.imm("0c80", 128)
    c.branch(4, "old_bank")
    c.emit("7601")
    c.label("old_bank")
    if navigation_fixes:
        c.imm("0c82", 1023)
        c.branch(3, "valid_slot")
        c.emit("7400")
        c.label("valid_slot")
        # A zero bank cell is the extended A/BUF presentation. Preserve an
        # existing alias through native rebuild/subscription callbacks. A
        # nonzero ordinary backing row must retain its bank and row.
        c.emit("7000 302a00a2 4a80")
        c.branch(6, "ordinary_cursor")
        for i in range(4):
            c.imm("2239", n.STATE + 32 + i * 4)
            c.emit("b481")
            c.branch(7, "alias_cursor")
        c.branch(0, "ordinary_cursor")
        c.label("alias_cursor")
        c.emit("2f02 2f0a")
        n.call(c, INVERSE, 8)
        c.branch(0, "mapped_rank")
        c.label("ordinary_cursor")
        c.emit("354200a2 2002")
        c.imm("0280", 127)
        c.imm("0c82", 128)
        c.branch(4, "ordinary_rank")
        c.emit("2800")
        qualified(c, "ordinary_unshifted")
        c.imm("0684", 4)
        c.label("ordinary_unshifted")
        c.emit("2004")
        c.label("ordinary_rank")
        c.label("mapped_rank")
    else:
        c.emit("2f02 2f0a")
        n.call(c, INVERSE, 8)
    c.emit("2800 7000 302a00a2")
    c.imm("0c80", 128)
    c.branch(4, "new_b")
    c.emit("7001")
    c.branch(0, "compare_banks")
    c.label("new_b")
    c.emit("7000")
    c.label("compare_banks")
    c.emit("b083")
    c.branch(7, "cursor_ready")
    c.emit("2f0a")
    n.call(c, BUILD_STOCK, 4)
    if not navigation_fixes:
        c.emit("2f02 2f0a")
        n.call(c, INVERSE, 8)
        c.emit("2800")
    c.label("cursor_ready")
    c.emit("2004 7200 2f01 2f00 41ea004c 2f08 2050 20680020 4e90 4fef000c")
    c.emit("2f0a")
    n.call(c, 0x4011AE46, 4)
    c.emit("4cd7041c 4fef0010 4e75")
    return c.finish(CURSOR)


def initial(*, navigation_fixes=False):
    c = Code()
    # BUILD has already normalized the current bank cell for BUF aliases.
    # The constructor's original slot still identifies the assigned sample.
    if navigation_fixes:
        # Canonicalize an assigned BUF only when opening the view. Ordinary
        # rebuilds and cursor callbacks retain their current bank/row.
        c.emit("4feffff0 48d7000c 7400 342a00a2 7000 302a00a0 2f00 2f0a")
        n.call(c, INVERSE, 8)
        c.emit("2600 7000 302a00a2")
        c.imm("0280", 0x380)
        c.emit("2200 2002")
        c.imm("0280", 0x380)
        c.emit("b081")
        c.branch(7, "ready")
        c.emit("2f0a")
        n.call(c, BUILD_STOCK, 4)
        c.label("ready")
        c.emit("2003 4cd7000c 4fef0010")
    else:
        c.emit("7000 302a00a0 2f00 2f0a")
        n.call(c, INVERSE, 8)
    c.imm("4ef9", 0x4001E5D0)
    return c.finish(INITIAL)


def resolve():
    c = Code()
    c.emit("2f00 2202")
    c.imm("0281", 0xFFFF)
    c.emit("2f01")
    n.call(c, FORWARD, 8)
    c.emit("2400")
    c.imm("4ef9", 0x4001E1E6)
    return c.finish(RESOLVE)


def format_row():
    c = Code()
    c.emit("4fefffe0 48d7041c 2408 206f0024 2450 2452 7000 302a00a2")
    c.imm("0c80", 128)
    c.branch(4, "stock")
    qualified(c, "stock")
    c.emit("2f2f0028")
    n.call(c, 0x401154E0, 4)
    c.imm("0c80", 4)
    c.branch(4, "stock")
    c.emit("2200 7003 9081 2600 d080 d080")
    c.imm("41f9", n.STATE + 32)
    c.emit("d1c0 2010 d080 d080 d080 d080")
    c.imm("43f9", 0x405B1368)
    c.emit("d3c0 20290008 4a80")
    c.branch(7, "empty")
    c.emit("2003 d080 d080 d080 d080 d080")
    c.imm("0680", NAMES + 16)
    c.branch(0, "construct")
    c.label("empty")
    c.emit("2003 d080 d080 d080 d080 d080")
    c.imm("0680", NAMES)
    c.label("construct")
    c.emit("41ef0018 2f08 2f00 2f02")
    n.call(c, 0x401E7A64, 12)
    c.emit("2002 4cd7041c 4fef0020 4e75")
    c.label("stock")
    c.emit("2042 4cd7041c 4fef0020")
    c.imm("4ef9", FORMAT_STOCK)
    return c.finish(FORMAT)


def normal_row():
    c = Code()
    c.emit("2052 7200 322800a2")
    c.imm("0c81", 128)
    c.branch(4, "done")
    c.emit("2f00")
    qualified(c, "unchanged")
    c.emit("201f")
    c.imm("0680", -4)
    c.branch(0, "restore")
    c.label("unchanged")
    c.emit("201f")
    c.label("restore")
    c.emit("7200 322800a2")
    c.label("done")
    c.imm("4ef9", 0x4001DFF0)
    return c.finish(NORMAL)


def navigate(*, navigation_fixes=False):
    """(view, signed row delta): use the stock bound sample-change callback."""
    c = Code()
    c.emit("4fefffe0 48d70c1c 246f0024 242f0028")
    qualified(c, "stock")
    if navigation_fixes:
        c.emit("7000 302a00a2")
        c.imm("0c80", 128)
        c.branch(4, "stock")
    c.emit("202a00c4 4a80")
    c.branch(7, "stock")
    # Query the list's native selected-slot helper. Its C++ context and menu
    # rank are already authoritative; no duplicate project parameter lookup.
    c.emit("2f0a")
    n.call(c, 0x4001E17A, 4)
    c.imm("0280", 0xFFFF)
    c.emit("2600")
    c.imm("0c83", 128)
    c.branch(5, "supported")
    for i in range(4):
        c.imm("2239", n.STATE + 32 + i * 4)
        c.emit("b681")
        c.branch(7, "supported")
    c.branch(0, "stock")
    c.label("supported")
    if navigation_fixes:
        # The list owns the presentation rank, including an ordinary A row
        # which happens to alias a BUF slot. Never reconstruct it from PCM ID.
        c.emit("41ea004c 2f08 2050 20680024 4e90 588f")
    else:
        c.emit("2f03 2f0a")
        n.call(c, INVERSE, 8)
    c.emit("d082")
    c.imm("0c80", 0)
    c.branch(12, "nonnegative")
    c.emit("7000")
    c.label("nonnegative")
    c.imm("0c80", 131)
    c.branch(15, "bounded")
    c.imm("203c", 131)
    c.label("bounded")
    if navigation_fixes:
        c.emit("2600")
    c.emit("2f00 7200 2f01")
    n.call(c, FORWARD, 8)
    c.emit("2800 2f04 41ea00b8 2f08 206a00c4 4e90 508f")
    # The bound absolute callback updates the parameter; unlike the stock
    # relative callback, it does not move this list's cursor.
    if navigation_fixes:
        c.emit("354400a2")
        c.imm("0c83", 4)
        c.branch(4, "rank_ready")
        c.emit("7000 354000a2")
        c.label("rank_ready")
        c.emit("2f03 2f0a")
        n.call(c, MOVE_RANK, 8)
    else:
        c.emit("2f04 2f0a")
        n.call(c, CURSOR, 8)
    c.emit("7001")
    c.branch(0, "done")
    c.label("stock")
    c.emit("7000")
    c.label("done")
    c.emit("4cd70c1c 4fef0020 4e75")
    return c.finish(NAVIGATE)


def key():
    c = Code()
    c.emit("4fefffe0 48d70c1c 246f0024 266f0028 202b000c")
    for code in (11, 14):
        c.imm("0c80", code)
        c.branch(7, "arrow")
    for code in (13, 15):
        c.imm("0c80", code)
        c.branch(7, "bank")
    c.branch(0, "stock")
    c.label("bank")
    c.emit("2400")
    c.imm("4879", 17)
    n.call(c, 0x4011DE70, 4)
    c.emit("4a80")
    c.branch(6, "stock")
    c.emit("222b0010")
    c.imm("0281", 1)
    c.emit("4a81")
    c.branch(7, "stock")
    c.emit("2f02 2f0a")
    n.call(c, BANK, 8)
    c.emit("4a80")
    c.branch(7, "stock")
    c.branch(0, "consumed")
    c.label("arrow")
    c.emit("2400")
    c.imm("4879", 17)
    n.call(c, 0x4011DE70, 4)
    c.emit("4a80")
    c.branch(6, "stock")
    c.emit("202b0010")
    c.imm("0280", 9)
    c.emit("4a80")
    c.branch(7, "consumed")
    c.emit("7001")
    c.imm("0c82", 14)
    c.branch(7, "move")
    c.emit("70ff")
    c.label("move")
    c.emit("2f00 2f0a")
    n.call(c, NAVIGATE, 8)
    c.emit("4a80")
    c.branch(7, "stock")
    c.label("consumed")
    c.emit("7001 4cd70c1c 4fef0020 4e75")
    c.label("stock")
    c.emit("4cd70c1c 4fef0020")
    c.imm("4ef9", KEY_STOCK)
    return c.finish(KEY)


def rotation():
    c = Code()
    c.emit("4fefffe0 48d70c1c 246f0024 266f0028")
    c.imm("d5fc", -4)  # IEncoder receiver is the secondary base at view+4.
    c.emit("2012")
    c.imm("0c80", 0x401EE4B8)
    c.branch(6, "stock")
    c.emit("7000 302a00a2")
    c.emit("4a80")
    c.branch(6, "stock")  # Only A00 and normalized BUF rows belong to this handler.
    c.imm("2039", VIEW_ENABLED)
    c.imm("0c80", 1)
    c.branch(6, "stock")
    c.imm("4879", 3)
    c.emit("2f0b")
    n.call(c, 0x40111732, 8)
    c.imm("0280", 255)
    c.emit("4a80")
    c.branch(7, "stock")
    c.imm("4879", 0x44D2E61C)
    c.emit("2f0b")
    c.imm("4879", SCALER)
    n.call(c, 0x40111B62, 12)
    c.emit("4a80")
    c.branch(12, "scaled")
    c.imm("0680", 255)
    c.label("scaled")
    c.emit("e080 4a80")
    c.branch(7, "consumed")
    c.emit("2f00 2f0a")
    n.call(c, NAVIGATE, 8)
    c.branch(0, "done")
    c.label("consumed")
    c.emit("7001")
    c.branch(0, "done")
    c.label("stock")
    c.emit("7000")
    c.label("done")
    c.emit("4cd70c1c 4fef0020 4e75")
    return c.finish(ROTATE)


def bank(*, navigation_fixes=False):
    """A logical BUF belongs before A00, irrespective of its backing bank."""
    c = Code()
    c.emit("4fefffe0 48d70c1c 246f0024 242f0028")
    qualified(c, "stock")
    if navigation_fixes:
        c.emit("7000 302a00a2 4a80")
        c.branch(6, "stock")
    c.emit("202a00c4 4a80")
    c.branch(7, "stock")
    c.emit("2f0a")
    n.call(c, 0x4001E17A, 4)
    c.imm("0280", 0xFFFF)
    for i in range(4):
        c.imm("2239", n.STATE + 32 + i * 4)
        c.emit("b081")
        c.branch(7, "buffer")
    c.branch(0, "stock")
    c.label("buffer")
    c.imm("0c82", 13)
    c.branch(7, "consumed")
    c.imm("4879", 128)
    c.emit("41ea00b8 2f08 206a00c4 4e90 508f")
    c.imm("4879", 128)
    c.emit("2f0a")
    n.call(c, CURSOR, 8)
    c.emit("2f0a")
    n.call(c, BUILD, 4)
    c.label("consumed")
    c.emit("7001")
    c.branch(0, "done")
    c.label("stock")
    c.emit("7000")
    c.label("done")
    c.emit("4cd70c1c 4fef0020 4e75")
    return c.finish(BANK)


def move_rank():
    c = Code()
    c.emit("4feffff0 48d70404 246f0014 242f0018")
    c.emit("7000 2f00 2f02 41ea004c 2f08 2050 20680020 4e90 4fef000c")
    c.emit("2f0a")
    n.call(c, 0x4011AE46, 4)
    c.emit("4cd70404 4fef0010 4e75")
    return c.finish(MOVE_RANK)


def payload(stock, *, navigation_fixes=False):
    import hashlib

    require(hashlib.sha256(stock).hexdigest() == STOCK_SHA, "BUF selector needs OS1.16")
    for pc, (expected, _) in HOOKS.items():
        raw = bytes.fromhex(expected)
        require(
            stock[pc - MAIN_BASE : pc - MAIN_BASE + len(raw)] == raw,
            f"BUF selector hook drift {pc:#x}",
        )
    result = {
        INVERSE: inverse(),
        FORWARD: forward(),
        BUILD: build_rows(navigation_fixes=navigation_fixes),
        COUNT: count(),
        CURSOR: cursor(navigation_fixes=navigation_fixes),
        INITIAL: initial(navigation_fixes=navigation_fixes),
        RESOLVE: resolve(),
        FORMAT: format_row(),
        NORMAL: normal_row(),
        KEY: key(),
        NAVIGATE: navigate(navigation_fixes=navigation_fixes),
        ROTATE: rotation(),
        BANK: bank(navigation_fixes=navigation_fixes),
    }
    if navigation_fixes:
        result[MOVE_RANK] = move_rank()
    for pc, dest in (
        (0x4001E31A, BUILD_STOCK),
        (0x4001DFBE, FORMAT_STOCK),
        (0x4001EBC8, KEY_STOCK),
    ):
        raw = bytes.fromhex(HOOKS[pc][0])
        result[dest] = raw + bytes.fromhex("4ef9") + struct.pack(">I", pc + len(raw))
    for i in range(4):
        result[NAMES + i * 32] = f"BUF {i + 1} EMPTY".encode().ljust(
            16, b"\0"
        ) + f"BUF {i + 1} READY".encode().ljust(16, b"\0")
    items = sorted(result.items())
    require(
        all(a + len(b) <= c for (a, b), (c, _) in zip(items, items[1:], strict=False)),
        "BUF selector payload overlap",
    )
    require(max(a + len(b) for a, b in items) <= END, "BUF selector arena overflow")
    return result
