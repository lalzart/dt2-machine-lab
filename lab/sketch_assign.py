"""Opt-in OS1.16 post-publication prompt; no recorder or allocator replacement.

Stock AssignPrompt pixels, separate base View lifetime and explicit live-BUF
assignment. All state is volatile. Synthetic addresses relocate only when enabled.
"""

import struct

from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as jobs
from lab import recorder_worker_code as w
from lab import sketch as s
from lab import sketch_copy as clip
from lab import sketch_managed as managed
from lab import sketchbook_preview as preview
from lab import sketchbook_ui as book
from lab.emit import Code
from lab.flex_native_save import push_dialog

BASE, SIZE = 0x11400000, 0x4000
STATE = BASE
PENDING, VIEW, PRESSED, CLOSING, BUF, SLOT, EPOCH, KIT, PROJECT, POOL = range(0, 40, 4)
RESULT, TARGET, SHOWN, ASSIGNED, SKIPPED = range(40, 60, 4)
KEYS = BASE + 0x100  # captured cache tuple followed by public pool tuple
QUEUE, CHECK, SERVICE, OPEN, KEY, ASSIGN, ROUTE, POLL = (
    BASE + x for x in (0x400, 0x800, 0xC00, 0x1000, 0x1400, 0x1800, 0x1C00, 0x1E00)
)
DTOR, DISPOSE, PUSH, TOP, CLOSE, CONSUME = (
    BASE + x for x in (0x2000, 0x2100, 0x2200, 0x2300, 0x2400, 0x2500)
)
VTABLE, SHARED, SECONDARY, NAME = (
    BASE + 0x3008,
    BASE + 0x3100,
    BASE + 0x3158,
    BASE + 0x3200,
)
STOCK_DRAW = 0x40018BE6
TOP_FROM = BASE + 0x2700
HELP_BUBBLE_VTABLE = 0x40216B04  # passive stock overlay above the normal main page
RESIDENT_VTABLES = (
    HELP_BUBBLE_VTABLE,
    0x401F64D0,  # KeyboardView
    0x401F8C6C,  # PatternGridView
    0x401F6254,  # TempoLedView
    0x401ED53C,  # SamplerLedView
    0x401ED888,  # ParameterPageView
    0x401F9BF4,  # TransportView
)
OK, NO, STALE, BUSY, MIDI, FAILED = range(1, 7)


def load(c, field, reg=0):
    c.imm(f"{0x2039 | reg << 9:04x}", STATE + field)


def store(c, field, reg=0):
    c.imm(f"{0x23C0 | reg:04x}", STATE + field)


def value(c, field, val):
    c.imm("203c", val)
    store(c, field)


def inc(c, field):
    load(c, field)
    c.emit("5280")
    store(c, field)


def context():
    return (
        (n.STATE, EPOCH),
        (0x80004704, KIT),
        (0x44F370A0, PROJECT),
        (w.STATE + 68, POOL),
    )


def queue():
    """Called only by successful publication, before its mutation lease clears."""
    c = Code()
    c.emit("4feffff0 48d70c0c")
    load(c, VIEW)
    c.emit("4a80")
    c.branch(6, "done")
    value(c, PENDING, 0)
    nb.load(c, nb.DEST, 2)
    c.emit("2002 5380")
    c.imm("0c80", 3)
    c.branch(2, "done")
    store(c, BUF, 2)
    c.emit("e588")
    c.imm("43f9", w.STATE + 96)
    c.emit("d3c0 2411 2002")
    store(c, SLOT)
    load(c, BUF, 1)
    c.imm("0681", 1019)
    c.emit("b081")
    c.branch(6, "done")
    for at, field in context():
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(7, "done")
        store(c, field)
    # Capture both native associations. Never retain a generation pointer.
    c.emit("2002 e588 e588")  # slot * 16
    c.imm("45f9", 0x405B1368)
    c.emit("d5c0")
    load(c, POOL, 1)
    c.emit("2641 d7c0")
    c.imm("43f9", KEYS)
    for source in ("a", "b"):
        for off in range(0, 16, 4):
            c.emit(f"202{source}{off:04x} 22c0")
    value(c, RESULT, 0)
    value(c, TARGET, 0)
    value(c, PENDING, 1)
    c.label("done")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(QUEUE)


