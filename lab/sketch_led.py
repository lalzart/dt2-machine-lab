"""SONG capture indicator at the stock OS1.16 LED output boundary.

No new state or service loop. Only SONG's output value is substituted while
the existing BUF transaction and native recorder both say recording. Every
other request follows the displaced stock entry; the compositor restores its
own value on the next normal LED update after capture ends.
"""

import struct

from lab import buf_next_bar as nb
from lab import sketch
from lab.emit import Code

ENTRY = sketch.BASE + 0x7800
TRAMP = sketch.BASE + 0x7900
SITE = 0x40133D64
PREFIX = bytes.fromhex("4e56ffec202e0008")
SONG, RED = 5, 0x11  # Native logical LED ID; UART index 4, stock RECORD red.


def output():
    c = Code()
    c.emit("202f0004")
    c.imm("0c80", SONG)
    c.branch(6, "stock")
    nb.load(c, nb.PHASE)
    c.imm("0c80", 2)
    c.branch(6, "stock")
    nb.load(c, nb.CTRL)
    c.emit("4a80")
    c.branch(7, "stock")
    c.emit("2f00")
    sketch.call(c, nb.auto.RECORDER_STATE, 4)
    c.imm("0c80", 2)
    c.branch(6, "stock")
    # Copy arguments: never overwrite the caller's original value or frame.
    c.emit(f"4878{RED:04x} 4878{SONG:04x}")
    sketch.call(c, TRAMP, 8)
    c.emit("4e75")
    c.label("stock")
    c.emit(PREFIX.hex())
    c.imm("4ef9", SITE + len(PREFIX))
    return c.finish(ENTRY)


def payload():
    return {
        ENTRY: output(),
        TRAMP: PREFIX + bytes.fromhex("4ef9") + struct.pack(">I", SITE + len(PREFIX)),
    }
