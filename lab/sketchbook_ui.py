"""Sketch SONG-page take list and native naming dialog for OS1.16.

No Samples view, filesystem chooser or base View method is replaced.
"""

import struct

from lab import flex_native_save as f
from lab import sketch as s
from lab import sketchbook_preview as p
from lab import sketchbook_save as b
from lab.dt2_116 import DOWN, LEFT, NO, RIGHT, UP, YES
from lab.emit import Code
from lab.project import require

BASE = p.BASE
STATE = BASE + 0x100
MODE, ROW, VIEW, LAST, BACK_KEY, NAME_KEY = 0, 4, 8, 12, 16, 20
LINE = STATE + 0x40
DRAW, KEY, ROTATE = BASE + 0x400, BASE + 0xC00, BASE + 0x1000
CALLBACK, OPEN_NAME, MESSAGE, PUSH, MANAGER, POLL = [
    BASE + x for x in (0x1200, 0x1400, 0x1600, 0x1700, 0x1800, 0x1900)
]
TARGET, COUNT = BASE + 0x1A00, BASE + 0x1C00
STRINGS = BASE + 0x2000
LABELS = {
    "book": "SKETCHBOOK %u/%u",
    "hint": "YES:SAVE  >:PLAY",
    "buf_row": "BUF %u  %s",
    "freeze_row": "FREEZE H%03u",
    "ready": "READY",
    "empty": "EMPTY",
    "title": "SAVE TO SKETCHBOOK",
    "initial": "Sketch",
    "missing": "EMPTY OR STALE TAKE",
    "busy": "BUSY / CANNOT SAVE",
    "saved": "SAVED TO SKETCHBOOK",
    "failed": "SAVE FAILED",
    "preview_failed": "PREVIEW FAILED",
    "saving": "SAVING TO SKETCHBOOK",
    "loading": "LOADING PREVIEW",
}


def texts():
    at = STRINGS
    table = {}
    parts = {}
    for key, value in LABELS.items():
        raw = value.encode() + b"\0"
        table[key] = at
        parts[at] = raw
        at += len(raw)
    require(at <= p.NAME, "Sketchbook UI text overlap")
    return table, parts


def load(c, off, reg=0):
    c.imm(f"{0x2039 | reg << 9:04x}", STATE + off)


def store(c, off, reg=0):
    c.imm(f"{0x23C0 | reg:04x}", STATE + off)


def value(c, off, v):
    c.imm("203c", v)
    store(c, off)


def count():
    c = Code()
    c.emit("41f9")
    c.data.extend(struct.pack(">I", b.n.SNAP))
    c.emit("7004")
    c.label("scan")
    c.emit("2f00 2010")
    c.imm("0c80", 1)
    c.branch(6, "next")
    c.emit("20280008")
    c.imm("2239", b.n.STATE)
    c.emit("b081")
    c.branch(6, "next")
    c.emit("201f 5280")
    c.branch(0, "advance")
    c.label("next")
    c.emit("201f")
    c.label("advance")
    c.emit("41e80040")
    c.imm("b1fc", b.n.SNAP + 512)
    c.branch(6, "scan")
    c.emit("4e75")
    return c.finish(COUNT)