def check():
    c = Code()
    c.emit("4feffff0 48d70c0c")
    for at, field in context():
        c.imm("2039", at)
        load(c, field, 1)
        c.emit("4a80")
        c.branch(7, "bad")
        c.emit("b081")
        c.branch(6, "bad")
    load(c, BUF)
    c.emit("5380")
    c.imm("0c80", 3)
    c.branch(2, "bad")
    c.imm("0680", 1020)
    load(c, SLOT, 1)
    c.emit("b081")
    c.branch(6, "bad")
    c.emit("e588 e588")
    c.imm("45f9", 0x405B1368)
    c.emit("d5c0")
    load(c, POOL, 1)
    c.emit("2641 d7c0")
    c.imm("43f9", KEYS)
    for source in ("a", "b"):
        for off in range(0, 16, 4):
            c.emit(f"202{source}{off:04x} 2219 b081")
            c.branch(6, "bad")
    c.emit("2012 4a80")
    c.branch(7, "bad")
    c.emit("2013 4a80")
    c.branch(7, "bad")
    c.emit("7001")
    c.branch(0, "done")
    c.label("bad")
    c.emit("7000")
    c.label("done")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(CHECK)


def top():
    c = Code()
    n.call(c, 0x40198948)
    c.emit("4a80")
    c.branch(7, "done")
    c.imm("0680", 0x40)
    c.emit("2f00")
    n.call(c, TOP_FROM, 4)
    c.label("done")
    c.emit("4e75")
    return c.finish(TOP)


def top_from():
    """Look through stock main-screen layers; stop at Sketch or any other dialog.

    The native controller retains the keyboard/grid/page/LED layers above
    MainScreenView even on ordinary SRC. These authenticated classes are not
    modal prompts. A foreign view anywhere above MainScreenView stops the walk.
    """
    c = Code()
    c.emit("4feffff4 48d70404 206f0010 45e80014 226a0004 7420")
    c.label("scan")
    c.emit("2009 220a b081")
    c.branch(7, "empty")
    c.emit("20290008 4a80")
    c.branch(7, "empty")
    c.emit("2040 2210")
    for table in RESIDENT_VTABLES:
        c.imm("0c81", table)
        c.branch(7, "resident")
    c.branch(0, "done")
    c.label("resident")
    c.emit("22690004 5382")
    c.branch(6, "scan")
    c.label("empty")
    c.emit("7000")
    c.label("done")
    c.emit("4cd70404 4fef000c 4e75")
    return c.finish(TOP_FROM)


def close():
    c = Code()
    load(c, CLOSING)
    c.emit("4a80")
    c.branch(6, "done")
    value(c, CLOSING, 1)
    value(c, PENDING, 0)
    value(c, PRESSED, 0)
    load(c, VIEW)
    c.emit("4a80")
    c.branch(7, "done")
    c.emit("2f00")
    n.call(c, 0x4011AEEA, 4)
    c.label("done")
    c.emit("4e75")
    return c.finish(CLOSE)


def service():
    c = Code()
    c.emit("4feffff0 48d70c0c")
    load(c, VIEW)
    c.emit("4a80")
    c.branch(6, "active")
    load(c, PENDING)
    c.emit("4a80")
    c.branch(7, "done")
    c.label("active")
    n.call(c, CHECK)
    c.emit("4a80")
    c.branch(7, "stale")
    nb.load(c, nb.PHASE)
    c.emit("4a80")
    c.branch(6, "stale")  # Never present a previous request during a new take.
    load(c, VIEW)
    c.emit("4a80")
    c.branch(6, "done")
    for at in (
        jobs.STOCK_BUSY,
        jobs.STATE + 56,
        w.STATE + 12,
        managed.STATE + managed.BORROWED,
        s.STATE + s.OWN,
        s.STATE + s.FUNC_OWN,
        clip.STATE + clip.OWN,
        book.STATE + book.BACK_KEY,
        book.STATE + book.NAME_KEY,
    ):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "done")
    # Let pre-existing note/button releases reach their original owners before
    # installing a modal that consumes keys. Avoid a stuck audition/held note.
    c.emit("7401")
    c.label("released_keys")
    c.emit("2f02")
    n.call(c, 0x4011DE70, 4)
    c.imm("0280", 255)
    c.branch(6, "done")
    c.emit("2002 5280 2400")
    c.imm("0c82", 51)
    c.branch(6, "released_keys")
    n.call(c, TOP)
    c.emit("4a80")
    c.branch(7, "done")
    c.emit("2440")
    s.load(c, s.VIEW, 1)
    c.emit("b081")
    c.branch(6, "main")
    book.load(c, book.MODE)
    c.emit("4a80")
    c.branch(6, "done")  # Sketchbook's menus retain their own input ownership.
    c.branch(0, "open")
    c.label("main")
    c.emit("2052 20280008")
    c.imm("0c80", s.MAIN_SITE)
    c.branch(6, "done")
    c.label("open")
    n.call(c, OPEN)
    c.branch(0, "done")
    c.label("stale")
    value(c, RESULT, STALE)
    n.call(c, CLOSE)
    c.label("done")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(SERVICE)


