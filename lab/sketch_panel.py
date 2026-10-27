"""Recorder-style Sketch panel; drawing only, no sampler or audio state writes."""

from lab import sketch as s
from lab.emit import Code
from lab.project import require

DRAW, END = s.BASE + 0x6000, s.BASE + 0x6E00
VALUE_FACE, LABEL_FACE = 0x402A96A0, 0x402A6C30
LABELS = {
    "panel_title": "SKETCH",
    "panel_buf": "%u",
    "panel_source": "%s%s",
    "panel_buf_label": "BUF",
    "panel_source_label": "SRC",
    "panel_channel_label": "CHAN",
    "panel_length_label": "LEN",
    "panel_monitor_label": "MON",
    "panel_start_label": "START",
}


def draw(t, *, managed_buffers=False):
    if managed_buffers:
        from lab import sketch_managed as managed
    getters = managed.GETTERS if managed_buffers else s.GETTERS
    c = Code()
    # Native Font is an eight-byte temporary at SP+0x30, outside saved registers.
    c.emit("4fefffc0 48d77cfc 246f0044 266f0048 49ef0030")

    def rect(x0, y0, x1, y1, colour=1):
        for v in (colour, y1, x1, y0, x0):
            c.imm("4879", v)
        c.emit("2f0b")
        s.call(c, 0x40112ECE, 24)

    def text(pointer, x, y, face=VALUE_FACE, align=2):
        # Same font constructor, renderer and destructor as SamplerView.
        c.imm("4879", face)
        c.emit("2f0c")
        s.call(c, 0x401144F8, 8)
        c.imm("4879", pointer)
        for v in (align, y, x):
            c.imm("4879", v)
        c.emit("2f0c 2f0b")
        s.call(c, s.TEXT, 24)
        c.emit("2f0c")
        s.call(c, 0x40114374, 4)

    def value(x, y, pointer_reg=0):
        # Preserve a computed string pointer across native Font construction.
        c.emit(f"{0x2A00 | pointer_reg:04x}")  # MOVE.L Dn,D5
        c.imm("4879", VALUE_FACE)
        c.emit("2f0c")
        s.call(c, 0x401144F8, 8)
        c.emit("2f05")
        for v in (2, y, x):
            c.imm("4879", v)
        c.emit("2f0c 2f0b")
        s.call(c, s.TEXT, 24)
        c.emit("2f0c")
        s.call(c, 0x40114374, 4)

    def fmt(key, args):
        for a in reversed(args):
            c.emit(a)
        c.imm("4879", t[key])
        c.imm("4879", s.LINE)
        s.call(c, s.PRINT, 4 * (len(args) + 2))

    def table(at, high, tag):
        s.clamp(c, 0, high, tag)
        c.emit("d080 d080")
        c.imm("41f9", at)
        c.emit("d1c0 2010")

    # A centered title; the recorder's ARM bitmap is not a Sketch control.
    text(t["panel_title"], 64, 56)
    rect(0, 54, 127, 63, -1)

    # A-D follow the physical encoder columns; E/F occupy the bottom left.
    s.load(c, s.BUF)
    c.emit("2f00")
    c.imm("4879", t["panel_buf"])
    c.imm("4879", s.LINE)
    s.call(c, s.PRINT, 12)
    text(s.LINE, 16, 43)
    text(t["panel_buf_label"], 16, 33, LABEL_FACE)

    c.emit("2f2a014c")
    s.call(c, getters[0], 4)
    c.emit("2400 2f00 2f0a")
    s.call(c, 0x4001FD88, 8)
    c.emit("2600 2f02 2f0a")
    s.call(c, 0x4001FDBE, 8)
    fmt("panel_source", ["2f03", "2f00"])
    text(s.LINE, 48, 43)
    text(t["panel_source_label"], 48, 33, LABEL_FACE)

    c.emit("2f2a014c")
    s.call(c, getters[1], 4)
    c.emit("2f00 2f0a")
    s.call(c, 0x4001FDF4, 8)
    value(80, 43)
    text(t["panel_channel_label"], 80, 33, LABEL_FACE)

    c.emit("2f2a014c")
    s.call(c, getters[2], 4)
    table(s.TEXTS, 8, "length")
    value(112, 43)
    text(t["panel_length_label"], 112, 33, LABEL_FACE)

    c.emit("2f2a014c")
    s.call(c, getters[3], 4)
    table(s.TEXTS + 36, 1, "monitor")
    value(16, 20)
    text(t["panel_monitor_label"], 16, 10, LABEL_FACE)

    if managed_buffers:
        s.call(c, managed.GETTERS[4])
    else:
        s.load(c, s.START_MODE)
    c.emit("4a80")
    c.branch(7, "bar")
    c.imm("203c", t["start_now"])
    c.branch(0, "start_mode")
    c.label("bar")
    c.imm("203c", t["start_bar"])
    c.label("start_mode")
    value(48, 20)
    text(t["panel_start_label"], 48, 10, LABEL_FACE)

    if managed_buffers:
        s.call(c, managed.STATUS_TEXT)
        value(96, 20)
        text(managed.TEXTS + 7 * 16, 96, 10, LABEL_FACE)

    c.emit("4cd77cfc 4fef0040 4e75")
    raw = c.finish(DRAW)
    require(DRAW + len(raw) <= END, "Sketch recorder-style panel overlap")
    return raw