def target():
    c = Code()
    c.emit("4feffff0 48d70c0c 242f0014 76ff")
    c.imm("0c82", 4)
    c.branch(4, "freeze")
    c.emit("2002")
    c.imm("0680", 1020)
    c.emit("2600")
    c.branch(0, "slot")
    c.label("freeze")
    c.imm("0682", -4)
    c.imm("45f9", b.n.SNAP)
    c.label("scan")
    c.emit("2012")
    c.imm("0c80", 1)
    c.branch(6, "next")
    c.emit("202a0008")
    c.imm("2239", b.n.STATE)
    c.emit("b081")
    c.branch(6, "next")
    c.emit("4a82")
    c.branch(7, "found")
    c.imm("0682", -1)
    c.label("next")
    c.emit("45ea0040")
    c.imm("b5fc", b.n.SNAP + 512)
    c.branch(6, "scan")
    c.branch(0, "bad")
    c.label("found")
    c.emit("262a0024")
    c.label("slot")
    c.emit("2003 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0 2410 2f02")
    b.call(c, b.n.LOOKUP, 4)
    c.imm("0c80", b.n.GEN)
    c.branch(5, "bad")
    c.imm("0c80", b.n.GEN + 512)
    c.branch(4, "bad")
    c.emit("2440")
    c.imm("223c", b.n.GEN)
    c.emit("9081 d080")
    c.imm("47f9", b.META)
    c.emit("d7c0 2013")
    c.imm("0c80", 1)
    c.branch(6, "bad")
    c.emit("202b0004 b082")
    c.branch(6, "bad")
    for off, actual in ((4, 16), (8, 20), (12, 24), (120, 28), (16, 8)):
        c.emit(f"202b{off:04x} 222a{actual:04x} b081")
        c.branch(6, "bad")
    c.emit("2042 200b")
    c.branch(0, "return")
    c.label("bad")
    c.emit("7000")
    c.label("return")
    c.emit("2203 4cd70c0c 4fef0010 4e75")
    return c.finish(TARGET)


def draw(t):
    c = Code()
    c.emit("4fefffd8 48d73cfc 246f002c 266f0030 200a")
    store(c, VIEW)
    c.emit("2f0b")
    b.call(c, s.CLEAR, 4)
    c.emit("4a80")
    c.branch(7, "done")

    def text(y, pointer=None):
        c.imm("4879", LINE if pointer is None else pointer)
        for arg in (0x20, y, 2, s.FONT):
            c.imm("4879", arg)
        c.emit("2f0b")
        b.call(c, s.TEXT, 24)

    def fmt(key, args):
        for a in reversed(args):
            if isinstance(a, int):
                c.imm("4879", a)
            else:
                c.emit(a)
        c.imm("4879", t[key])
        c.imm("4879", LINE)
        b.call(c, s.PRINT, 4 * (len(args) + 2))

    b.call(c, COUNT)
    c.emit("2400")
    load(c, ROW)
    c.emit("5280")
    fmt("book", ["2f00", "2f02"])
    text(56)

    def bar(low, high):
        for arg in (-1, high, 127, low, 0):
            c.imm("4879", arg)
        c.emit("2f0b")
        b.call(c, 0x40112ECE, 24)

    bar(54, 63)
    load(c, ROW)
    c.imm("0280", 0xFFFFFFFC)
    c.emit("2400")
    for i, y in enumerate((44, 34, 24, 14)):
        c.emit("2f02")
        b.call(c, TARGET, 4)
        c.emit("2600 2a01")
        c.imm("0c85", -1)
        c.branch(7, f"next{i}")
        c.imm("0c82", 4)
        c.branch(4, f"freeze{i}")
        c.emit("4a83")
        c.branch(7, f"empty{i}")
        c.imm("263c", t["ready"])
        c.branch(0, f"buf{i}")
        c.label(f"empty{i}")
        c.imm("263c", t["empty"])
        c.label(f"buf{i}")
        c.emit("2002 5280 2c00")
        fmt("buf_row", ["2f06", "2f03"])
        c.branch(0, f"paint{i}")
        c.label(f"freeze{i}")
        c.emit("2005")
        c.imm("0680", -896)
        c.emit("2c00")
        fmt("freeze_row", ["2f06"])
        c.label(f"paint{i}")
        text(y)
        load(c, ROW)
        c.emit("b082")
        c.branch(6, f"next{i}")
        bar(y - 2, y + 6)
        c.label(f"next{i}")
        c.imm("0682", 1)
    b.load(c, b.JOB)
    c.imm("0c80", 1)
    c.branch(7, "pending")
    c.imm("0c80", 2)
    c.branch(7, "pending")
    text(4, t["hint"])
    c.branch(0, "done")
    c.label("pending")
    b.load(c, b.KIND)
    c.imm("0c80", 2)
    c.branch(7, "loading")
    text(4, t["saving"])
    c.branch(0, "done")
    c.label("loading")
    text(4, t["loading"])
    c.label("done")
    c.emit("4cd73cfc 4fef0028 4e75")
    return c.finish(DRAW)