def open_view():
    c = Code()
    c.emit("4feffff0 48d70c0c")
    c.imm("4879", 0x4C + 16)
    n.call(c, 0x4011E8F0, 4)
    c.emit("4a80")
    c.branch(7, "failed")
    c.emit("2640")
    c.imm("203c", SHARED)
    c.emit("2680 7001 27400004 27400008 41eb0010 2748000c")
    c.imm("4879", NAME)
    c.emit("2f08")
    n.call(c, 0x4011AD8E, 8)
    c.emit("45eb0010")
    c.imm("203c", VTABLE)
    c.emit("2480")
    c.imm("203c", SECONDARY)
    c.emit("25400004")
    c.emit("7000 2f00 2f0a")
    n.call(c, 0x4011ACDC, 8)
    c.emit("7006 2f00 2f0a")
    n.call(c, 0x4011B23A, 8)
    c.emit("200a")
    store(c, VIEW)
    value(c, PRESSED, 0)
    value(c, CLOSING, 0)
    value(c, PENDING, 0)
    c.emit("2f0b")
    n.call(c, PUSH, 4)
    # A rejected push releases the reference and runs our destructor.
    load(c, VIEW)
    c.emit("4a80")
    c.branch(7, "failed")
    inc(c, SHOWN)
    c.branch(0, "done")
    c.label("failed")
    value(c, PENDING, 0)
    value(c, RESULT, FAILED)
    c.label("done")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(OPEN)


def assign():
    """D0 result: 1 assigned, 3 stale, 4 busy, 5 unsupported track, 6 failed."""
    c = Code()
    c.emit("4feffff0 48d70c0c 242f0014")
    c.imm("0c82", 15)
    c.branch(2, "failed")
    n.call(c, CHECK)
    c.emit("4a80")
    c.branch(7, "stale")
    for at in (jobs.STOCK_BUSY, jobs.STATE + 56, w.STATE + 12, nb.STATE + nb.PHASE):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "busy")
    load(c, KIT)
    c.emit("2440 2002")
    c.imm("223c", 0x450)
    c.emit("4c010800 d5c0 7000 102a00d6")
    c.imm("0c80", 4)
    c.branch(3, "supported")
    c.imm("0c80", 6)
    c.branch(6, "midi")
    c.label("supported")
    n.call(c, 0x401988A2)
    c.emit("2f02")
    c.imm("4879", 0xCD)
    c.emit("2f00")
    n.call(c, 0x40045582, 12)
    c.emit("4a80")
    c.branch(7, "failed")
    c.emit("2440")
    for arg in (1, 1, 1, -1):
        c.imm("4879", arg)
    load(c, SLOT)
    c.emit("2f00")
    c.imm("4879", 0xCD)
    c.emit("2f0a")
    n.call(c, 0x4003B570, 28)
    load(c, SLOT, 1)
    c.emit("b081")
    c.branch(6, "failed")
    c.emit("2002 5280")
    store(c, TARGET)
    inc(c, ASSIGNED)
    c.emit("7001")
    c.branch(0, "done")
    for label, val in (
        ("stale", STALE),
        ("busy", BUSY),
        ("midi", MIDI),
        ("failed", FAILED),
    ):
        c.label(label)
        c.imm("203c", val)
        c.branch(0, "done")
    c.label("done")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(ASSIGN)