def key(t):
    """Handle take-list keys only when the actual Sketch view receives them."""
    c = Code()
    c.emit("4feffff0 48d70c0c 246f0014 266f0018 242b000c")
    s.load(c, s.VIEW)
    c.emit("220a b081")
    c.branch(6, "no")
    s.load(c, s.OWN)
    c.emit("4a80")
    c.branch(6, "no")
    # A back press returns to Sketch. Its release still belongs to this list;
    # otherwise the old Sketch NO handler would also dismiss the parent view.
    load(c, BACK_KEY)
    c.emit("b082")
    c.branch(6, "press")
    c.emit("202b0010")
    c.imm("0280", 1)
    c.branch(6, "press")
    value(c, BACK_KEY, 0)
    c.branch(0, "yes")
    c.label("press")
    c.imm("0c82", NO)
    c.branch(6, "name_key")
    load(c, MODE)
    c.emit("4a80")
    c.branch(7, "name_key")
    c.emit("202b0010")
    c.imm("0280", 1)
    c.branch(7, "yes")  # A dismissed filename/message can release NO here.
    c.label("name_key")
    # Open naming on the matching YES release, so the key that entered the
    # editor cannot also accept its default name. Foreign modal releases and
    # unpaired releases must never begin a save.
    c.imm("0c82", YES)
    c.branch(6, "ordinary_press")
    load(c, MODE)
    c.emit("4a80")
    c.branch(7, "ordinary_press")
    c.emit("202b0010")
    c.imm("0280", 1)
    c.branch(6, "ordinary_press")
    load(c, NAME_KEY)
    c.emit("4a80")
    c.branch(7, "no")
    value(c, NAME_KEY, 0)
    c.branch(0, "action")
    c.label("ordinary_press")
    c.emit("202b0010")
    c.imm("0280", 9)
    c.imm("0c80", 1)
    c.branch(6, "no")
    load(c, MODE)
    c.emit("4a80")
    c.branch(6, "list")
    c.imm("0c82", DOWN)
    c.branch(6, "no")
    value(c, MODE, 1)
    value(c, ROW, 0)
    value(c, NAME_KEY, 0)
    c.branch(0, "yes")
    c.label("list")
    for k in (NO, LEFT):
        c.imm("0c82", k)
        c.branch(7, "back")
    c.imm("0c82", UP)
    c.branch(7, "up")
    c.imm("0c82", DOWN)
    c.branch(7, "down")
    c.imm("0c82", YES)
    c.branch(6, "preview_key")
    value(c, NAME_KEY, 1)
    c.branch(0, "yes")
    c.label("preview_key")
    c.imm("0c82", RIGHT)
    c.branch(7, "action")
    c.branch(0, "no")
    c.label("up")
    load(c, ROW)
    c.imm("0680", -1)
    s.clamp(c, 0, 11, "up")
    store(c, ROW)
    c.branch(0, "yes")
    c.label("down")
    b.call(c, COUNT)
    c.imm("0680", -1)
    c.emit("2600")
    load(c, ROW)
    c.emit("5280 b083")
    c.branch(3, "next_row")
    c.emit("2003")
    c.label("next_row")
    store(c, ROW)
    c.branch(0, "yes")
    c.label("back")
    store(c, BACK_KEY, 2)
    value(c, NAME_KEY, 0)
    b.call(c, 0x40139AE6)
    b.load(c, b.JOB)
    c.imm("0c80", 1)
    c.branch(7, "cancel")
    c.imm("0c80", 2)
    c.branch(6, "root")
    c.label("cancel")
    b.value(c, b.CANCEL, 1)
    c.label("root")
    value(c, MODE, 0)
    c.branch(0, "yes")
    c.label("action")
    load(c, ROW)
    c.emit("2f00")
    b.call(c, TARGET, 4)
    c.emit("4a80")
    c.branch(7, "empty")
    c.imm("0c82", YES)
    c.branch(7, "name")
    c.emit("2f01")
    b.call(c, p.SUBMIT, 4)
    c.emit("4a80")
    c.branch(6, "busy")
    c.branch(0, "yes")
    c.label("name")
    c.emit("2f08 2f00")
    b.call(c, OPEN_NAME, 8)
    c.emit("7002")
    c.branch(0, "return")  # The native modal now owns painting.
    c.label("empty")
    c.imm("4879", t["missing"])
    c.branch(0, "message")
    c.label("busy")
    c.imm("4879", t["busy"])
    c.label("message")
    b.call(c, MESSAGE, 4)
    c.label("yes")
    c.emit("7001")
    c.branch(0, "return")
    c.label("no")
    c.emit("7000")
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(KEY)


def rotate():
    c = Code()
    c.emit("4feffff0 48d70c0c 246f0014 266f0018")
    load(c, MODE)
    c.emit("4a80")
    c.branch(7, "no")
    c.emit("202b000c")
    c.imm("0c80", 9)
    c.branch(6, "yes")
    c.emit("202b0010 4a80")
    c.branch(7, "yes")
    c.branch(11, "negative")
    c.emit("7401")
    c.branch(0, "step")
    c.label("negative")
    c.emit("74ff")
    c.label("step")
    b.call(c, COUNT)
    c.imm("0680", -1)
    c.emit("2600")
    load(c, ROW)
    c.emit("d082")
    s.clamp(c, 0, 11, "list")
    c.emit("b083")
    c.branch(3, "row")
    c.emit("2003")
    c.label("row")
    store(c, ROW)
    c.emit("2f0a")
    b.call(c, 0x4011AE46, 4)
    c.label("yes")
    c.emit("7001")
    c.branch(0, "return")
    c.label("no")
    c.emit("7000")
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(ROTATE)


def callback(t):
    c = Code()
    c.emit("206f0004 2250 20280004 22290004 b081")
    c.branch(6, "bad")
    c.emit("206f0008 2f10 2f290018")
    b.call(c, b.SUBMIT, 8)
    c.emit("4a80")
    c.branch(6, "bad")
    c.emit("4e75")
    c.label("bad")
    c.imm("4879", t["busy"])
    b.call(c, MESSAGE, 4)
    c.emit("4e75")
    return c.finish(CALLBACK)


def poll(t):
    c = Code()
    c.emit("4feffff0 48d70303")
    b.load(c, b.COMPLETIONS)
    load(c, LAST, 1)
    c.emit("b081")
    c.branch(7, "return")
    store(c, LAST)
    load(c, VIEW)
    c.emit("4a80")
    c.branch(7, "return")
    c.emit("2f00")
    b.call(c, 0x4011AE46, 4)
    b.load(c, b.KIND)
    c.imm("0c80", 2)
    c.branch(7, "preview")
    b.load(c, b.RESULT)
    c.emit("4a80")
    c.branch(6, "failed")
    c.imm("4879", t["saved"])
    c.branch(0, "show")
    c.label("failed")
    c.imm("4879", t["failed"])
    c.branch(0, "show")
    c.label("preview")
    b.load(c, b.RESULT)
    c.emit("4a80")
    c.branch(7, "return")
    c.imm("4879", t["preview_failed"])
    c.label("show")
    b.call(c, MESSAGE, 4)
    c.label("return")
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", b.POLL)
    return c.finish(POLL)


def payload():
    t, data = texts()
    parts = {
        DRAW: draw(t),
        KEY: key(t),
        ROTATE: rotate(),
        CALLBACK: callback(t),
        OPEN_NAME: f.open_name(
            OPEN_NAME, MANAGER, CALLBACK, PUSH, t["title"], t["initial"]
        ),
        MESSAGE: f.message(MESSAGE, PUSH),
        PUSH: f.push_dialog(PUSH),
        MANAGER: f.manager(MANAGER),
        POLL: poll(t),
        TARGET: target(),
        COUNT: count(),
    }
    seq = sorted(parts.items())
    for (at, raw), (nxt, _) in zip(seq, seq[1:], strict=False):
        require(at + len(raw) <= nxt, "Sketchbook UI code overlap")
    return parts, data