def key():
    c = Code()
    c.emit("4feffff0 48d70c0c 246f0018 242a000c 262a0010")
    load(c, CLOSING)
    c.emit("4a80")
    c.branch(6, "done")
    c.imm("0c82", 12)
    c.branch(7, "choice")
    c.emit("2002")
    c.imm("0680", -25)
    c.imm("0c80", 15)
    c.branch(2, "done")
    c.label("choice")
    c.emit("2003")
    c.imm("0280", 9)  # native initial (1) or fast second press (5), never repeat/hold
    c.imm("0c80", 1)
    c.branch(6, "release")
    load(c, PRESSED)
    c.emit("4a80")
    c.branch(6, "done")
    store(c, PRESSED, 2)
    c.branch(0, "done")
    c.label("release")
    c.emit("2003")
    c.imm("0280", 0x11)
    c.imm("0c80", 0x10)
    c.branch(6, "done")
    load(c, PRESSED)
    c.emit("b082")
    c.branch(6, "done")
    value(c, PRESSED, 0)
    c.imm("0c82", 12)
    c.branch(7, "skip")
    c.emit("2002")
    c.imm("0680", -25)
    c.emit("2f00")
    n.call(c, ASSIGN, 4)
    store(c, RESULT)
    c.imm("0c80", OK)
    c.branch(7, "close")
    c.imm("0c80", STALE)
    c.branch(6, "done")
    c.branch(0, "close")
    c.label("skip")
    inc(c, SKIPPED)
    value(c, RESULT, NO)
    c.label("close")
    n.call(c, CLOSE)
    c.label("done")
    c.emit("7001 4cd70c0c 4fef0010 4e75")
    return c.finish(KEY)


def route():
    c = Code()
    c.emit("4feffff0 48d70c0c 246f0014 266f0018")
    load(c, VIEW, 2)
    c.emit("4a82")
    c.branch(7, "stock")
    c.emit("2f0a")
    n.call(c, TOP_FROM, 4)
    c.emit("b082")
    c.branch(6, "stock")
    # Consume before registered track/performance listeners, including release.
    c.emit("2f0b 2f02")
    n.call(c, KEY, 8)
    c.emit("4cd70c0c 4fef0010 4e75")
    c.label("stock")
    c.emit("4cd70c0c 4fef0010")
    c.imm("4ef9", preview.CANCEL_KEY)
    return c.finish(ROUTE)


def payload(main):
    c = Code()
    c.emit("4feffff0 48d70303")
    n.call(c, SERVICE)
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", managed.POLL)
    poll = c.finish(POLL)
    c = Code()
    for field in (VIEW, PENDING, PRESSED, CLOSING):
        value(c, field, 0)
    c.imm("4ef9", 0x4011AFE4)
    dtor = c.finish(DTOR)
    c = Code()
    c.emit("206f0004 2f28000c")
    n.call(c, DTOR, 4)
    c.emit("4e75")
    dispose = c.finish(DISPOSE)
    table = bytearray(main[0x4021DB18 - 0x40000400 : 0x4021DB64 - 0x40000400])
    for off, target in ((0, DTOR), (8, KEY), (16, STOCK_DRAW)):
        struct.pack_into(">I", table, 8 + off, target)
    table += struct.pack(">II", CONSUME, 0x4011ACFC)
    secondary = bytearray(main[0x4021DB64 - 0x40000400 : 0x4021DB78 - 0x40000400])
    struct.pack_into(">I", secondary, 16, CONSUME)
    code = {
        QUEUE: queue(),
        CHECK: check(),
        TOP: top(),
        TOP_FROM: top_from(),
        SERVICE: service(),
        OPEN: open_view(),
        ASSIGN: assign(),
        KEY: key(),
        ROUTE: route(),
        POLL: poll,
        DTOR: dtor,
        DISPOSE: dispose,
        PUSH: push_dialog(PUSH),
        CLOSE: close(),
        CONSUME: bytes.fromhex("70014e75"),
    }
    pointers = {
        VTABLE - 8: bytes(table),
        SHARED: struct.pack(">5I", 0, 0, DISPOSE, 0x4011E8FC, 0),
        SECONDARY - 8: bytes(secondary),
    }
    return code, pointers, {NAME: b"SketchAssignPrompt\0"}
